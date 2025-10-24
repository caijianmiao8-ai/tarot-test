"""Blueprint registration for the interactive code playground game."""
from flask import Blueprint, render_template, make_response, request
import secrets

SLUG = "code_playground"


def get_meta():
    return {
        "slug": SLUG,
        "title": "实时画布",
        "subtitle": "左侧写代码 · 右侧立即预览",
        "path": f"/g/{SLUG}/",
        "tags": ["Game", "Code", "Live Preview"],
    }


bp = Blueprint(
    SLUG,
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",
)


def _ensure_sid(resp):
    """Keep behaviour aligned with other mini games by issuing a sid cookie."""
    if request.cookies.get("sid"):
        return resp

    sid = secrets.token_hex(16)
    resp.set_cookie(
        "sid",
        sid,
        max_age=60 * 60 * 24 * 730,
        httponly=True,
        samesite="Lax",
        secure=False,
    )
    return resp


@bp.get("/")
def page():
    resp = make_response(render_template("games/code_playground/index.html"))
    return _ensure_sid(resp)


def get_blueprint():
    return bp
