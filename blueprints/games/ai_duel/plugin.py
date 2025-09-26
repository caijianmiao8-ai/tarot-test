# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, Response, jsonify, make_response, stream_with_context
import os, json, secrets, time, requests, re
from itsdangerous import URLSafeSerializer
from typing import Iterable, List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import g   # ← 新增
from core.runtime import GameRuntime   # ← 新增
from config import Config 
from datetime import datetime, timedelta, timezone
import threading
from database import DatabaseManager


SLUG = "ai_duel"

def get_meta():
    return {
        "slug": SLUG,
        "title": "AI 斗蛐蛐",
        "subtitle": "两个 LLM 扮演不同角色围绕一个问题讨论 + 裁判",
        "path": f"/g/{SLUG}/",
        "tags": ["LLM","Debate","Roleplay","Judge","Streaming"]
    }

bp = Blueprint(
    SLUG, __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",
)

# ---------------- 基础：轻身份（仅 cookie） ----------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
COOKIE_SECURE = os.getenv("COOKIE_SECURE","0").lower() in ("1","true","yes")
SER = URLSafeSerializer(SECRET_KEY, salt=f"{SLUG}-state")

def _ids():
    user_id = (getattr(g, "user", {}) or {}).get("id")
    sid = request.cookies.get("sid")
    return user_id, sid

def _ensure_sid(resp):
    if request.cookies.get("sid"):
        return resp
    sid = secrets.token_hex(16)
    resp.set_cookie("sid", sid, max_age=60*60*24*730, httponly=True, samesite="Lax", secure=COOKIE_SECURE)
    return resp

@bp.get("/")
@bp.get("")
def page():
    resp = make_response(render_template(f"games/{SLUG}/index.html"))
    return _ensure_sid(resp)


# === DB 缓存 DAO ===
class ModelCacheDAO:
    @staticmethod
    def upsert(model_id: str, name: str, ok: bool, error: str | None, checked_at: datetime):
        with DatabaseManager.get_db() as conn, conn.cursor() as cur:
            cur.execute("""
                insert into model_availability(model_id, model_name, ok, error, checked_at)
                values (%s,%s,%s,%s,%s)
                on conflict (model_id) do update set
                  model_name = excluded.model_name,
                  ok         = excluded.ok,
                  error      = excluded.error,
                  checked_at = excluded.checked_at
            """, (model_id, name, ok, error, checked_at))
            conn.commit()

    @staticmethod
    def get_all():
        with DatabaseManager.get_db() as conn, conn.cursor() as cur:
            cur.execute("""select model_id, model_name, ok, error, checked_at
                           from model_availability order by model_name asc""")
            return cur.fetchall()

    @staticmethod
    def get_last_checked_at():
        with DatabaseManager.get_db() as conn, conn.cursor() as cur:
            cur.execute("select max(checked_at) as ts from model_availability")
            row = cur.fetchone()
            return (row['ts'] if isinstance(row, dict) else (row[0] if row else None))

def fetch_openrouter_directory(api_key: str) -> list[dict]:
    # 返回 [{id,name}, ...]
    try:
        r = requests.get("https://openrouter.ai/api/v1/models",
                         headers={"Authorization": f"Bearer {api_key}"},
                         timeout=20)
        if r.ok:
            data = (r.json() or {}).get("data", [])
            out = []
            for m in data:
                mid = m.get("id")
                if not mid: continue
                out.append({"id": mid, "name": m.get("name") or mid})
            return out
    except Exception:
        pass
    # 回退静态
    return [
        {"id": "openai/gpt-4o-mini",                 "name": "OpenAI · GPT-4o-mini"},
        {"id": "anthropic/claude-3.5-sonnet",        "name": "Anthropic · Claude 3.5 Sonnet"},
        {"id": "meta-llama/llama-3.1-70b-instruct",  "name": "Llama · 3.1-70B Instruct"},
        {"id": "qwen/qwen-2.5-72b-instruct",         "name": "Qwen · 2.5-72B Instruct"},
        {"id": "google/gemini-1.5-pro",              "name": "Google · Gemini 1.5 Pro"},
        {"id": "deepseek/deepseek-chat",             "name": "DeepSeek · Chat"},
    ]

def preflight_model_with_err(model_id: str, app_url: str, app_name: str) -> tuple[bool, str]:
    ok, err = preflight_model(model_id, app_url, app_name)
    return ok, (err or "")

def refresh_models_bulk(app_url: str, app_name: str, *, max_workers: int = 6) -> dict:
    """
    拉目录 -> 并发预检 -> 全量写 DB 缓存
    返回 {count:int, ok:int}
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {"count": 0, "ok": 0}

    directory = fetch_openrouter_directory(api_key)
    if not directory:
        return {"count": 0, "ok": 0}

    ok_cnt = 0
    now = datetime.now(timezone.utc)
    def worker(m):
        nonlocal ok_cnt
        ok, err = preflight_model_with_err(m["id"], app_url, app_name)
        if ok: ok_cnt += 1
        ModelCacheDAO.upsert(m["id"], m["name"], ok, err, now)

    if max_workers <= 1:
        for m in directory: worker(m)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(worker, directory))

    return {"count": len(directory), "ok": ok_cnt}


# ---------------- 模型目录 + 可用性缓存/预检 ----------------
_MODEL_OK_CACHE: dict[str, float] = {}  # {model_id: expire_ts}
_MODEL_TTL_SEC = 600                    # 10 分钟

def _headers(app_url: str, app_name: str):
    return {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
        "Content-Type": "application/json",
        "HTTP-Referer": app_url,
        "X-Title": app_name,
    }

def preflight_model(model_id: str, app_url: str, app_name: str) -> Tuple[bool, str]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return False, "缺少 OPENROUTER_API_KEY"
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {"model": model_id, "messages": [{"role":"user","content":"ping"}], "max_tokens": 1, "stream": False}
    try:
        r = requests.post(url, headers=_headers(app_url, app_name), json=payload, timeout=15)
        if r.status_code == 200:
            return True, ""
        try:
            j = r.json()
            msg = (j.get("error") or {}).get("message") or j.get("message") or r.text
        except Exception:
            msg = r.text
        return False, f"OpenRouter {r.status_code}: {msg}"
    except Exception as e:
        return False, str(e)

def _model_ok(mid: str, app_url: str, app_name: str) -> bool:
    now = time.time()
    exp = _MODEL_OK_CACHE.get(mid)
    if exp and exp > now:
        return True
    ok, _ = preflight_model(mid, app_url, app_name)
    if ok:
        _MODEL_OK_CACHE[mid] = now + _MODEL_TTL_SEC
    return ok

@bp.get("/api/models")
def api_models():
    """
    ?available=1  只返回可用(ok=true)的；默认 1
    ?refresh=1    强制同步刷新（仅限你自己调试；建议用 /api/models/refresh）
    """
    only_available = (request.args.get("available","1").lower() in ("1","true","yes"))
    force_refresh  = (request.args.get("refresh","0").lower() in ("1","true","yes"))

    app_url  = os.getenv("APP_URL") or request.host_url.rstrip("/")
    app_name = os.getenv("APP_NAME", "AI Duel Arena")

    # 环境变量控制缓存策略
    ttl_days  = int(os.getenv("MODEL_CACHE_TTL_DAYS", "30"))
    lazy_bg   = os.getenv("MODEL_CACHE_LAZY_BG", "0").lower() in ("1","true","yes")  # 是否过期后后台懒刷新

    rows = ModelCacheDAO.get_all()
    last = ModelCacheDAO.get_last_checked_at()

    def rows_to_models(rs):
        out = []
        for r in rs:
            rid = r["model_id"] if isinstance(r, dict) else r[0]
            nm  = r["model_name"] if isinstance(r, dict) else r[1]
            ok  = r["ok"] if isinstance(r, dict) else r[2]
            if (not only_available) or ok:
                out.append({"id": rid, "name": nm})
        if not out:
            out.append({"id":"fake/demo", "name":"内置演示（无 Key）"})
        out.sort(key=lambda x: x["name"].lower())
        return out

    # 1) 首次没有缓存：同步刷新一次
    if not rows or force_refresh:
        stat = refresh_models_bulk(app_url, app_name)
        rows = ModelCacheDAO.get_all()
        return jsonify({"ok": True, "models": rows_to_models(rows), "refreshed": True, "stat": stat})

    # 2) 有缓存：直接用，并根据 TTL 判断是否后台懒刷新
    models = rows_to_models(rows)

    too_old = False
    if last:
        # last 可能是 naive/aware，统一成 aware
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        too_old = (datetime.now(timezone.utc) - last) > timedelta(days=ttl_days)
    else:
        too_old = True

    if too_old and lazy_bg:
        # 后台线程，立即返回缓存（Vercel 上通常也能跑完；不保证）
        try:
            threading.Thread(target=lambda: refresh_models_bulk(app_url, app_name), daemon=True).start()
        except Exception:
            pass

    return jsonify({"ok": True, "models": models, "refreshed": False, "cache_age_days": None if not last else (datetime.now(timezone.utc)-last).days})


@bp.post("/api/models/refresh")
def api_models_refresh():
    token = request.args.get("token") or request.headers.get("X-Refresh-Token")
    secret = os.getenv("MODEL_REFRESH_TOKEN")  # 你自己在环境变量里设置一个强随机串
    if not secret or token != secret:
        return jsonify({"ok": False, "error": "UNAUTHORIZED"}), 401

    app_url  = os.getenv("APP_URL") or request.host_url.rstrip("/")
    app_name = os.getenv("APP_NAME", "AI Duel Arena")
    stat = refresh_models_bulk(app_url, app_name)
    return jsonify({"ok": True, "stat": stat})


@bp.post("/api/models/check")
def api_models_check():
    j = request.get_json(silent=True) or {}
    mid = (j.get("id") or "").strip()
    if not mid:
        return jsonify({"ok": False, "error": "NO_ID"}), 400
    app_url  = os.getenv("APP_URL") or request.host_url.rstrip("/")
    app_name = os.getenv("APP_NAME", "AI Duel Arena")
    ok, err = preflight_model(mid, app_url, app_name)
    if ok:
        _MODEL_OK_CACHE[mid] = time.time() + _MODEL_TTL_SEC
    return jsonify({"ok": ok, "error": err or ""})

# ---------------- OpenRouter 工具：一次性与流式 ----------------
def chat_once_openrouter(model_id: str, messages: List[Dict], app_url: str, app_name: str,
                         max_tokens: int = 800, temperature: float = 0.7) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 OPENROUTER_API_KEY 环境变量")
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    r = requests.post(url, headers=_headers(app_url, app_name), json=payload, timeout=120)
    if r.status_code != 200:
        try:
            j = r.json()
            msg = (j.get("error") or {}).get("message") or j.get("message") or r.text
        except Exception:
            msg = r.text
        raise RuntimeError(f"OpenRouter {r.status_code}: {msg}")
    j = r.json()
    return (j["choices"][0]["message"]["content"] or "").strip()

def _extract_text_from_chunk(obj) -> str:
    """
    兼容多供应商的 SSE 数据结构，尽可能提取文本。
    """
    try:
        choices = obj.get("choices") or []
        if not choices:
            return ""
        ch0 = choices[0] or {}
        # 1) OpenAI 兼容：delta.content 是字符串
        delta = ch0.get("delta") or {}
        c = delta.get("content")
        if isinstance(c, str):
            return c or ""
        # 2) 某些把 content 做成数组 [{type:'text'/'output_text', text:'...'}]
        if isinstance(c, list):
            out = []
            for piece in c:
                if isinstance(piece, dict):
                    if piece.get("type") in ("text", "output_text"):
                        txt = piece.get("text") or piece.get("content") or ""
                        if txt: out.append(txt)
            if out:
                return "".join(out)
        # 3) 有的直接给 text 字段
        if isinstance(ch0.get("text"), str):
            return ch0["text"] or ""
        # 4) 有的只在末尾给 message.content
        msg = ch0.get("message") or {}
        if isinstance(msg.get("content"), str):
            return msg["content"] or ""
    except Exception:
        return ""
    return ""

def stream_openrouter_messages(model_id: str, messages: List[Dict],
                               app_url: str | None = None,
                               app_name: str | None = None) -> Iterable[str]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 OPENROUTER_API_KEY")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = _headers(app_url or "", app_name or "")
    with requests.post(url, headers=headers,
                       json={"model": model_id, "messages": messages, "temperature": 0.7, "stream": True},
                       stream=True, timeout=600) as r:
        if r.status_code != 200:
            try:
                j = r.json()
                msg = (j.get("error") or {}).get("message") or j.get("message") or r.text
            except Exception:
                msg = r.text
            raise RuntimeError(f"OpenRouter {r.status_code}: {msg}")
        for raw in r.iter_lines(decode_unicode=False):
            if not raw:
                continue
            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            # 兼容多结构抽取
            delta_txt = _extract_text_from_chunk(obj)
            if delta_txt:
                yield delta_txt


def pick_streamer(model_id: str, app_url: str, app_name: str, max_tokens: int):
    prov = model_id.split("/", 1)[0]
    if prov == "fake":
        return lambda msgs: stream_fake_messages(model_id, msgs)
    else:
        return lambda msgs: stream_openrouter_messages(
            model_id, msgs, app_url=app_url, app_name=app_name, max_tokens=max_tokens
        )



def stream_fake_messages(model: str, messages: List[Dict]) -> Iterable[str]:
    last = messages[-1]["content"] if messages else "开始发言。"
    text = f"（{model}）基于上下文：{last[:60]}…… 我方观点是：首先… 其次… 最后…"
    for ch in text:
        yield ch
        time.sleep(0.01)


# ---------------- 文本组织：转录、摘要、消息构造 ----------------
def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def join_turns(transcript: List[Dict]) -> str:
    lines = []
    for t in transcript:
        if t["type"] != "turn":  # 只拼双方最终发言
            continue
        tag = "A方" if t["side"]=="A" else "B方"
        lines.append(f"[{tag}·第{t['round']}轮] {t['text']}")
    return "\n".join(lines)

def cheap_summarize(text: str, max_chars: int = 700) -> str:
    if not text: return ""
    s, total = [], 0
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        pick = line
        m = re.search(r"[。.!?]", line)
        if m: pick = line[:m.end()]
        s.append(pick)
        total += len(pick)
        if total >= max_chars: break
    out = " ".join(s)
    return (out[:max_chars] + "…") if len(out)>max_chars else out

def build_messages_for_side(topic: str,
                            preset_system: str,
                            opponent_preset: str,
                            transcript: List[Dict],
                            side_label: str,
                            opponent_label: str,
                            *,
                            reply_len: str = "medium",
                            max_ctx_tokens: int = 6000,
                            keep_last_rounds: int = 2):
    """
    - preset_system: 本方系统预设
    - opponent_preset: 对手系统预设（用于告知对手人设）
    - reply_len: 'short'/'medium'/'long'（决定字符上限）
    """
    # 字数上限映射（再配合 max_tokens 双保险）
    limit_map = {"short": 70, "medium": 140, "long": 220}
    limit_chars = limit_map.get(reply_len, 140)

    # —— 系统提示：明确本方 + 对手的人设，并要求互动 —— 
    self_profile = (preset_system or "").strip()
    opp_profile  = (opponent_preset or "").strip()
    if not self_profile:
        self_profile = f"你是{side_label}角色。"
    if not opp_profile:
        opp_profile = f"你的对手是{opponent_label}角色。"

    system = (
        f"{self_profile}\n\n"
        f"【对手设定】{opp_profile}\n\n"
        "对话要求：\n"
        "1) 回应必须紧扣对手要点，直接点名对手并引用其关键信息进行反驳/补充；\n"
        "2) 语言简洁有力，避免空话；\n"
        f"3) 单轮不超过 {limit_chars} 个汉字；\n"
        "4) 如有数据/示例，请简短引用来源或给出类比；\n"
        "5) 切勿重复整段论点，尽量推进讨论。"
    )

    # —— 最近 N 轮原文 + 更早摘要 —— 
    turns = [t for t in transcript if t["type"] == "turn"]
    recent_rounds = []
    if turns:
        max_round = max(t["round"] for t in turns)
        lo = max(1, max_round - keep_last_rounds + 1)
        recent_rounds = [t for t in turns if t["round"] >= lo]
    recent_text = join_turns(recent_rounds) if recent_rounds else ""
    earlier = [t for t in turns if t not in recent_rounds]
    summary_text = cheap_summarize(join_turns(earlier)) if earlier else ""

    next_round = (turns[-1]["round"] if turns else 0) + (1 if (not turns or turns[-1]["side"] == "B") else 0)

    def compose(summ, recent):
        blocks = []
        blocks.append(f"【话题】{topic}")
        if summ:   blocks.append(f"【既往摘要】{summ}")
        if recent: blocks.append(f"【最近几轮】\n{recent}")
        blocks.append(
            f"请给出你的第 {next_round} 轮回应（≤{limit_chars}字，直入要点，必要时引用对手内容并明确称呼“{opponent_label}”）："
        )
        return "\n\n".join(blocks)

    user = compose(summary_text, recent_text)
    budget = max_ctx_tokens - (est_tokens(system) + 300)

    # 动态瘦身
    k = keep_last_rounds
    while est_tokens(user) > budget and k > 0:
        k -= 1
        if turns:
            max_round = max(t["round"] for t in turns)
            lo = max(1, max_round - k + 1)
            recent_rounds = [t for t in turns if t["round"] >= lo]
            recent_text = join_turns(recent_rounds) if recent_rounds else ""
        user = compose(summary_text, recent_text)
    while est_tokens(user) > budget and summary_text:
        summary_text = summary_text[: max(50, len(summary_text) - 200)]
        user = compose(summary_text, recent_text)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ]


    def compose(summ, recent):
        blocks = [f"【话题】{topic}"]
        if summ:
            blocks.append(f"【既往摘要】{summ}")
        if recent:
            blocks.append(f"【最近几轮】\n{recent}")
        blocks.append(f"请给出你的第 {next_round} 轮回应：")
        return "\n\n".join(blocks)

    user = compose(summary_text, recent_text)
    budget = max_ctx_tokens - (est_tokens(system) + 300)

    # 动态瘦身
    k = keep_last_rounds
    while est_tokens(user) > budget and k > 0:
        k -= 1
        if turns:
            max_round = max(t["round"] for t in turns)
            lo = max(1, max_round - k + 1)
            recent_rounds = [t for t in turns if t["round"] >= lo]
            recent_text = join_turns(recent_rounds) if recent_rounds else ""
        user = compose(summary_text, recent_text)
    while est_tokens(user) > budget and summary_text:
        summary_text = summary_text[: max(50, len(summary_text) - 200)]
        user = compose(summary_text, recent_text)

    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


    def compose(summ, recent):
        blocks = []
        blocks.append(f"【话题】{topic}")
        if summ:   blocks.append(f"【既往摘要】{summ}")
        if recent: blocks.append(f"【最近几轮】\n{recent}")
        blocks.append(f"请给出你的第 {next_round} 轮回应（≤150字，直入要点，可举例）：")
        return "\n\n".join(blocks)

    user = compose(summary_text, recent_text)
    budget = max_ctx_tokens - (est_tokens(system) + 300)

    # 动态瘦身
    k = keep_last_rounds
    while est_tokens(user) > budget and k > 0:
        k -= 1
        if turns:
            max_round = max(t["round"] for t in turns)
            lo = max(1, max_round - k + 1)
            recent_rounds = [t for t in turns if t["round"] >= lo]
            recent_text = join_turns(recent_rounds) if recent_rounds else ""
        user = compose(summary_text, recent_text)
    while est_tokens(user) > budget and summary_text:
        summary_text = summary_text[: max(50, len(summary_text)-200)]
        user = compose(summary_text, recent_text)

    return [{"role":"system","content":system},{"role":"user","content":user}]

def build_judge_messages(topic: str, transcript: List[Dict], *, final: bool=False):
    """
    裁判提示：可做“每轮点评”或“终局裁决”
    """
    if final:
        txt = join_turns([t for t in transcript if t["type"]=="turn"])
        sys = ("你是专业裁判。请基于双方完整转录，做客观判定："
               "1）总结双方最有力观点 2）指出逻辑/证据问题 3）判定更优一方及理由。"
               "输出≤200字。")
        user = f"【话题】{topic}\n【双方发言】\n{txt}\n请给出最终裁决："
    else:
        # 取最后一轮 A/B
        last_round = max((t["round"] for t in transcript if t["type"]=="turn"), default=1)
        ab = [t for t in transcript if t["type"]=="turn" and t["round"]==last_round]
        ab_txt = "\n".join([f"[{t['side']}·第{t['round']}轮] {t['text']}" for t in ab])
        sys = ("你是现场裁判。请给出简短点评（≤120字）："
               "指出双方当轮亮点与瑕疵，避免人身攻击，保持专业。")
        user = f"【话题】{topic}\n【当轮发言】\n{ab_txt}\n请给出裁判点评："
    return [{"role":"system","content":sys},{"role":"user","content":user}]

# ---------------- 预设扩写：将 seed 扩展成 A/B 两个系统预设 ----------------
@bp.post("/api/preset/expand")
def api_preset_expand():
    j = request.get_json(silent=True) or {}
    seed = (j.get("seed") or "").strip()
    builder = (j.get("builderModel") or "").strip() or "openai/gpt-4o-mini"
    if not seed:
        return jsonify({"ok": False, "error": "NO_SEED"}), 400
    app_url  = os.getenv("APP_URL") or request.host_url.rstrip("/")
    app_name = os.getenv("APP_NAME", "AI Duel Arena")
    try:
        prompt = [
            {"role":"system","content":
             "你是对话设计师。根据用户的一句设定，将两个参与方的系统预设写清楚，"
             "风格可不同但彼此互补。返回 JSON：{A: <系统预设>, B: <系统预设>}，不要多余文字。"},
            {"role":"user","content":
             f"一句设定：{seed}\n请给出适用于两位角色的系统预设，语种与设定一致，面向实时对话，长度各≤150字。"}
        ]
        text = chat_once_openrouter(builder, prompt, app_url, app_name, max_tokens=500, temperature=0.5)
        # 尝试从文本里提取 JSON
        m = re.search(r"\{[\s\S]*\}", text)
        obj = {"A":"你是角色 A。简明扼要，偏事实论证。", "B":"你是角色 B。富有想象力，善于举例。"}
        if m:
            try: obj = json.loads(m.group(0))
            except Exception: pass
        return jsonify({"ok": True, "presetA": obj.get("A",""), "presetB": obj.get("B",""), "raw": text})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------------- 主流程：流式对话 + 可选裁判 ----------------
@bp.post("/api/stream")
def api_stream():
    j = request.get_json(silent=True) or {}
    topic    = (j.get("topic") or "").strip()

    # ★ 轮次上限 = 配置里的 max_rounds（默认 10）
    max_rounds_cfg = (Config.GAME_FEATURES.get("ai_duel", {}).get("max_rounds", 10))
    rounds   = max(1, min(int(j.get("rounds") or 4), int(max_rounds_cfg)))

    modelA   = j.get("modelA") or "fake/demo"
    modelB   = j.get("modelB") or "fake/demo"
    presetA  = (j.get("presetA") or "").strip()
    presetB  = (j.get("presetB") or "").strip()
    seed     = (j.get("seed") or "").strip()
    builder  = (j.get("builderModel") or "").strip() or "openai/gpt-4o-mini"

    judge_on        = bool(j.get("judge", False))
    judge_per_round = bool(j.get("judgePerRound", True))
    judge_model     = (j.get("judgeModel") or "").strip() or ("fake/demo" if not judge_on else "openai/gpt-4o-mini")
    reply_style = (j.get("reply_style") or "medium").strip().lower()
    if reply_style not in ("short","medium","long"):
        reply_style = "medium"
    # 给流式的 max_tokens 一个映射（和上面 limit_chars 相匹配）
    mt_map = {"short": 120, "medium": 220, "long": 360}
    side_max_tokens = mt_map.get(reply_style, 220)

    if not topic:
        return jsonify({"ok": False, "error": "NO_TOPIC"}), 400

    # ★★★ 配额校验：一次开赛 = 1 次使用
    user_id, sid = _ids()
    ok, left = GameRuntime.can_play("ai_duel", user_id, sid, is_guest=(user_id is None))
    if not ok:
        # 直接 429，前端会提示今日剩余次数
        return jsonify({"ok": False, "error": "DAILY_LIMIT", "left": left}), 429

    # ★★★ 建立/获取“当日会话”，并且只在这里记 1 次用量
    s = GameRuntime.session("ai_duel", user_id, sid, daily=True)
    GameRuntime.log("ai_duel", s["id"], user_id,
                    "start",
                    {"topic": topic, "rounds": rounds, "modelA": modelA, "modelB": modelB},
                    bump=True, sid=sid)  # ← 仅此处 bump 记账

    # ↓↓↓ 你原先的流式生成逻辑（gen / Response）保持不动
    app_url  = os.getenv("APP_URL") or request.host_url.rstrip("/")
    app_name = os.getenv("APP_NAME", "AI Duel Arena")
    streamA  = pick_streamer(modelA, app_url, app_name, max_tokens=side_max_tokens)
    streamB  = pick_streamer(modelB, app_url, app_name, max_tokens=side_max_tokens)

    transcript: List[Dict] = []

    def gen():
        # ✅ 关键修复：nonlocal 必须放在内层函数顶部，且在第一次使用这些变量之前
        nonlocal presetA, presetB

        # 元信息
        yield json.dumps({"type":"meta","topic":topic,"rounds":rounds,
                          "A":modelA,"B":modelB,
                          "judge": judge_on, "judgePerRound": judge_per_round, "judgeModel": judge_model},
                         ensure_ascii=False) + "\n"

        # 若未给预设但给了 seed，先扩写
        if (not presetA or not presetB) and seed:
            try:
                text = chat_once_openrouter(
                    builder,
                    [
                        {"role":"system","content":
                         "你是对话设计师。根据用户的一句设定，将两个参与方的系统预设写清楚，"
                         "返回 JSON：{A: <系统预设>, B: <系统预设>}，不要多余文字。"},
                        {"role":"user","content":
                         f"一句设定：{seed}\n请给出适用于两位角色的系统预设，语种与设定一致，长度各≤150字。"}
                    ],
                    app_url, app_name, max_tokens=500, temperature=0.5
                )
                m = re.search(r"\{[\s\S]*\}", text)
                if m:
                    try:
                        obj = json.loads(m.group(0))
                    except Exception:
                        obj = {}
                    a_local = (obj.get("A") or "").strip()
                    b_local = (obj.get("B") or "").strip()
                    if a_local or b_local:
                        if a_local: presetA = a_local
                        if b_local: presetB = b_local
                        yield json.dumps({"type":"preset","A":presetA,"B":presetB}, ensure_ascii=False) + "\n"
            except Exception as e:
                yield json.dumps({"type":"error","who":"builder","message":str(e)}, ensure_ascii=False) + "\n"

        # 预检 A/B/裁判
        okA, errA = preflight_model(modelA, app_url, app_name) if not modelA.startswith("fake/") else (True,"")
        okB, errB = preflight_model(modelB, app_url, app_name) if not modelB.startswith("fake/") else (True,"")
        okJ, errJ = (True,"")
        if judge_on and not judge_model.startswith("fake/"):
            okJ, errJ = preflight_model(judge_model, app_url, app_name)
        if (not okA) or (not okB) or (judge_on and not okJ):
            if not okA: yield json.dumps({"type":"error","side":"A","round":1,"message":errA}, ensure_ascii=False) + "\n"
            if not okB: yield json.dumps({"type":"error","side":"B","round":1,"message":errB}, ensure_ascii=False) + "\n"
            if judge_on and not okJ: yield json.dumps({"type":"error","who":"judge","message":errJ}, ensure_ascii=False) + "\n"
            yield json.dumps({"type":"end"}) + "\n"
            return

        # 裁判流：streamer
        streamJ = (lambda msgs: stream_fake_messages(judge_model, msgs)) if judge_model.startswith("fake/") \
                  else (lambda msgs: stream_openrouter_messages(judge_model, msgs, app_url=app_url, app_name=app_name))

        # 对战
        for r in range(1, rounds+1):
            # A
            msgsA = build_messages_for_side(
                topic, presetA, presetB, transcript,
                side_label="A方", opponent_label="B方",
                reply_len=reply_style, max_ctx_tokens=6000, keep_last_rounds=2
            )
            acc = []
            try:
                for delta in streamA(msgsA):
                    acc.append(delta)
                    yield json.dumps({"type":"chunk","side":"A","round":r,"delta":delta}, ensure_ascii=False) + "\n"
            except Exception as e:
                yield json.dumps({"type":"error","side":"A","round":r,"message":str(e)}, ensure_ascii=False) + "\n"
                break
            fullA = "".join(acc).strip()
            transcript.append({"type":"turn","side":"A","round":r,"text":fullA})
            yield json.dumps({"type":"turn","side":"A","round":r,"text":fullA}, ensure_ascii=False) + "\n"

            # B
            msgsB = build_messages_for_side(
                topic, presetB, presetA, transcript,
                side_label="B方", opponent_label="A方",
                reply_len=reply_style, max_ctx_tokens=6000, keep_last_rounds=2
            )

            acc = []
            try:
                for delta in streamB(msgsB):
                    acc.append(delta)
                    yield json.dumps({"type":"chunk","side":"B","round":r,"delta":delta}, ensure_ascii=False) + "\n"
            except Exception as e:
                yield json.dumps({"type":"error","side":"B","round":r,"message":str(e)}, ensure_ascii=False) + "\n"
                break
            fullB = "".join(acc).strip()
            transcript.append({"type":"turn","side":"B","round":r,"text":fullB})
            yield json.dumps({"type":"turn","side":"B","round":r,"text":fullB}, ensure_ascii=False) + "\n"

            # 每轮裁判
            if judge_on and judge_per_round:
                try:
                    msgsJ = build_judge_messages(topic, transcript, final=False)
                    accj = []
                    for delta in streamJ(msgsJ):
                        accj.append(delta)
                        yield json.dumps({"type":"judge_chunk","round":r,"delta":delta}, ensure_ascii=False) + "\n"
                    fullJ = "".join(accj).strip()
                    yield json.dumps({"type":"judge_turn","round":r,"text":fullJ}, ensure_ascii=False) + "\n"
                except Exception as e:
                    yield json.dumps({"type":"error","who":"judge","round":r,"message":str(e)}, ensure_ascii=False) + "\n"

        # 最终裁判（若只开终裁或与每轮裁判并存）
        if judge_on and not judge_per_round:
            try:
                msgsJF = build_judge_messages(topic, transcript, final=True)
                accf = []
                for delta in streamJ(msgsJF):
                    accf.append(delta)
                    yield json.dumps({"type":"judge_final_chunk","delta":delta}, ensure_ascii=False) + "\n"
                fullF = "".join(accf).strip()
                yield json.dumps({"type":"judge_final","text":fullF}, ensure_ascii=False) + "\n"
            except Exception as e:
                yield json.dumps({"type":"error","who":"judge_final","message":str(e)}, ensure_ascii=False) + "\n"

        yield json.dumps({"type":"end"}) + "\n"

    headers = {
        "Content-Type": "application/x-ndjson; charset=utf-8",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return Response(stream_with_context(gen()), headers=headers)


@bp.post("/track")
def track():
    _ = request.get_json(silent=True) or {}
    return ("", 204)

@bp.get("/api/quota")
def api_quota():
    user_id, sid = _ids()
    ok, left = GameRuntime.can_play("ai_duel", user_id, sid, is_guest=(user_id is None))
    # 推算总配额（仅用于展示）
    limits = Config.GAME_FEATURES.get("ai_duel", {})
    limit  = limits.get('daily_limit_user' if user_id else 'daily_limit_guest', 5)
    return jsonify({"ok": True, "left": left, "limit": limit})

# 在 ai_duel 的 plugin.py -> get_blueprint() 里，添加：
import os, requests

@bp.post("/api/presets")
def api_presets():
    data = request.get_json(silent=True) or {}
    topic = (data.get("topic") or "").strip()
    seed  = (data.get("seed") or "").strip()
    # 任选一个便宜稳定的模型来扩写预设（你也可改成你常用的）
    model = os.getenv("DUEL_PRESET_MODEL", "google/gemma-2-9b-it")
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        return jsonify({"ok": False, "error": "NO_API_KEY"}), 500
    if not (topic or seed):
        return jsonify({"ok": False, "error": "EMPTY"}), 400

    prompt = f"""请为一场围绕“{topic or seed}”的讨论，分别生成两个角色的扮演预设（中文），语言风格、关注点与价值取向要形成对比。每个预设 2-4 句，简短有辨识度。输出 JSON：
{{"presetA":"...","presetB":"..."}}"""

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL","https://example.com"),
                "X-Title": "AI Duel Preset Builder",
            },
            json={
                "model": model,
                "messages": [
                    {"role":"system","content":"你是资深 Prompt 设计师，擅长将一句设定扩展成对立角色预设。"},
                    {"role":"user","content": prompt}
                ],
                "temperature": 0.7
            },
            timeout=30
        )
        resp.raise_for_status()
        txt = resp.json()["choices"][0]["message"]["content"]
        # 宽松解析 JSON（允许大括号内包含换行）
        import re, json as pyjson
        m = re.search(r"\{[\s\S]*\}", txt)
        if not m:
            return jsonify({"ok": False, "error": "PARSE_FAIL"}), 500
        data = pyjson.loads(m.group(0))
        return jsonify({"ok": True, "presetA": data.get("presetA",""), "presetB": data.get("presetB","")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def get_blueprint():
    return bp

