# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, Response, jsonify, make_response, stream_with_context, g
import os, json, secrets, time, requests, re, threading
from itsdangerous import URLSafeSerializer
from typing import Iterable, List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from core.runtime import GameRuntime
from database import DatabaseManager
from config import Config

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

# ---------------- 轻身份（cookie） ----------------
SECRET_KEY    = os.getenv("SECRET_KEY", "dev-secret")
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

# ---------------- 模型目录缓存（DB） ----------------
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
            cur.execute("""
                select model_id, model_name, ok, error, checked_at
                from model_availability
                order by model_name asc
            """)
            return cur.fetchall()

    @staticmethod
    def get_last_checked_at():
        with DatabaseManager.get_db() as conn, conn.cursor() as cur:
            cur.execute("select max(checked_at) as ts from model_availability")
            row = cur.fetchone()
            try:
                return row["ts"]
            except Exception:
                return row[0] if row else None

def fetch_openrouter_directory(api_key: str) -> list[dict]:
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
    # 回退
    return [
        {"id":"openai/gpt-4o-mini",                "name":"OpenAI · GPT-4o-mini"},
        {"id":"anthropic/claude-3.5-sonnet",       "name":"Anthropic · Claude 3.5 Sonnet"},
        {"id":"meta-llama/llama-3.1-70b-instruct", "name":"Llama · 3.1-70B Instruct"},
        {"id":"qwen/qwen-2.5-72b-instruct",        "name":"Qwen · 2.5-72B Instruct"},
        {"id":"google/gemini-1.5-pro",             "name":"Google · Gemini 1.5 Pro"},
        {"id":"deepseek/deepseek-chat",            "name":"DeepSeek · Chat"},
    ]

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

def refresh_models_bulk(app_url: str, app_name: str, *, max_workers:int=6) -> dict:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return {"count":0, "ok":0}
    directory = fetch_openrouter_directory(api_key)
    if not directory:
        return {"count":0, "ok":0}

    ok_cnt = 0
    now = datetime.now(timezone.utc)

    def worker(m):
        nonlocal ok_cnt
        ok, err = preflight_model(m["id"], app_url, app_name)
        if ok: ok_cnt += 1
        ModelCacheDAO.upsert(m["id"], m["name"], ok, err or "", now)

    if max_workers <= 1:
        for m in directory: worker(m)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            list(ex.map(worker, directory))

    return {"count": len(directory), "ok": ok_cnt}

# ---------------- 一次性/流式请求 ----------------
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

def stream_openrouter_messages(model_id: str, messages: List[Dict],
                               app_url: str | None = None,
                               app_name: str | None = None) -> Iterable[str]:
    """严格不接受 max_tokens —— 由提示词控制长度"""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 OPENROUTER_API_KEY 环境变量")
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
            if not raw: continue
            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if not line.startswith("data:"): continue
            data = line[5:].strip()
            if data == "[DONE]": break
            try:
                obj = json.loads(data)
                delta = obj["choices"][0]["delta"].get("content") or ""
                if delta: yield delta
            except Exception:
                continue

def stream_fake_messages(model: str, messages: List[Dict]) -> Iterable[str]:
    last = messages[-1]["content"] if messages else "开始发言。"
    text = f"（{model}）基于上下文：{last[:60]}…… 我方观点是：首先… 其次… 最后…"
    for ch in text:
        yield ch
        time.sleep(0.01)

def pick_streamer(model_id: str, app_url: str, app_name: str):
    prov = model_id.split("/", 1)[0]
    if prov == "fake":
        return lambda msgs: stream_fake_messages(model_id, msgs)
    else:
        return lambda msgs: stream_openrouter_messages(model_id, msgs, app_url=app_url, app_name=app_name)

# ---------------- 文本组织/提示词 ----------------
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

def build_messages_for_side(
    topic: str,
    preset_system: str,
    transcript: List[Dict],
    side_label: str,
    reply_style: str,
    *,
    max_ctx_tokens: int = 6000,
    keep_last_rounds: int = 2,
    opponent_preset: str = "",
    share_persona: bool = False
):
    """
    reply_style: short / medium / long -> 约束句数与字数
    share_persona: True 时将在 system 中追加“对手角色卡（参考）”
    """
    style = (reply_style or "medium").lower()
    if style == "short":
        sentence_hint, char_limit = "尽量 1-2 句", 90
    elif style == "long":
        sentence_hint, char_limit = "尽量 4-6 句", 260
    else:
        sentence_hint, char_limit = "尽量 2-4 句", 160

    system = (preset_system or "").strip()
    if not system:
        system = (f"你是{side_label}。围绕话题回答，回应要点清晰，引用对方观点进行论证或反驳；"
                  f"{sentence_hint}，严格≤{char_limit}字，避免长段。")

    # ★ 互知人设：把对手人设作为参考信息拼进 system（兼容各种提供商）
    if share_persona and opponent_preset:
        opp = opponent_preset.strip()
        if len(opp) > 220:
            opp = opp[:220] + "…"
        system += f"\n（对手角色卡【供参考】：{opp}）"

    # 最近 N 轮原文 + 早期摘要
    turns = [t for t in transcript if t["type"]=="turn"]
    recent_rounds = []
    if turns:
        max_round = max(t["round"] for t in turns)
        lo = max(1, max_round - keep_last_rounds + 1)
        recent_rounds = [t for t in turns if t["round"] >= lo]
    recent_text = join_turns(recent_rounds) if recent_rounds else ""
    earlier = [t for t in turns if t not in recent_rounds]
    summary_text = cheap_summarize(join_turns(earlier)) if earlier else ""

    def compose(summ, recent):
        blocks = []
        blocks.append(f"【话题】{topic}")
        if summ:   blocks.append(f"【既往摘要】{summ}")
        if recent: blocks.append(f"【最近几轮】\n{recent}")
        blocks.append(f"请给出你的回应（{sentence_hint}，≤{char_limit}字，直入要点，可举例）：")
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

def build_judge_messages(topic: str, transcript: List[Dict], *, final: bool=False, reply_style: str="medium"):
    if reply_style == "short":
        lim = 110
    elif reply_style == "long":
        lim = 220
    else:
        lim = 160

    if final:
        txt = join_turns([t for t in transcript if t["type"]=="turn"])
        sys = (f"你是专业裁判。请基于双方完整转录做客观判定："
               f"1）总结双方最有力观点 2）指出逻辑/证据问题 3）判定更优一方及理由。"
               f"严格≤{lim}字。")
        user = f"【话题】{topic}\n【双方发言】\n{txt}\n请给出最终裁决："
    else:
        last_round = max((t["round"] for t in transcript if t["type"]=="turn"), default=1)
        ab = [t for t in transcript if t["type"]=="turn" and t["round"]==last_round]
        ab_txt = "\n".join([f"[{t['side']}·第{t['round']}轮] {t['text']}" for t in ab])
        sys = (f"你是现场裁判。请给出简短点评：指出双方当轮亮点与瑕疵，保持专业；"
               f"严格≤{lim}字。")
        user = f"【话题】{topic}\n【当轮发言】\n{ab_txt}\n请给出裁判点评："
    return [{"role":"system","content":sys},{"role":"user","content":user}]

# ---------------- 预设扩写（可选模型） ----------------
@bp.post("/api/preset/expand")
def api_preset_expand():
    j = request.get_json(silent=True) or {}
    seed    = (j.get("seed") or "").strip()
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
        m = re.search(r"\{[\s\S]*\}", text)
        obj = {"A":"你是角色 A。简明扼要，偏事实论证。", "B":"你是角色 B。富有想象力，善于举例。"}
        if m:
            try: obj = json.loads(m.group(0))
            except Exception: pass
        return jsonify({"ok": True, "presetA": obj.get("A",""), "presetB": obj.get("B",""), "raw": text})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------------- 模型接口 ----------------
@bp.get("/api/models")
def api_models():
    """
    ?available=1  只返回可用；默认 1
    ?refresh=1    强制同步刷新（管理员）
    """
    only_available = (request.args.get("available","1").lower() in ("1","true","yes"))
    force_refresh  = (request.args.get("refresh","0").lower() in ("1","true","yes"))
    app_url  = os.getenv("APP_URL") or request.host_url.rstrip("/")
    app_name = os.getenv("APP_NAME", "AI Duel Arena")

    ttl_days = int(os.getenv("MODEL_CACHE_TTL_DAYS", "30"))
    lazy_bg  = os.getenv("MODEL_CACHE_LAZY_BG", "1").lower() in ("1","true","yes")

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

    if not rows or force_refresh:
        stat = refresh_models_bulk(app_url, app_name)
        rows = ModelCacheDAO.get_all()
        return jsonify({"ok": True, "models": rows_to_models(rows), "refreshed": True, "stat": stat})

    models = rows_to_models(rows)

    too_old = False
    if last:
        if last.tzinfo is None: last = last.replace(tzinfo=timezone.utc)
        too_old = (datetime.now(timezone.utc) - last) > timedelta(days=ttl_days)
    else:
        too_old = True

    if too_old and lazy_bg:
        try:
            threading.Thread(target=lambda: refresh_models_bulk(app_url, app_name), daemon=True).start()
        except Exception:
            pass

    age_days = None if not last else (datetime.now(timezone.utc)-last).days
    return jsonify({"ok": True, "models": models, "refreshed": False, "cache_age_days": age_days})

@bp.post("/api/models/refresh")
def api_models_refresh():
    token  = request.args.get("token") or request.headers.get("X-Refresh-Token")
    secret = os.getenv("MODEL_REFRESH_TOKEN")
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
    return jsonify({"ok": ok, "error": err or ""})

# ---------------- 主流程：流式对战 ----------------
@bp.post("/api/stream")
def api_stream():
    j = request.get_json(silent=True) or {}
    topic  = (j.get("topic") or "").strip()

    # 轮次上限（Config 控制）
    max_rounds_cfg = int(Config.GAME_FEATURES.get("ai_duel", {}).get("max_rounds", 10))
    rounds  = max(1, min(int(j.get("rounds") or 4), max_rounds_cfg))

    reply_style   = (j.get("reply_style") or "medium").lower()
    share_persona = bool(j.get("sharePersona", False))

    modelA  = j.get("modelA") or "fake/demo"
    modelB  = j.get("modelB") or "fake/demo"
    presetA = (j.get("presetA") or "").strip()
    presetB = (j.get("presetB") or "").strip()

    judge_on        = bool(j.get("judge", False))
    judge_per_round = bool(j.get("judgePerRound", True))
    judge_model     = (j.get("judgeModel") or "").strip() or ("fake/demo" if not judge_on else "openai/gpt-4o-mini")

    if not topic:
        return jsonify({"ok": False, "error": "NO_TOPIC"}), 400

    # 配额：一次开赛 = 1 次
    user_id, sid = _ids()
    ok, left = GameRuntime.can_play("ai_duel", user_id, sid, is_guest=(user_id is None))
    if not ok:
        return jsonify({"ok": False, "error": "DAILY_LIMIT", "left": left}), 429

    s = GameRuntime.session("ai_duel", user_id, sid, daily=True)
    GameRuntime.log("ai_duel", s["id"], user_id, "start",
                    {"topic": topic, "rounds": rounds, "modelA": modelA, "modelB": modelB},
                    bump=True)

    app_url  = os.getenv("APP_URL") or request.host_url.rstrip("/")
    app_name = os.getenv("APP_NAME", "AI Duel Arena")
    streamA  = pick_streamer(modelA, app_url, app_name)
    streamB  = pick_streamer(modelB, app_url, app_name)

    transcript: List[Dict] = []

    def gen():
        nonlocal presetA, presetB
        # 元信息（含互知人设/回复风格）
        yield json.dumps({"type":"meta","topic":topic,"rounds":rounds,
                          "A":modelA,"B":modelB,
                          "reply_style": reply_style,
                          "sharePersona": share_persona,
                          "judge": judge_on, "judgePerRound": judge_per_round, "judgeModel": judge_model},
                         ensure_ascii=False) + "\n"

        # 预检兜底（前端可关，这里仍保证健壮性）
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

        streamJ = (lambda msgs: stream_fake_messages(judge_model, msgs)) if judge_model.startswith("fake/") \
                  else (lambda msgs: stream_openrouter_messages(judge_model, msgs, app_url=app_url, app_name=app_name))

        # 对战循环
        for r in range(1, rounds+1):
            # A 发言
            msgsA = build_messages_for_side(
                topic, presetA, transcript, side_label="A方", reply_style=reply_style,
                max_ctx_tokens=6000, keep_last_rounds=2,
                opponent_preset=presetB, share_persona=share_persona
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

            # B 发言
            msgsB = build_messages_for_side(
                topic, presetB, transcript, side_label="B方", reply_style=reply_style,
                max_ctx_tokens=6000, keep_last_rounds=2,
                opponent_preset=presetA, share_persona=share_persona
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
                    msgsJ = build_judge_messages(topic, transcript, final=False, reply_style=reply_style)
                    accj = []
                    for delta in streamJ(msgsJ):
                        accj.append(delta)
                        yield json.dumps({"type":"judge_chunk","round":r,"delta":delta}, ensure_ascii=False) + "\n"
                    fullJ = "".join(accj).strip()
                    yield json.dumps({"type":"judge_turn","round":r,"text":fullJ}, ensure_ascii=False) + "\n"
                except Exception as e:
                    yield json.dumps({"type":"error","who":"judge","round":r,"message":str(e)}, ensure_ascii=False) + "\n"

        # 终局裁判
        if judge_on and not judge_per_round:
            try:
                msgsJF = build_judge_messages(topic, transcript, final=True, reply_style=reply_style)
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

# ---------------- 配额/心跳 ----------------
@bp.get("/api/quota")
def api_quota():
    user_id, sid = _ids()
    ok, left = GameRuntime.can_play("ai_duel", user_id, sid, is_guest=(user_id is None))
    limits = Config.GAME_FEATURES.get("ai_duel", {})
    limit  = limits.get('daily_limit_user' if user_id else 'daily_limit_guest', 5)
    return jsonify({"ok": True, "left": left, "limit": limit})

@bp.post("/track")
def track():
    _ = request.get_json(silent=True) or {}
    return ("", 204)

def get_blueprint():
    return bp
