# blueprints/games/tic_tac_toe/plugin.py
from flask import Blueprint, render_template, make_response, request
import secrets

SLUG = "tic_tac_toe"

def get_meta():
    return {
        "slug": SLUG,
        "title": "AI 井字棋",
        "subtitle": "玩家 vs AI（可选难度）",
        "path": f"/g/{SLUG}/",
        "tags": ["Game","Frontend-only"]
    }

bp = Blueprint(
    SLUG, __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",
)

def _ensure_sid(resp):
    # 与项目中其余游戏一致：为游客发一个 sid，方便未来统计/配额
    if request.cookies.get("sid"):
        return resp
    sid = secrets.token_hex(16)
    resp.set_cookie("sid", sid, max_age=60*60*24*730, httponly=True, samesite="Lax", secure=False)
    return resp

@bp.get("/")
def page():
    resp = make_response(render_template("games/tic_tac_toe/index.html"))
    return _ensure_sid(resp)

def get_blueprint():
    return bp
