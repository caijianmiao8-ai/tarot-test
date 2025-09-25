from flask import Blueprint, render_template, request, jsonify, g, make_response
from itsdangerous import URLSafeSerializer
from datetime import date
import hmac, hashlib, os, secrets, json

SLUG = "guess_number"

def get_meta():
    return {
        "slug": SLUG,
        "title": "猜数字",
        "subtitle": "后端有状态 · 可极快模式",
        "path": f"/g/{SLUG}/",
        "tags": ["Demo","FastPath"]
    }

bp = Blueprint(
    SLUG, __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",
)

# —— 配置开关 ——
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
COOKIE_SECURE = os.getenv("COOKIE_SECURE","0").lower() in ("1","true","yes")
HARD_GATE_AT_START = os.getenv("HARD_GATE_AT_START","0").lower() in ("1","true","yes")  # 需要严格配额就开
SER = URLSafeSerializer(SECRET_KEY, salt=f"{SLUG}-state")  # 签名 cookie 的序列化器

def _ensure_sid(resp):
    if request.cookies.get("sid"):
        return resp
    sid = secrets.token_hex(16)
    resp.set_cookie("sid", sid, max_age=60*60*24*730, httponly=True, samesite="Lax", secure=COOKIE_SECURE)
    return resp

def _today(): return date.today().isoformat()

def _secret_for(day, sid, user_id=None):
    """纯计算 secret：同一天+同身份固定，**不落库**"""
    msg = f"{day}:{sid or ''}:{user_id or ''}:{SLUG}".encode()
    digest = hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).digest()
    return (int.from_bytes(digest[:4], "big") % 100) + 1

def _ids():
    user_id = (getattr(g, "user", {}) or {}).get("id")
    sid = request.cookies.get("sid")
    return user_id, sid

def _load_state():
    """从签名 cookie 读取 {d:day, t:tries}；跨天或验签失败即重置"""
    raw = request.cookies.get(f"{SLUG}_state")
    if not raw: return {"d": _today(), "t": 0}
    try:
        st = SER.loads(raw)
        if st.get("d") != _today():
            return {"d": _today(), "t": 0}
        st["t"] = int(st.get("t", 0))
        return st
    except Exception:
        return {"d": _today(), "t": 0}

def _save_state(resp, st):
    resp.set_cookie(f"{SLUG}_state", SER.dumps(st), max_age=60*60*24, httponly=True, samesite="Lax", secure=COOKIE_SECURE)
    return resp

@bp.get("/")
@bp.get("")
def page():
    resp = make_response(render_template(f"games/{SLUG}/index.html"))
    return _ensure_sid(resp)

# —— 可选“硬闸”：需要严格配额时才查库 —— 
@bp.post("/api/start")
def api_start():
    if HARD_GATE_AT_START:
        # 严格配额：只在 start 做一次 DB 检查（示意）
        try:
            from core.runtime import GameRuntime
            user_id, sid = _ids()
            ok, left = GameRuntime.can_play(SLUG, user_id, sid, is_guest=(user_id is None))
            if not ok:
                return jsonify({"ok": False, "error": "DAILY_LIMIT", "left": left}), 429
        except Exception:
            pass  # 检查失败也不阻断体验（按需改）

    # 初始化本地 state（t=0），不清空前端日志
    st = {"d": _today(), "t": 0}
    resp = jsonify({"ok": True})
    _save_state(resp, st)
    return _ensure_sid(resp)

# —— 热路径：不查库，纯计算 & 签名 cookie 记次，毫秒级返回 —— 
@bp.post("/api/guess")
def api_guess():
    # 解析 JSON 或 表单
    data = request.get_json(silent=True) or {}
    raw = str(data.get("n")) if "n" in data else (request.form.get("n") or "").strip()
    try:
        n = int(raw)
    except Exception:
        return jsonify({"ok": False, "error": "BAD_INPUT"}), 400
    if not (1 <= n <= 100):
        return jsonify({"ok": False, "error": "BAD_INPUT_RANGE"}), 400

    user_id, sid = _ids()
    day = _today()
    secret = _secret_for(day, sid, user_id)

    st = _load_state()
    st["t"] = int(st.get("t", 0)) + 1

    res = "equal" if n == secret else ("low" if n < secret else "high")
    payload = {"ok": True, "result": res, "tries": st["t"]}

    # 立即返回给用户
    resp = jsonify(payload)
    _save_state(resp, st)           # 回写签名 cookie（不阻塞）
    return _ensure_sid(resp)

# —— 冷路径：前端 sendBeacon 上报日志/用量；尽量快处理/可丢弃 —— 
@bp.post("/track")
def track():
    try:
        j = request.get_json(silent=True) or {}
        # 你可以在这里快速写库/入队；失败就忽略，不影响体验
        # 示例：只接受很小的一条数据，避免大 JSON
        evt = {
            "game": SLUG,
            "at": _today(),
            "res": j.get("res"),
            "tries": int(j.get("tries", 0)),
        }
        # 写库（可选）：建议用连接池+极短事务（略）
        # from core.runtime import GameRuntime
        # GameRuntime.log(...)/GameUsageDAO.bump(...) —— 可按需封装为 batch
    except Exception:
        pass
    return ("", 204)  # 不要让前端等

def get_blueprint():
    return bp
