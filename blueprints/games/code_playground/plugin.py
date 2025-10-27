"""Blueprint registration for the interactive code playground game."""

from flask import (
    Blueprint,
    render_template,
    make_response,
    request,
    jsonify,
    url_for,
    abort,
)
import secrets
import time

SLUG = "code_playground"

# 用内存暂存分享快照（MVP够用）
# 如果你要线上长久分享，可以后面换成数据库
_SNAPSHOTS = {}  # { share_id: { "source": "...", "ts": 1730000000 } }


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
    """跟其他小游戏保持一致：如果没有 sid cookie，就发一个"""
    if request.cookies.get("sid"):
        return resp

    sid = secrets.token_hex(16)
    resp.set_cookie(
        "sid",
        sid,
        max_age=60 * 60 * 24 * 730,  # 2年
        httponly=True,
        samesite="Lax",
        secure=False,
    )
    return resp


@bp.get("/")
def page():
    """
    主编辑器页：
    - 左侧textarea写代码
    - 右侧iframe实时预览
    """
    resp = make_response(render_template("games/code_playground/index.html"))
    return _ensure_sid(resp)


@bp.post("/snapshot")
def create_snapshot():
    """
    前端点“分享演示”时会POST到这里。
    输入: {"source": "<当前编辑器代码>"}
    输出: {"id": "<随机ID>", "url": "http://.../g/code_playground/p/<随机ID>"}
    """
    data = request.get_json(silent=True) or {}
    source = data.get("source", "")

    if not isinstance(source, str) or not source.strip():
        return jsonify({"error": "缺少有效的 source"}), 400

    share_id = secrets.token_urlsafe(8)
    _SNAPSHOTS[share_id] = {
        "source": source,
        "ts": int(time.time()),
    }

    share_url = url_for(
        f"{SLUG}.shared_page",
        share_id=share_id,
        _external=True,  # 返回完整URL，方便复制给别人
    )

    return jsonify(
        {
            "id": share_id,
            "url": share_url,
        }
    )


@bp.get("/p/<share_id>")
def shared_page(share_id):
    """
    别人打开这个链接：/g/code_playground/p/<share_id>
    看到的是只读预览页（没有左侧编辑器）。
    这个页会把 source 再丢到 /api/compile-preview 编译，然后放进 iframe。
    """
    snap = _SNAPSHOTS.get(share_id)
    if not snap:
        abort(404)

    resp = make_response(
        render_template(
            "games/code_playground/share.html",
            share_id=share_id,
            source=snap["source"],
        )
    )
    return _ensure_sid(resp)


def get_blueprint():
    return bp
