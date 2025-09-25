from flask import Blueprint, render_template, request, jsonify, g, make_response
from core.runtime import GameRuntime
import secrets

SLUG = "guess_number"

def get_meta():
    return {
        "slug": SLUG,
        "title": "猜数字",
        "subtitle": "后端有状态 · 完全独立样式",
        "path": f"/g/{SLUG}/",
        "tags": ["Demo","Backend"]
    }

def _ids():
    """统一获取身份：登录用 user_id，游客用 sid（如无则返回 None）"""
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
        httponly=True, samesite="Lax", secure=True  # 若本地 http 开发，secure 改为 False
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
    def page():
        # 页面渲染时确保游客有 sid
        resp = make_response(render_template(f"games/{SLUG}/index.html"))
        return _ensure_sid(resp)

    @bp.post("/api/start")
    def api_start():
        user_id, sid = _ids()
        # 配额校验
        ok, left = GameRuntime.can_play(SLUG, user_id, sid, is_guest=(user_id is None))
        if not ok:
            return jsonify({"ok": False, "error": "DAILY_LIMIT", "left": left}), 429

        # 拿“当日会话”
        s = GameRuntime.session(SLUG, user_id, sid, daily=True)

        # 初始化一局
        import random
        GameRuntime.patch_state(s["id"], {"secret": random.randint(1, 100), "tries": 0})
        GameRuntime.log(SLUG, s["id"], user_id, "start", {"init": True})

        resp = jsonify({"ok": True})
        return _ensure_sid(resp)

    @bp.post("/api/guess")
    def api_guess():
        user_id, sid = _ids()

        # 也要做配额校验（防止跳过 /api/start）
        ok, left = GameRuntime.can_play(SLUG, user_id, sid, is_guest=(user_id is None))
        if not ok:
            return jsonify({"ok": False, "error": "DAILY_LIMIT", "left": left}), 429

        s = GameRuntime.session(SLUG, user_id, sid, daily=True)
        st = (s.get("state") or {})

        # 兜底：如果还没 start，自动开启一局
        if "secret" not in st:
            import random
            GameRuntime.patch_state(s["id"], {"secret": random.randint(1, 100), "tries": 0})
            st = (GameRuntime.session(SLUG, user_id, sid, daily=True).get("state") or {})

        secret = int(st.get("secret", 50))
        tries  = int(st.get("tries", 0)) + 1

        data = request.get_json(silent=True) or {}
        try:
            n = int(data.get("n"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "BAD_INPUT"}), 400

        res = "equal" if n == secret else ("low" if n < secret else "high")

        # 更新状态 + 记账/日志（log 内部会 bump 用量一次）
        GameRuntime.patch_state(s["id"], {"tries": tries})
        GameRuntime.log(SLUG, s["id"], user_id, "guess", {"n": n}, {"res": res, "tries": tries})

        return jsonify({"ok": True, "result": res, "tries": tries})

    return bp
