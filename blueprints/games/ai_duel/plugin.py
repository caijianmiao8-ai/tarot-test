# blueprints/games/ai_duel/plugin.py
from flask import Blueprint, render_template, request, Response, jsonify, make_response
from flask import g
from itsdangerous import URLSafeSerializer
import os, json, time, secrets
from datetime import date

SLUG = "ai_duel"

def get_meta():
    return {
        "slug": SLUG,
        "title": "AI 斗蛐蛐",
        "subtitle": "选命题 + 选 2 个模型，自动辩论",
        "path": f"/g/{SLUG}/",
        "tags": ["LLM","Debate","Streaming"]
    }

bp = Blueprint(
    SLUG, __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",
)

# —— 轻身份（仅为前端体验），不查库 ——
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
COOKIE_SECURE = os.getenv("COOKIE_SECURE","0").lower() in ("1","true","yes")
SER = URLSafeSerializer(SECRET_KEY, salt=f"{SLUG}-state")

def _ensure_sid(resp):
    if request.cookies.get("sid"): return resp
    sid = secrets.token_hex(16)
    resp.set_cookie("sid", sid, max_age=60*60*24*730, httponly=True, samesite="Lax", secure=COOKIE_SECURE)
    return resp

@bp.get("/")
@bp.get("")
def page():
    resp = make_response(render_template(f"games/{SLUG}/index.html"))
    return _ensure_sid(resp)

# —— 模型列表（前端下拉）—— 你可以改成从配置/环境读取
@bp.get("/api/models")
def api_models():
    return jsonify({
        "ok": True,
        "models": [
            {"id": "openai:gpt-4o-mini", "name": "OpenAI · GPT-4o-mini"},
            {"id": "openai:gpt-4o",       "name": "OpenAI · GPT-4o"},
            {"id": "anthropic:claude-3-5-sonnet", "name": "Anthropic · Claude 3.5 Sonnet"},
            {"id": "dify:debate-agent-a", "name": "Dify · Agent A（示例）"},
            {"id": "dify:debate-agent-b", "name": "Dify · Agent B（示例）"},
        ]
    })

# —— 核心：流式对战，一次请求内 orchestrate 两边交替 —— #
def _fake_llm_turn(side, model_id, topic, stance, history_text):
    """
    占位的“模型调用”：你把这里替换成真实 LLM 调用即可。
    - 入参：对方历史文本、当前立场、题目等
    - 出参：本轮整段话（字符串）
    """
    # 这里先返回一个假答案，并 sleep 模拟生成时延
    time.sleep(0.2)
    return f"（{stance} · {model_id}）针对『{topic[:60]}...』的观点：{('我同意' if side=='A' else '我不同意')}，理由是……（基于对方发言长度 {len(history_text)}）"

def _call_model(model_id: str, messages: list[str], system_prompt: str) -> str:
    """
    真实 LLM 的统一入口（你可以接 Dify / OpenAI / Anthropic）
    这里先简化：把 messages 拼成 history_text 交给 _fake_llm_turn
    """
    # TODO: 替换成你实际的 LLM 客户端；messages 是整段上下文
    return "\n".join(messages[-2:])  # 仅示例

@bp.post("/api/stream")
def api_stream():
    """
    请求体 JSON：
    {
      "topic": "AI 应否开源？",
      "rounds": 4,
      "modelA": "openai:gpt-4o-mini",
      "modelB": "anthropic:claude-3-5-sonnet",
      "stanceA": "正方", "stanceB": "反方",
      "judge": false   // 可选，是否最后请第三模型判胜
    }
    返回：NDJSON 流（每行一个 JSON：{"type": "...", ...}）
    """
    data = request.get_json(silent=True) or {}
    topic   = (data.get("topic") or "").strip()
    rounds  = max(1, min(int(data.get("rounds") or 4), 12))
    modelA  = data.get("modelA") or "openai:gpt-4o-mini"
    modelB  = data.get("modelB") or "anthropic:claude-3-5-sonnet"
    stanceA = (data.get("stanceA") or "正方").strip()
    stanceB = (data.get("stanceB") or "反方").strip()
    do_judge= bool(data.get("judge"))

    if not topic:
        return jsonify({"ok": False, "error": "NO_TOPIC"}), 400

    # —— 一次请求内的本地状态（无 DB）——
    msgA, msgB = [], []   # 各自收到的"可见历史文本"
    transcript = []       # 整场记录（方便最后上报）
    sid = request.cookies.get("sid") or ""

    def gen():
        # 头部：基本信息
        yield json.dumps({"type":"meta","topic":topic,"rounds":rounds,"A":modelA,"B":modelB,"stanceA":stanceA,"stanceB":stanceB}) + "\n"

        # 轮换发言：A 先手
        last_text = ""
        for r in range(1, rounds+1):
            # A 发言
            a_text = _fake_llm_turn("A", modelA, topic, stanceA, last_text)
            transcript.append({"side":"A","round":r,"text":a_text})
            msgA.append(a_text); msgB.append(a_text)  # 双方都能看到对方发言
            yield json.dumps({"type":"turn","side":"A","round":r,"text":a_text}) + "\n"

            # B 发言
            b_text = _fake_llm_turn("B", modelB, topic, stanceB, a_text)
            transcript.append({"side":"B","round":r,"text":b_text})
            msgA.append(b_text); msgB.append(b_text)
            yield json.dumps({"type":"turn","side":"B","round":r,"text":b_text}) + "\n"

            last_text = b_text

        # 可选：让“裁判模型”来个总结/判胜（此处先占位）
        if do_judge:
            judge_text = f"基于以上 {rounds*2} 次交锋，判定『（示例）A 小胜』，理由：……"
            yield json.dumps({"type":"judge","text":judge_text}) + "\n"
            transcript.append({"side":"JUDGE","round":0,"text":judge_text})

        # 尾部：收场 + 前端可异步上报
        yield json.dumps({"type":"end"}) + "\n"

    # NDJSON 流（比 SSE 更容易前端处理）
    headers = {"Content-Type": "application/x-ndjson; charset=utf-8", "Cache-Control": "no-cache"}
    return Response(gen(), headers=headers)

# —— 冷路径：异步上报（不阻塞 UI）——
@bp.post("/track")
def track():
    # 允许前端 sendBeacon 上报 {"topic":..., "models": {...}, "transcript":[...]}
    # 你可以在这里用连接池快速落库；失败直接 204 返回，不影响体验
    _ = request.get_json(silent=True) or {}
    return ("", 204)

def get_blueprint():
    return bp
