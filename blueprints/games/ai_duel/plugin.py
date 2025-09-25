# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, Response, jsonify, make_response, stream_with_context
import os, json, secrets, time, requests
from itsdangerous import URLSafeSerializer
from typing import Iterable, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

SLUG = "ai_duel"

def get_meta():
    return {
        "slug": SLUG,
        "title": "AI 斗蛐蛐",
        "subtitle": "选命题 + 选2模型，实时辩论流（OpenRouter）",
        "path": f"/g/{SLUG}/",
        "tags": ["LLM","Debate","Streaming"]
    }

bp = Blueprint(
    SLUG, __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",
)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
COOKIE_SECURE = os.getenv("COOKIE_SECURE","0").lower() in ("1","true","yes")
SER = URLSafeSerializer(SECRET_KEY, salt=f"{SLUG}-state")

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

# =========================
#   模型目录 + 可用性预检
# =========================
_MODEL_OK_CACHE: dict[str, float] = {}  # {model_id: expire_ts}
_MODEL_TTL_SEC = 600                    # 10 分钟缓存

def preflight_model(model_id: str, app_url: str, app_name: str) -> tuple[bool, str]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return False, "缺少 OPENROUTER_API_KEY"
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": app_url,
        "X-Title": app_name,
    }
    payload = {
        "model": model_id,
        "messages": [{"role":"user","content":"ping"}],
        "max_tokens": 1,
        "stream": False
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
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

def _model_ok(model_id: str, app_url: str, app_name: str) -> bool:
    now = time.time()
    exp = _MODEL_OK_CACHE.get(model_id)
    if exp and exp > now:
        return True
    ok, _ = preflight_model(model_id, app_url, app_name)
    if ok:
        _MODEL_OK_CACHE[model_id] = now + _MODEL_TTL_SEC
    return ok

@bp.get("/api/models")
def api_models():
    """
    ?available=1 仅返回“当前 Key 真可用”的模型（并发预检 + 缓存）
    ?available=0 返回全量目录（不预检） —— 推荐前端用这条再逐个检查并显示进度
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    app_url  = os.getenv("APP_URL") or request.host_url.rstrip("/")
    app_name = os.getenv("APP_NAME", "AI Duel Arena")
    only_available = (request.args.get("available","1").lower() in ("1","true","yes"))

    models: List[Dict] = []

    # 1) 动态拉取目录
    if api_key:
        try:
            r = requests.get("https://openrouter.ai/api/v1/models",
                             headers={"Authorization": f"Bearer {api_key}"},
                             timeout=20)
            if r.ok:
                data = (r.json() or {}).get("data", [])
                for m in data:
                    mid = m.get("id")
                    if not mid: 
                        continue
                    name = m.get("name") or mid
                    models.append({"id": mid, "name": name})
        except Exception:
            pass

    # 2) 回退静态（动态失败时）
    if not models:
        models = [
            {"id": "openai/gpt-4o-mini",                 "name": "OpenAI · GPT-4o-mini"},
            {"id": "anthropic/claude-3.5-sonnet",        "name": "Anthropic · Claude 3.5 Sonnet"},
            {"id": "meta-llama/llama-3.1-70b-instruct",  "name": "Llama · 3.1-70B Instruct"},
            {"id": "qwen/qwen-2.5-72b-instruct",         "name": "Qwen · 2.5-72B Instruct"},
            {"id": "google/gemini-1.5-pro",              "name": "Google · Gemini 1.5 Pro"},
            {"id": "deepseek/deepseek-chat",             "name": "DeepSeek · Chat"},
        ]

    # 3) 只保留“可用”（后端一把筛的旧逻辑，保留给可选场景）
    if only_available and models:
        filtered: List[Dict] = []
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = {ex.submit(_model_ok, m["id"], app_url, app_name): m for m in models}
            for fut in as_completed(futs):
                m = futs[fut]
                try:
                    if fut.result():
                        filtered.append(m)
                except Exception:
                    pass
        models = filtered

    # 4) 排序 + 兜底演示项
    models.sort(key=lambda x: x["name"].lower())
    models.append({"id": "fake/demo", "name": "内置演示（无 Key）"})

    return jsonify({"ok": True, "models": models})

@bp.post("/api/models/check")
def api_models_check():
    """单个模型预检（供前端并发调用以显示进度）"""
    j = request.get_json(silent=True) or {}
    model_id = (j.get("id") or "").strip()
    if not model_id:
        return jsonify({"ok": False, "error": "NO_ID"}), 400
    app_url  = os.getenv("APP_URL") or request.host_url.rstrip("/")
    app_name = os.getenv("APP_NAME", "AI Duel Arena")
    ok, err = preflight_model(model_id, app_url, app_name)
    if ok:
        _MODEL_OK_CACHE[model_id] = time.time() + _MODEL_TTL_SEC
    return jsonify({"ok": ok, "error": err or ""})

# =========================
#      上下文与摘要
# =========================
def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def join_turns(transcript: List[Dict]) -> str:
    lines = []
    for t in transcript:
        tag = "A方" if t["side"]=="A" else ("B方" if t["side"]=="B" else "裁判")
        lines.append(f"[{tag}·第{t['round']}轮] {t['text']}")
    return "\n".join(lines)

def cheap_summarize(text: str, max_chars: int = 600) -> str:
    if not text: return ""
    s = []
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        if any(k in line for k in ("因此","所以","综上","因而","结果")):
            s.append(line[:200])
        else:
            stops = [p for p in (".","。","!","?") if p in line]
            cut_positions = [line.find(p) for p in stops if line.find(p) != -1]
            cut = min(cut_positions) + 1 if cut_positions else min(120, len(line))
            s.append(line[:cut])
        if sum(len(x) for x in s) > max_chars: break
    out = "；".join(s)
    return (out[:max_chars] + "…") if len(out) > max_chars else out

def build_messages_for_side(topic: str, stance: str, transcript: List[Dict],
                            side: str, *, max_ctx_tokens: int = 6000, keep_last_rounds: int = 2):
    system = (
        f"你是辩论选手{side}，立场：{stance}。题目：「{topic}」。"
        "规则：每轮≤150字；引用对方上一轮关键点进行论证或反驳；给出具体例证或推理；保持礼貌，不复述题面。"
    )
    recent_rounds = []
    if transcript:
        max_round = max(t["round"] for t in transcript if t["side"] in ("A","B"))
        lo = max(1, max_round - keep_last_rounds + 1)
        recent_rounds = [t for t in transcript if t["round"] >= lo and t["side"] in ("A","B")]
    recent_text = join_turns(recent_rounds) if recent_rounds else ""
    earlier = [t for t in transcript if t not in recent_rounds and t["side"] in ("A","B")]
    summary_text = cheap_summarize(join_turns(earlier)) if earlier else ""
    next_round = (transcript[-1]["round"] if transcript else 0) + (1 if (not transcript or transcript[-1]["side"]=="B") else 0)

    def compose(summ, recent):
        blocks = []
        if summ:   blocks.append(f"【既往摘要】\n{summ}")
        if recent: blocks.append(f"【最近几轮】\n{recent}")
        blocks.append(f"请给出你的第 {next_round} 轮回应：")
        return "\n\n".join(blocks)

    user = compose(summary_text, recent_text)
    budget = max_ctx_tokens - (est_tokens(system) + 300)
    k = keep_last_rounds
    while est_tokens(user) > budget and k > 0:
        k -= 1
        if transcript:
            max_round = max(t["round"] for t in transcript if t["side"] in ("A","B"))
            lo = max(1, max_round - k + 1)
            recent_rounds = [t for t in transcript if t["round"] >= lo and t["side"] in ("A","B")]
            recent_text = join_turns(recent_rounds) if recent_rounds else ""
        user = compose(summary_text, recent_text)
    while est_tokens(user) > budget and summary_text:
        summary_text = summary_text[: max(50, len(summary_text)-200)]
        user = compose(summary_text, recent_text)

    return [
        {"role":"system","content":system},
        {"role":"user","content":user},
    ]

# =========================
#     OpenRouter 流式
# =========================
def stream_openrouter_messages(model_id: str, messages: List[Dict],
                               app_url: str | None = None,
                               app_name: str | None = None) -> Iterable[str]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 OPENROUTER_API_KEY 环境变量")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if app_url:  headers["HTTP-Referer"] = app_url
    if app_name: headers["X-Title"]      = app_name

    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.7,
        "stream": True,
    }

    with requests.post(url, headers=headers, json=payload, stream=True, timeout=600) as r:
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
                delta = obj["choices"][0]["delta"].get("content") or ""
                if delta:
                    yield delta
            except Exception:
                continue

def stream_fake_messages(model: str, messages: List[Dict]) -> Iterable[str]:
    last = messages[-1]["content"] if messages else "开始发言。"
    text = f"（{model}）基于当前上下文：{last[:80]}…… 我的回应是：首先… 其次… 最后…"
    for ch in text:
        yield ch
        time.sleep(0.012)

def pick_streamer(model_id: str, app_url: str, app_name: str):
    prov = model_id.split("/", 1)[0]
    if prov == "fake":
        return lambda msgs: stream_fake_messages(model_id, msgs)
    else:
        return lambda msgs: stream_openrouter_messages(model_id, msgs, app_url=app_url, app_name=app_name)

# =========================
#         对战主流程
# =========================
@bp.post("/api/stream")
def api_stream():
    j = request.get_json(silent=True) or {}
    topic   = (j.get("topic") or "").strip()
    rounds  = max(1, min(int(j.get("rounds") or 4), 12))
    modelA  = j.get("modelA") or "fake/demo"
    modelB  = j.get("modelB") or "fake/demo"
    stanceA = (j.get("stanceA") or "正方").strip()
    stanceB = (j.get("stanceB") or "反方").strip()
    do_judge= bool(j.get("judge"))
    if not topic:
        return jsonify({"ok": False, "error": "NO_TOPIC"}), 400

    app_url  = os.getenv("APP_URL") or request.host_url.rstrip("/")
    app_name = os.getenv("APP_NAME", "AI Duel Arena")

    streamA = pick_streamer(modelA, app_url, app_name)
    streamB = pick_streamer(modelB, app_url, app_name)

    transcript: List[Dict] = []

    def gen():
        yield json.dumps({"type":"meta","topic":topic,"rounds":rounds,
                          "A":modelA,"B":modelB,"stanceA":stanceA,"stanceB":stanceB}, ensure_ascii=False) + "\n"

        # 开局预检（快速失败）
        okA, errA = preflight_model(modelA, app_url, app_name)
        okB, errB = preflight_model(modelB, app_url, app_name)
        if not okA:
            yield json.dumps({"type":"error","side":"A","round":1,"message":errA}, ensure_ascii=False) + "\n"
        if not okB:
            yield json.dumps({"type":"error","side":"B","round":1,"message":errB}, ensure_ascii=False) + "\n"
        if (not okA) or (not okB):
            yield json.dumps({"type":"end"}) + "\n"
            return

        for r in range(1, rounds+1):
            msgsA = build_messages_for_side(topic, stanceA, transcript, side="A",
                                            max_ctx_tokens=6000, keep_last_rounds=2)
            acc = []
            try:
                for delta in streamA(msgsA):
                    acc.append(delta)
                    yield json.dumps({"type":"chunk","side":"A","round":r,"delta":delta}, ensure_ascii=False) + "\n"
            except Exception as e:
                yield json.dumps({"type":"error","side":"A","round":r,"message":str(e)}, ensure_ascii=False) + "\n"
                break
            fullA = "".join(acc).strip()
            transcript.append({"side":"A","round":r,"text":fullA})
            yield json.dumps({"type":"turn","side":"A","round":r,"text":fullA}, ensure_ascii=False) + "\n"

            msgsB = build_messages_for_side(topic, stanceB, transcript, side="B",
                                            max_ctx_tokens=6000, keep_last_rounds=2)
            acc = []
            try:
                for delta in streamB(msgsB):
                    acc.append(delta)
                    yield json.dumps({"type":"chunk","side":"B","round":r,"delta":delta}, ensure_ascii=False) + "\n"
            except Exception as e:
                yield json.dumps({"type":"error","side":"B","round":r,"message":str(e)}, ensure_ascii=False) + "\n"
                break
            fullB = "".join(acc).strip()
            transcript.append({"side":"B","round":r,"text":fullB})
            yield json.dumps({"type":"turn","side":"B","round":r,"text":fullB}, ensure_ascii=False) + "\n"

        if do_judge:
            judge_text = "（示例裁判）基于以上发言，A 略胜；双方可进一步提供数据支持。"
            yield json.dumps({"type":"judge","text":judge_text}, ensure_ascii=False) + "\n"

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

def get_blueprint():
    return bp
