from flask import Blueprint, render_template, request, jsonify, g, make_response
from core.runtime import GameRuntime
import secrets, random, os

SLUG = "guess_number"

def get_meta():
    return {
        "slug": SLUG,
        "title": "猜数字",
        "subtitle": "后端有状态 · 完全独立样式",
        "path": f"/g/{SLUG}/",
        "tags": ["Demo","Backend"]
    }

# 本地 http 建议不启用 Secure；上线 https 可在环境变量里设 COOKIE_SECURE=1
SECURE_COOKIE = os.getenv("COOKIE_SECURE", "0").lower() in ("1", "true", "yes")

def _ids():
    """统一获取身份：登录用 user_id，游客用 sid"""
    user_id = (getattr(g, "user", {}) or {}).get("id")
    sid = request.cookies.get("sid")
    return user_id, sid

def _ensure_sid(resp):
    """若没有 sid，为游客下发一个长期 cookie（2 年）"""
    if request.cookies.get("sid"):
        return resp
    sid = secrets.token_hex(16)
    resp.set_cookie(
        "sid", sid,
        max_age=60*60*24*730,  # 2 years
        httponly=True, samesite="Lax", secure=SECURE_COOKIE
    )
    return resp

def get_blueprint():
    bp = Blueprint(
        SLUG, __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path=f"/static/games/{SLUG}",
    )

    @bp.get("/")
    @bp.get("")  # 无尾斜杠也能命中
    def page():
        resp = make_response(render_template(f"games/{SLUG}/index.html"))
        return _ensure_sid(resp)

    # 兜底：若未来有非“简单请求”的 header 导致预检，也能秒回
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
        """兼容 JSON 与 表单 两种入参"""
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

        ok, left = GameRuntime.can_play(SLUG, user_id, sid, is_guest=(user_id is None))
        if not ok:
            return jsonify({"ok": False, "error": "DAILY_LIMIT", "left": left}), 429

        s = GameRuntime.session(SLUG, user_id, sid, daily=True)
        st = (s.get("state") or {})

        # 兜底：还没 start 也能自动开一局
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

    return bp
