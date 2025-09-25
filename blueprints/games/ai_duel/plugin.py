# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, Response, jsonify, make_response
import os, json, secrets, time, requests
from itsdangerous import URLSafeSerializer
from typing import Iterable, List, Dict

SLUG = "ai_duel"

def get_meta():
    return {
        "slug": SLUG,
        "title": "AI 斗蛐蛐",
        "subtitle": "选命题 + 选2模型，实时辩论流",
        "path": f"/g/{SLUG}/",
        "tags": ["LLM","Debate","Streaming"]
    }

bp = Blueprint(
    SLUG, __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",
)

# —— 轻身份：仅用于 cookie，不查库 ——
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

@bp.get("/api/models")
def api_models():
    # 这里列出常用 OpenRouter 模型；你可继续添加
    # 名称写法遵循 openrouter 的 "provider/model" 形式
    models = [
        {"id": "openai/gpt-4o-mini",           "name": "OpenAI · GPT-4o-mini"},
        {"id": "openai/gpt-4o",                "name": "OpenAI · GPT-4o"},
        {"id": "anthropic/claude-3.5-sonnet",  "name": "Anthropic · Claude 3.5 Sonnet"},
        {"id": "google/gemini-1.5-pro",        "name": "Google · Gemini 1.5 Pro"},
        {"id": "qwen/qwen-2.5-72b-instruct",   "name": "Qwen · 2.5-72B Instruct"},
        {"id": "meta-llama/llama-3.1-70b-instruct", "name": "Llama · 3.1-70B Instruct"},
        {"id": "deepseek/deepseek-chat",       "name": "DeepSeek · Chat"},
        {"id": "fake/demo",                    "name": "内置演示（无 Key）"},
    ]
    return jsonify({"ok": True, "models": models})

# ------------------ 上下文与摘要 ------------------

def est_tokens(text: str) -> int:
    # 粗估 token：足够用于预算控制
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
            stops = [line.find(p) for p in ("。",".","!","?") if line.find(p) != -1]
            cut = (min(stops) + 1) if stops else min(120, len(line))
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

    # 最近 N 轮原文
    recent_rounds = []
    if transcript:
        max_round = max(t["round"] for t in transcript if t["side"] in ("A","B"))
        lo = max(1, max_round - keep_last_rounds + 1)
        recent_rounds = [t for t in transcript if t["round"] >= lo and t["side"] in ("A","B")]
    recent_text = join_turns(recent_rounds) if recent_rounds else ""

    # 更早历史摘要
    earlier = [t for t in transcript if t not in recent_rounds and t["side"] in ("A","B")]
    summary_text = cheap_summarize(join_turns(earlier)) if earlier else ""

    next_round = (transcript[-1]["round"] if transcript else 0) + (1 if (not transcript or transcript[-1]["side"]=="B") else 0)

    def compose(summary_txt, recent_txt):
        blocks = []
        if summary_txt: blocks.append(f"【既往摘要】\n{summary_txt}")
        if recent_txt:  blocks.append(f"【最近几轮】\n{recent_txt}")
        blocks.append(f"请给出你的第 {next_round} 轮回应：")
        return "\n\n".join(blocks)

    user = compose(summary_text, recent_text)
    budget = max_ctx_tokens - (est_tokens(system) + 300)  # 给生成留余量

    # 先减 recent 轮数
    k = keep_last_rounds
    while est_tokens(user) > budget and k > 0:
        k -= 1
        if transcript:
            max_round = max(t["round"] for t in transcript if t["side"] in ("A","B"))
            lo = max(1, max_round - k + 1)
            recent_rounds = [t for t in transcript if t["round"] >= lo and t["side"] in ("A","B")]
            recent_text = join_turns(recent_rounds) if recent_rounds else ""
        user = compose(summary_text, recent_text)
    # 再缩摘要
    while est_tokens(user) > budget and summary_text:
        summary_text = summary_text[: max(50, len(summary_text)-200)]
        user = compose(summary_text, recent_text)

    messages = [
        {"role":"system","content":system},
        {"role":"user","content":user},
    ]
    return messages

# ------------------ OpenRouter 流式 ------------------

def stream_openrouter_messages(model_id: str, messages: List[Dict]) -> Iterable[str]:
    """
    直连 OpenRouter /v1/chat/completions，逐 token 产出 delta.content
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 OPENROUTER_API_KEY 环境变量")

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # 以下两个非必须，但官方建议加上
        "HTTP-Referer": os.getenv("APP_URL", request.host_url.rstrip("/")),
        "X-Title": os.getenv("APP_NAME", "AI Duel Arena"),
    }
    payload = {
        "model": model_id,       # 例如 "anthropic/claude-3.5-sonnet"
        "messages": messages,    # OpenAI/Anthropic 兼容格式
        "temperature": 0.7,
        "stream": True,
    }
    with requests.post(url, headers=headers, json=payload, stream=True, timeout=600) as r:
        r.raise_for_status()
        for raw in r.iter_lines(decode_unicode=True):
            if not raw: 
                continue
            if raw.startswith("data:"):
                data = raw[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    # 与 OpenAI 一致：choices[0].delta.content
                    delta = obj["choices"][0]["delta"].get("content") or ""
                    if delta:
                        yield delta
                except Exception:
                    continue

def stream_fake_messages(model: str, messages: List[Dict]) -> Iterable[str]:
    # 演示用：无 Key 也可预览 UI 效果
    last = messages[-1]["content"] if messages else "开始发言。"
    text = f"（{model}）基于当前上下文：{last[:80]}…… 我的回应是：首先… 其次… 最后…"
    for ch in text:
        yield ch
        time.sleep(0.012)

def pick_streamer(model_id: str):
    prov = model_id.split("/", 1)[0]
    if prov == "fake":
        return lambda msgs: stream_fake_messages(model_id, msgs)
    else:
        return lambda msgs: stream_openrouter_messages(model_id, msgs)

# ------------------ 主对战：NDJSON 流 ------------------

@bp.post("/api/stream")
def api_stream():
    """
    请求 JSON：
      topic, rounds, modelA, modelB, stanceA, stanceB, judge
    返回 NDJSON 流：
      meta / chunk / turn / judge / end / error
    """
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

    streamA = pick_streamer(modelA)
    streamB = pick_streamer(modelB)

    transcript: List[Dict] = []

    def gen():
        # 头信息
        yield json.dumps({"type":"meta","topic":topic,"rounds":rounds,
                          "A":modelA,"B":modelB,"stanceA":stanceA,"stanceB":stanceB}, ensure_ascii=False) + "\n"
        # 逐回合：A 先手
        for r in range(1, rounds+1):
            # A 回合（流式）
            msgsA = build_messages_for_side(topic, stanceA, transcript, side="A",
                                            max_ctx_tokens=6000, keep_last_rounds=2)
            acc = []
            try:
                for delta in streamA(msgsA):
                    acc.append(delta)
                    yield json.dumps({"type":"chunk","side":"A","round":r,"delta":delta}, ensure_ascii=False) + "\n"
            except Exception as e:
                yield json.dumps({"type":"error","side":"A","round":r,"message":str(e)}) + "\n"
                break
            fullA = "".join(acc).strip()
            transcript.append({"side":"A","round":r,"text":fullA})
            yield json.dumps({"type":"turn","side":"A","round":r,"text":fullA}, ensure_ascii=False) + "\n"

            # B 回合（流式）
            msgsB = build_messages_for_side(topic, stanceB, transcript, side="B",
                                            max_ctx_tokens=6000, keep_last_rounds=2)
            acc = []
            try:
                for delta in streamB(msgsB):
                    acc.append(delta)
                    yield json.dumps({"type":"chunk","side":"B","round":r,"delta":delta}, ensure_ascii=False) + "\n"
            except Exception as e:
                yield json.dumps({"type":"error","side":"B","round":r,"message":str(e)}) + "\n"
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
    return Response(gen(), headers=headers)

# 可选：冷路径上报统计（不阻塞 UI）
@bp.post("/track")
def track():
    _ = request.get_json(silent=True) or {}
    return ("", 204)

def get_blueprint():
    return bp
