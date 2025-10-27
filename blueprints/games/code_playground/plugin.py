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

# 这里用一个简单的内存字典来存快照。
# 这意味着：服务器重启就没了，多进程部署时各进程不共享。
# 但本地演示 / 单进程部署已经够用了。
_SNAPSHOTS = {}  # { share_id: {"source": "...", "ts": 1730000000} }


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
    """编辑+预览的主页面"""
    resp = make_response(render_template("games/code_playground/index.html"))
    return _ensure_sid(resp)


# ========== 新增：创建分享快照 ==========
@bp.post("/snapshot")
def create_snapshot():
    """
    前端会把当前编辑器里的源码 POST 过来。
    我们分配一个随机ID，存在内存里，然后回前端一个可分享链接。
    """
    data = request.get_json(silent=True) or {}
    source = data.get("source", "")

    if not isinstance(source, str) or not source.strip():
        return jsonify({"error": "缺少有效的 source"}), 400

    # 生成短一点的分享ID
    share_id = secrets.token_urlsafe(8)
    _SNAPSHOTS[share_id] = {
        "source": source,
        "ts": int(time.time()),
    }

    share_url = url_for(
        f"{SLUG}.shared_page",
        share_id=share_id,
        _external=True,  # 返回绝对URL，方便直接复制给别人
    )

    return jsonify(
        {
            "id": share_id,
            "url": share_url,
        }
    )


# ========== 新增：只读分享页 ==========
@bp.get("/p/<share_id>")
def shared_page(share_id):
    """
    别人通过 /g/code_playground/p/<share_id> 打开这个页面。
    页面是“只读演示模式”：
    - 没有左侧编辑器
    - 只有右边的预览画布
    - 前端会拿我们保存的源码，再去调 /api/compile-preview 做一次编译
    """
    snap = _SNAPSHOTS.get(share_id)
    if not snap:
        abort(404)

    resp = make_response(
        render_template(
            "games/code_playground/share.html",
            share_id=share_id,
            # 传给模板，模板里会塞进 window.__SNAPSHOT_SOURCE__
            source=snap["source"],
        )
    )
    return _ensure_sid(resp)


def get_blueprint():
    return bp
