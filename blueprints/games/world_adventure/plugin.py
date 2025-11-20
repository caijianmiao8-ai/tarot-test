"""
AI 世界冒险跑团游戏模块
支持:世界生成 → 角色创建 → Run 游玩 → 结算
"""
from flask import Blueprint, render_template, request, jsonify, g, redirect, url_for
import uuid
from datetime import datetime
from database import DatabaseManager

SLUG = "world_adventure"

def get_meta():
    """游戏元信息"""
    return {
        "slug": SLUG,
        "title": "AI 世界冒险",
        "subtitle": "单人跑团 · 持久世界 · AI DM",
        "path": f"/g/{SLUG}/",
        "tags": ["AI", "RPG", "冒险"]
    }

bp = Blueprint(
    SLUG,
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",
)


# ========================================
# 辅助函数
# ========================================
def _get_user_id():
    """获取当前用户 ID(支持游客)"""
    user = getattr(g, 'user', None)
    if user and isinstance(user, dict):
        return user.get('id')
    return None

def _get_session_id():
    """获取会话 ID(用于游客)"""
    from flask import session
    return session.get('id') or session.get('session_id')


# ========================================
# 页面路由
# ========================================
@bp.get("/")
@bp.get("")
def index():
    """游戏主页:显示世界选择界面"""
    user_id = _get_user_id()
    session_id = _get_session_id()

    # 获取用户的世界列表
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            # 简化版:只获取登录用户的世界
            if user_id:
                cur.execute("""
                    SELECT * FROM adventure_worlds
                    WHERE owner_user_id = %s
                    ORDER BY created_at DESC
                """, (user_id,))
            else:
                # 游客模式:可以考虑用 session_id 绑定
                cur.execute("SELECT * FROM adventure_worlds LIMIT 0")

            worlds = cur.fetchall()

    return render_template(
        f"games/{SLUG}/index.html",
        worlds=worlds
    )


@bp.get("/worlds/create")
def world_create_page():
    """世界创建页面"""
    # 获取世界模板列表
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM adventure_world_templates
                WHERE is_active = TRUE
                ORDER BY id
            """)
            templates = cur.fetchall()

    return render_template(
        f"games/{SLUG}/world_create.html",
        templates=templates
    )


@bp.get("/characters/create")
def character_create_page():
    """角色创建页面"""
    return render_template(f"games/{SLUG}/character_create.html")


@bp.get("/runs/<run_id>/play")
def run_play_page(run_id):
    """Run 游玩页面"""
    user_id = _get_user_id()

    # 验证权限
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.*, w.world_name, c.char_name
                FROM adventure_runs r
                JOIN adventure_worlds w ON r.world_id = w.id
                JOIN adventure_characters c ON r.character_id = c.id
                WHERE r.id = %s
            """, (run_id,))
            run = cur.fetchone()

    if not run:
        return "Run 不存在", 404

    # 权限检查(简化版)
    if user_id and run.get('user_id') != user_id:
        return "无权访问", 403

    return render_template(
        f"games/{SLUG}/run_play.html",
        run=run
    )


# ========================================
# API 路由
# ========================================
@bp.post("/api/worlds/create")
def api_world_create():
    """创建世界"""
    user_id = _get_user_id()
    data = request.get_json() or {}

    template_id = data.get("template_id")
    world_name = data.get("world_name", "未命名世界")

    # 从模板加载默认参数
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM adventure_world_templates WHERE id = %s
            """, (template_id,))
            template = cur.fetchone()

    if not template:
        return jsonify({"error": "模板不存在"}), 400

    # 生成世界 ID
    world_id = str(uuid.uuid4())

    # TODO: 这里应该调用 AI 生成世界描述/地点/NPC 等
    # 现在先用简单的占位数据
    world_description = f"这是一个{template['name']}类型的世界"

    default_params = template.get('default_world_params') or {}

    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO adventure_worlds
                (id, owner_user_id, template_id, world_name, world_description,
                 stability, danger, mystery)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """, (
                world_id,
                user_id,
                template_id,
                world_name,
                world_description,
                default_params.get('stability', 50),
                default_params.get('danger', 50),
                default_params.get('mystery', 50)
            ))
            world = cur.fetchone()
            conn.commit()

    return jsonify({
        "ok": True,
        "world_id": world_id,
        "world": dict(world) if world else None
    })


@bp.post("/api/characters/create")
def api_character_create():
    """创建角色"""
    user_id = _get_user_id()
    data = request.get_json() or {}

    char_id = str(uuid.uuid4())

    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO adventure_characters
                (id, user_id, char_name, char_class, background, personality,
                 ability_combat, ability_social, ability_stealth,
                 ability_knowledge, ability_survival)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """, (
                char_id,
                user_id,
                data.get('char_name', '无名冒险者'),
                data.get('char_class', '冒险者'),
                data.get('background', ''),
                data.get('personality', ''),
                data.get('ability_combat', 5),
                data.get('ability_social', 5),
                data.get('ability_stealth', 5),
                data.get('ability_knowledge', 5),
                data.get('ability_survival', 5)
            ))
            character = cur.fetchone()
            conn.commit()

    return jsonify({
        "ok": True,
        "character_id": char_id,
        "character": dict(character) if character else None
    })


@bp.post("/api/runs/start")
def api_run_start():
    """开始一个新的 Run"""
    user_id = _get_user_id()
    data = request.get_json() or {}

    world_id = data.get("world_id")
    character_id = data.get("character_id")

    # 验证世界和角色存在
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM adventure_worlds WHERE id = %s", (world_id,))
            if not cur.fetchone():
                return jsonify({"error": "世界不存在"}), 400

            cur.execute("SELECT 1 FROM adventure_characters WHERE id = %s", (character_id,))
            if not cur.fetchone():
                return jsonify({"error": "角色不存在"}), 400

    run_id = str(uuid.uuid4())

    # TODO: 这里应该调用 AI 生成任务标题/目标等
    run_title = "未知的冒险"
    mission_objective = "探索世界,完成未知的使命"

    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO adventure_runs
                (id, world_id, character_id, user_id, run_title,
                 run_type, mission_objective, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'active')
                RETURNING *
            """, (
                run_id,
                world_id,
                character_id,
                user_id,
                run_title,
                'exploration',
                mission_objective
            ))
            run = cur.fetchone()
            conn.commit()

    return jsonify({
        "ok": True,
        "run_id": run_id,
        "redirect": url_for(f"{SLUG}.run_play_page", run_id=run_id)
    })


@bp.post("/api/runs/<run_id>/action")
def api_run_action(run_id):
    """玩家在 Run 中执行行动"""
    user_id = _get_user_id()
    data = request.get_json() or {}

    action_text = data.get("action", "").strip()
    if not action_text:
        return jsonify({"error": "行动不能为空"}), 400

    # 获取 Run 信息
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM adventure_runs WHERE id = %s
            """, (run_id,))
            run = cur.fetchone()

    if not run:
        return jsonify({"error": "Run 不存在"}), 404

    if run['status'] != 'active':
        return jsonify({"error": "Run 已结束"}), 400

    # 保存玩家消息
    msg_id = str(uuid.uuid4())
    current_turn = run['current_turn'] + 1

    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO adventure_run_messages
                (id, run_id, role, content, turn_number)
                VALUES (%s, %s, 'player', %s, %s)
            """, (msg_id, run_id, action_text, current_turn))

            # 更新 Run 的回合数
            cur.execute("""
                UPDATE adventure_runs
                SET current_turn = %s
                WHERE id = %s
            """, (current_turn, run_id))

            conn.commit()

    # TODO: 这里应该调用 AI 生成 DM 响应
    dm_response = f"(AI DM 回应占位) 你执行了:{action_text}"

    # 保存 DM 消息
    dm_msg_id = str(uuid.uuid4())
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO adventure_run_messages
                (id, run_id, role, content, turn_number)
                VALUES (%s, %s, 'dm', %s, %s)
            """, (dm_msg_id, run_id, dm_response, current_turn))
            conn.commit()

    return jsonify({
        "ok": True,
        "turn": current_turn,
        "dm_response": dm_response
    })


@bp.post("/api/runs/<run_id>/complete")
def api_run_complete(run_id):
    """完成 Run(结算)"""
    user_id = _get_user_id()
    data = request.get_json() or {}

    outcome = data.get("outcome", "success")  # success/failure/partial/death

    # TODO: 这里应该调用 AI 生成结算总结和影响
    summary = f"冒险结束,结果:{outcome}"

    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE adventure_runs
                SET status = 'completed',
                    outcome = %s,
                    summary = %s,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (outcome, summary, run_id))

            # 更新世界和角色的 total_runs
            cur.execute("""
                UPDATE adventure_worlds
                SET total_runs = total_runs + 1
                WHERE id = (SELECT world_id FROM adventure_runs WHERE id = %s)
            """, (run_id,))

            cur.execute("""
                UPDATE adventure_characters
                SET total_runs = total_runs + 1
                WHERE id = (SELECT character_id FROM adventure_runs WHERE id = %s)
            """, (run_id,))

            conn.commit()

    return jsonify({
        "ok": True,
        "summary": summary
    })


def get_blueprint():
    """返回 Blueprint 对象"""
    return bp
