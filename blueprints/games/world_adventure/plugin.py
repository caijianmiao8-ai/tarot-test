"""
AI 世界冒险跑团游戏模块
支持:世界生成 → 角色创建 → Run 游玩 → 结算
"""
from flask import Blueprint, render_template, request, jsonify, g, redirect, url_for
import uuid
import json
from datetime import datetime
from database import DatabaseManager
from .ai_service import AdventureAIService  # AI 服务统一接口

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


def generate_world_with_ai(template, world_name, user_prompt=None, stability=50, danger=50, mystery=50):
    """使用 AI 生成世界内容"""
    try:
        world_data = AdventureAIService.generate_world(
            template=template,
            world_name=world_name,
            user_prompt=user_prompt,
            stability=stability,
            danger=danger,
            mystery=mystery
        )

        # 如果 AI 返回 None，使用默认值
        if world_data is None:
            return {
                "world_description": f"{world_name}是一个神秘的世界，等待勇敢的冒险者探索。",
                "world_lore": "关于这个世界的历史，还有许多未解之谜...",
                "locations": [],
                "factions": [],
                "npcs": []
            }

        return world_data

    except Exception as e:
        print(f"AI 生成世界失败: {e}")
        # 返回默认值
        return {
            "world_description": f"{world_name}是一个神秘的世界，等待勇敢的冒险者探索。",
            "world_lore": "关于这个世界的历史，还有许多未解之谜...",
            "locations": [],
            "factions": [],
            "npcs": []
        }


def generate_dm_response(run, character, world, player_action):
    """AI DM 生成响应"""
    try:
        # 获取对话历史
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT role, content FROM adventure_run_messages
                    WHERE run_id = %s
                    ORDER BY created_at ASC
                    LIMIT 20
                """, (run['id'],))
                messages = cur.fetchall()

        # 使用新的 AI 服务
        dm_response = AdventureAIService.generate_dm_response(
            run=run,
            character=character,
            world=world,
            player_action=player_action,
            conversation_history=messages
        )

        # 如果 AI 返回 None，使用默认响应
        if dm_response is None:
            dm_response = f"(你执行了行动: {player_action[:50]}...)，周围的环境发生了一些变化..."

        return dm_response

    except Exception as e:
        print(f"AI DM 响应失败: {e}")
        return f"(你执行了行动: {player_action[:50]}...)，周围的环境发生了一些变化..."


# ========================================
# 页面路由
# ========================================
@bp.get("/")
@bp.get("")
def index():
    """游戏主页:显示世界选择界面"""
    user_id = _get_user_id()

    # 获取用户的世界列表
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            if user_id:
                cur.execute("""
                    SELECT * FROM adventure_worlds
                    WHERE owner_user_id = %s AND is_archived = FALSE
                    ORDER BY created_at DESC
                """, (user_id,))
            else:
                # 游客模式:暂时不显示
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

    # 获取 Run 详细信息
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    r.*,
                    w.world_name, w.stability, w.danger, w.mystery,
                    c.char_name, c.char_class,
                    c.ability_combat, c.ability_social, c.ability_stealth,
                    c.ability_knowledge, c.ability_survival
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
    """创建世界（含 AI 生成）"""
    user_id = _get_user_id()
    data = request.get_json() or {}

    template_id = data.get("template_id")
    world_name = data.get("world_name", "未命名世界")
    user_prompt = data.get("user_prompt")
    stability = data.get("stability", 50)
    danger = data.get("danger", 50)
    mystery = data.get("mystery", 50)

    # 获取模板
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM adventure_world_templates WHERE id = %s
            """, (template_id,))
            template = cur.fetchone()

    if not template:
        return jsonify({"error": "模板不存在"}), 400

    # AI 生成世界内容
    world_data = generate_world_with_ai(
        template, world_name, user_prompt,
        stability, danger, mystery
    )

    # 生成世界 ID
    world_id = str(uuid.uuid4())

    # 保存到数据库
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO adventure_worlds
                (id, owner_user_id, template_id, world_name, world_description,
                 world_lore, stability, danger, mystery,
                 locations_data, factions_data, npcs_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """, (
                world_id,
                user_id,
                template_id,
                world_name,
                world_data.get('world_description', ''),
                world_data.get('world_lore', ''),
                stability,
                danger,
                mystery,
                json.dumps(world_data.get('locations', [])),
                json.dumps(world_data.get('factions', [])),
                json.dumps(world_data.get('npcs', []))
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
                 appearance, ability_combat, ability_social, ability_stealth,
                 ability_knowledge, ability_survival, equipment_data, relationships_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """, (
                char_id,
                user_id,
                data.get('char_name', '无名冒险者'),
                data.get('char_class', '冒险者'),
                data.get('background', ''),
                data.get('personality', ''),
                data.get('appearance', ''),
                data.get('ability_combat', 5),
                data.get('ability_social', 5),
                data.get('ability_stealth', 5),
                data.get('ability_knowledge', 5),
                data.get('ability_survival', 5),
                '{}',  # equipment_data
                '{}'   # relationships_data
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
            cur.execute("SELECT * FROM adventure_worlds WHERE id = %s", (world_id,))
            world = cur.fetchone()
            if not world:
                return jsonify({"error": "世界不存在"}), 400

            cur.execute("SELECT * FROM adventure_characters WHERE id = %s", (character_id,))
            character = cur.fetchone()
            if not character:
                return jsonify({"error": "角色不存在"}), 400

    # AI 生成任务
    run_title = f"{character['char_name']}在{world['world_name']}的冒险"
    mission_objective = "探索这个未知的世界，发现隐藏的秘密"

    run_id = str(uuid.uuid4())

    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO adventure_runs
                (id, world_id, character_id, user_id, run_title,
                 run_type, mission_objective, status, max_turns, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', 20, %s)
                RETURNING *
            """, (
                run_id,
                world_id,
                character_id,
                user_id,
                run_title,
                'exploration',
                mission_objective,
                '{}'
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

    # 获取 Run、世界、角色信息
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.*, w.*, c.*
                FROM adventure_runs r
                JOIN adventure_worlds w ON r.world_id = w.id
                JOIN adventure_characters c ON r.character_id = c.id
                WHERE r.id = %s
            """, (run_id,))
            full_data = cur.fetchone()

    if not full_data:
        return jsonify({"error": "Run 不存在"}), 404

    if full_data['status'] != 'active':
        return jsonify({"error": "Run 已结束"}), 400

    # 保存玩家消息
    current_turn = full_data['current_turn'] + 1
    msg_id = str(uuid.uuid4())

    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO adventure_run_messages
                (id, run_id, role, content, turn_number, action_type, dice_rolls)
                VALUES (%s, %s, 'player', %s, %s, NULL, NULL)
            """, (msg_id, run_id, action_text, current_turn))

            # 更新 Run 的回合数
            cur.execute("""
                UPDATE adventure_runs
                SET current_turn = %s
                WHERE id = %s
            """, (current_turn, run_id))

            conn.commit()

    # AI 生成 DM 响应
    dm_response = generate_dm_response(full_data, full_data, full_data, action_text)

    # 保存 DM 消息
    dm_msg_id = str(uuid.uuid4())
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO adventure_run_messages
                (id, run_id, role, content, turn_number, action_type, dice_rolls)
                VALUES (%s, %s, 'dm', %s, %s, NULL, NULL)
            """, (dm_msg_id, run_id, dm_response, current_turn))
            conn.commit()

    # 检查是否达到回合上限
    run_ended = current_turn >= full_data['max_turns']

    return jsonify({
        "ok": True,
        "turn": current_turn,
        "dm_response": dm_response,
        "run_ended": run_ended
    })


@bp.get("/api/runs/<run_id>/messages")
def api_run_messages(run_id):
    """获取 Run 的所有消息"""
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT role, content, turn_number, created_at
                FROM adventure_run_messages
                WHERE run_id = %s
                ORDER BY created_at ASC
            """, (run_id,))
            messages = cur.fetchall()

    return jsonify({
        "ok": True,
        "messages": [dict(msg) for msg in messages]
    })


@bp.post("/api/runs/<run_id>/complete")
def api_run_complete(run_id):
    """完成 Run(结算)"""
    user_id = _get_user_id()
    data = request.get_json() or {}

    outcome = data.get("outcome", "success")

    # TODO: AI 生成结算总结
    summary = f"冒险结束，结果：{outcome}"

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
