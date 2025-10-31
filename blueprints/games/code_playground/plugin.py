"""
Blueprint for the interactive code_playground page.
Now with permanent share links backed by Supabase/Postgres.
"""

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
from database import DatabaseManager  # <-- 关键：用你现有的 Supabase 连接管理器


SLUG = "code_playground"

bp = Blueprint(
    SLUG,
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",
)

# ------------------------------------------------------------------
# cookie 辅助：给访客分配 sid，和你原来的一致
# ------------------------------------------------------------------
def _ensure_sid(resp):
    if request.cookies.get("sid"):
        return resp

    sid = secrets.token_hex(16)
    resp.set_cookie(
        "sid",
        sid,
        max_age=60 * 60 * 24 * 730,  # 2年
        httponly=True,
        samesite="Lax",
        secure=False,  # 如果你全站是 https，可以改成 True
    )
    return resp


# ------------------------------------------------------------------
# DB helpers: 持久化 snapshot
# ------------------------------------------------------------------

def _create_table_if_needed(conn):
    """
    确保表存在。Postgres 里的 IF NOT EXISTS 是幂等的，
    所以即使每次请求都跑也不会报错。
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS code_playground_snapshots (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
        )
    conn.commit()


def save_snapshot_to_db(share_id: str, source: str):
    """
    把分享快照写进 Supabase 的 Postgres 里。
    """
    with DatabaseManager.get_db() as conn:
        _create_table_if_needed(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO code_playground_snapshots (id, source, created_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (id) DO UPDATE
                SET source = EXCLUDED.source;
                """,
                (share_id, source),
            )
        conn.commit()


def load_snapshot_from_db(share_id: str):
    """
    通过 share_id 取出当时保存的代码。
    如果没有，就返回 None。
    """
    with DatabaseManager.get_db() as conn:
        _create_table_if_needed(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source
                FROM code_playground_snapshots
                WHERE id = %s
                LIMIT 1;
                """,
                (share_id,),
            )
            row = cur.fetchone()

    # RealDictCursor: row 是 dict-like，比如 {"source": "..."}，否则可能是 tuple
    if not row:
        return None
    try:
        return row["source"]
    except Exception:
        # fallback for tuple-style fetchone
        return row[0] if len(row) > 0 else None


# ------------------------------------------------------------------
# 页面路由
# ------------------------------------------------------------------

def get_meta():
    return {
        "slug": SLUG,
        "title": "实时画布",
        "subtitle": "左侧写代码 · 右侧立即预览",
        "path": f"/g/{SLUG}/",
        "tags": ["Game", "Code", "Live Preview"],
    }


@bp.get("/")
def page():
    """
    主编辑器页：
    - 左侧 textarea/code editor 写 React+Tailwind
    - 右侧 iframe 实时预览（main.js 里去调 /api/compile-preview）
    """
    resp = make_response(render_template("games/code_playground/index.html"))
    return _ensure_sid(resp)


@bp.post("/snapshot")
def create_snapshot():
    """
    前端点击“分享演示”时会调用这个接口。
    请求体: { "source": "<当前编辑器代码字符串>" }

    我们要做：
    1. 生成 share_id
    2. 把 source 永久写进数据库
    3. 返回一个可以公开访问的链接 /g/code_playground/p/<share_id>

    前端拿这个链接，复制给别人就行了。
    """
    data = request.get_json(silent=True) or {}
    source = data.get("source", "")

    if not isinstance(source, str) or not source.strip():
        return jsonify({"ok": False, "error": "缺少有效的 source"}), 400

    share_id = secrets.token_urlsafe(8)  # 短ID就够用了，可读又随机

    # 写入 Supabase / Postgres
    save_snapshot_to_db(share_id, source)

    share_url = url_for(
        f"{SLUG}.shared_page",
        share_id=share_id,
        _external=True,  # 让前端拿到完整 URL（包含域名）
    )

    return jsonify(
        {
            "ok": True,
            "id": share_id,
            "url": share_url,
        }
    )


@bp.get("/p/<share_id>")
def shared_page(share_id):
    """
    别人打开 /g/code_playground/p/<share_id> 时走这里。

    这个页面不会显示左侧编辑器，只展示 iframe 预览。
    share.html 里会把源码注入成 window.__SNAPSHOT_SOURCE__，
    然后 share_view.js 会拿这段源码去 POST /api/compile-preview，
    得到 {js, css}，最后把它塞进 iframe。
    """
    source = load_snapshot_from_db(share_id)
    if not source:
        abort(404)

    resp = make_response(
        render_template(
            "games/code_playground/share.html",
            share_id=share_id,
            source=source,
        )
    )
    return _ensure_sid(resp)


def get_blueprint():
    return bp
