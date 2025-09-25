from flask import Blueprint, render_template, request, jsonify, g, make_response
from core.runtime import GameRuntime
import random, secrets, os

SLUG = "guess_number"

bp = Blueprint(
    SLUG, __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",
)

# 本地开发 http 建议保持 False；上线 https 配置环境变量 COOKIE_SECURE=1
SECURE_COOKIE = os.getenv("COOKIE_SECURE", "0").lower() in ("1", "true", "yes")

def _ids():
    """登录用户用 user_id；游客用 sid"""
    user_id = (getattr(g, "user", {}) or {}).get("id")
    sid = request.cookies.get("sid")
    return user_id, sid

def _ensure_sid(resp):
    """游客没有 sid 时发一个"""
    if request.cookies.get("sid"):
        return resp
    sid = secrets.token_hex(16)
    resp.set_cookie(
        "sid", sid,
        max_age=60 * 60 * 24 * 730,  # 2 years
        httponly=True,
        samesite="Lax",
        secure=SECURE_COOKIE,        # 本地 http 请保持 False
    )
    return resp

@bp.get("/")
def page():
    resp = make_response(render_template(f"games/{SLUG}/index.html"))
    return _ensure_sid(resp)

# 兜底：如果将来有非“简单请求”的 header，预检也能秒回
@bp.route("/api/guess", methods=["OPTIONS"])
def api_guess_options():
    return ("", 204)

@bp.post("/api/start")
def api_start():
    user_id, sid = _ids()
    ok, left = GameRuntime.can_play(SLUG, user_id, sid, is_guest=(user_id is None))
    if not ok:
        return jsonify({"ok": False, "error": "DAILY_LIMIT", "left": left}), 429

    s = GameRuntime.session(SLUG, user_id, sid, daily=True)
    GameRuntime.patch_state(s["id"], {"secret": random.randint(1, 100), "tries": 0})
    GameRuntime.log(SLUG, s["id"], user_id, "start", {"init": True})
    return _ensure_sid(jsonify({"ok": True}))

def _parse_n():
    """兼容 JSON 与表单两种入参"""
    data = request.get_json(silent=True)
    if data and "n" in data:
        raw = str(data.get("n"))
    else:
        raw = request.form.get("n", "")
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return None, "BAD_INPUT"

@bp.post("/api/guess")
def api_guess():
    user_id, sid = _ids()

    # 防止绕过 /api/start 暴力猜
    ok, left = GameRuntime.can_play(SLUG, user_id, sid, is_guest=(user_id is None))
    if not ok:
        return jsonify({"ok": False, "error": "DAILY_LIMIT", "left": left}), 429

    s = GameRuntime.session(SLUG, user_id, sid, daily=True)
    st = (s.get("state") or {})

    # 没 start 也能自动开一局
    if "secret" not in st:
        GameRuntime.patch_state(s["id"], {"secret": random.randint(1, 100), "tries": 0})
        s = GameRuntime.session(SLUG, user_id, sid, daily=True)
        st = (s.get("state") or {})

    n, err = _parse_n()
    if err:
        return jsonify({"ok": False, "error": err}), 400
    if not (1 <= n <= 100):
        return jsonify({"ok": False, "error": "BAD_INPUT_RANGE"}), 400

    secret = int(st.get("secret", 50))
    tries  = int(st.get("tries", 0)) + 1
    res = "equal" if n == secret else ("low" if n < secret else "high")

    GameRuntime.patch_state(s["id"], {"tries": tries})
    GameRuntime.log(SLUG, s["id"], user_id, "guess", {"n": n}, {"res": res, "tries": tries})

    return jsonify({"ok": True, "result": res, "tries": tries})
