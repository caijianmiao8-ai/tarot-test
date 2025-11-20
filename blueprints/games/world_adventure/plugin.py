"""
AI 世界冒险跑团游戏模块 V2
支持:共享持久世界 → 角色创建 → 任务冒险 → 骰子判定
"""
from flask import Blueprint, render_template, request, jsonify, g, redirect, url_for
import uuid
import json
from datetime import datetime
from database import DatabaseManager
from .ai_service import AdventureAIService  # AI 服务统一接口
from .game_engine import GameEngine  # V2 游戏引擎

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
    """游戏主页:显示官方世界选择界面 (V2)"""
    user_id = _get_user_id()

    worlds = []
    characters = []

    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            # V2: 查询官方共享世界
            cur.execute("""
                SELECT w.*,
                    COUNT(DISTINCT l.id) as location_count,
                    COUNT(DISTINCT n.id) as npc_count,
                    COUNT(DISTINCT q.id) as quest_count
                FROM adventure_worlds w
                LEFT JOIN world_locations l ON w.id = l.world_id
                LEFT JOIN world_npcs n ON w.id = n.world_id
                LEFT JOIN world_quests q ON w.id = q.world_id
                WHERE w.is_official_world = TRUE
                GROUP BY w.id
                ORDER BY w.created_at DESC
            """)
            worlds = cur.fetchall()

            # 查询角色（只有登录用户才有角色）
            if user_id:
                cur.execute("""
                    SELECT * FROM adventure_characters
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (user_id,))
                characters = cur.fetchall()

    return render_template(
        f"games/{SLUG}/index.html",
        worlds=worlds,
        characters=characters
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
    """Run 游玩页面 (V2 - 包含任务/地点/NPC 数据)"""
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

            # V2: 获取当前任务信息
            current_quest = None
            quest_progress = None
            if run.get('current_quest_id'):
                cur.execute("""
                    SELECT * FROM world_quests WHERE id = %s
                """, (run['current_quest_id'],))
                current_quest = cur.fetchone()

                # 获取玩家任务进度
                if current_quest:
                    cur.execute("""
                        SELECT quest_progress FROM player_world_progress
                        WHERE user_id = %s AND world_id = %s
                    """, (run['user_id'], run['world_id']))
                    progress_row = cur.fetchone()
                    if progress_row and progress_row['quest_progress']:
                        quest_progress = progress_row['quest_progress'].get(str(run['current_quest_id']), {})

            # V2: 获取当前地点信息
            current_location = None
            if run.get('current_location_id'):
                cur.execute("""
                    SELECT * FROM world_locations WHERE id = %s
                """, (run['current_location_id'],))
                current_location = cur.fetchone()

            # V2: 获取附近的 NPC
            nearby_npcs = []
            if run.get('current_location_id'):
                cur.execute("""
                    SELECT * FROM world_npcs
                    WHERE world_id = %s AND current_location_id = %s
                    ORDER BY interaction_count DESC
                    LIMIT 5
                """, (run['world_id'], run['current_location_id']))
                nearby_npcs = cur.fetchall()

    # 权限检查(简化版)
    if user_id and run.get('user_id') != user_id:
        return "无权访问", 403

    return render_template(
        f"games/{SLUG}/run_play.html",
        run=run,
        current_quest=current_quest,
        quest_progress=quest_progress,
        current_location=current_location,
        nearby_npcs=nearby_npcs
    )


# ========================================
# API 路由
# ========================================
@bp.post("/api/worlds/create")
def api_world_create():
    """创建世界（含 AI 生成）"""
    try:
        user_id = _get_user_id()
        data = request.get_json() or {}

        template_id = data.get("template_id")
        world_name = data.get("world_name", "未命名世界")
        user_prompt = data.get("user_prompt")
        stability = data.get("stability", 50)
        danger = data.get("danger", 50)
        mystery = data.get("mystery", 50)

        if not template_id:
            return jsonify({"ok": False, "error": "请选择世界模板"}), 400

        # 获取模板
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM adventure_world_templates WHERE id = %s
                """, (template_id,))
                template = cur.fetchone()

        if not template:
            return jsonify({"ok": False, "error": "模板不存在"}), 400

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

    except Exception as e:
        print(f"创建世界失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": f"创建世界失败: {str(e)}"
        }), 500


@bp.post("/api/characters/create")
def api_character_create():
    """创建角色"""
    try:
        user_id = _get_user_id()
        data = request.get_json() or {}

        # 验证必需字段
        char_name = data.get('char_name', '').strip()
        if not char_name:
            return jsonify({"ok": False, "error": "请输入角色名称"}), 400

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
                    char_name,
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

    except Exception as e:
        print(f"创建角色失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": f"创建角色失败: {str(e)}"
        }), 500


@bp.post("/api/runs/start")
def api_run_start():
    """开始一个新的 Run (V2 - 使用游戏引擎)"""
    try:
        user_id = _get_user_id()
        data = request.get_json() or {}

        world_id = data.get("world_id")
        character_id = data.get("character_id")

        if not world_id or not character_id:
            return jsonify({"ok": False, "error": "请选择世界和角色"}), 400

        # 初始化游戏引擎
        engine = GameEngine()

        # 验证世界和角色存在
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM adventure_worlds WHERE id = %s", (world_id,))
                world = cur.fetchone()
                if not world:
                    return jsonify({"ok": False, "error": "世界不存在"}), 400

                cur.execute("SELECT * FROM adventure_characters WHERE id = %s", (character_id,))
                character = cur.fetchone()
                if not character:
                    return jsonify({"ok": False, "error": "角色不存在"}), 400

                # 获取或创建玩家进度
                progress = engine.state.get_or_create_player_progress(user_id, world_id)

                # 获取初始位置（已发现的地点，或世界起始地点）
                start_location_id = None
                if progress.get('current_location_id'):
                    start_location_id = progress['current_location_id']
                else:
                    # 查找世界的起始地点（已发现的安全地点）
                    cur.execute("""
                        SELECT id FROM world_locations
                        WHERE world_id = %s AND is_discovered = TRUE
                        ORDER BY danger_level ASC
                        LIMIT 1
                    """, (world_id,))
                    start_loc = cur.fetchone()
                    if start_loc:
                        start_location_id = start_loc['id']
                        # 设置为当前位置
                        engine.state.update_current_location(user_id, world_id, start_location_id)

                # 获取或分配主线任务
                current_quest_id = None
                cur.execute("""
                    SELECT id FROM world_quests
                    WHERE world_id = %s AND quest_type = 'main' AND is_active = TRUE
                    ORDER BY difficulty ASC
                    LIMIT 1
                """, (world_id,))
                quest = cur.fetchone()
                if quest:
                    current_quest_id = quest['id']

        # 创建Run
        run_title = f"{character['char_name']}在{world['world_name']}的冒险"
        mission_objective = "探索这个未知的世界，发现隐藏的秘密"

        run_id = str(uuid.uuid4())

        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO adventure_runs
                    (id, world_id, character_id, user_id, run_title,
                     run_type, mission_objective, status, max_turns, metadata,
                     current_quest_id, current_location_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', 50, %s, %s, %s)
                    RETURNING *
                """, (
                    run_id,
                    world_id,
                    character_id,
                    user_id,
                    run_title,
                    'exploration',
                    mission_objective,
                    '{}',
                    current_quest_id,
                    start_location_id
                ))
                run = cur.fetchone()
                conn.commit()

        return jsonify({
            "ok": True,
            "run_id": run_id,
            "redirect": url_for(f"{SLUG}.run_play_page", run_id=run_id)
        })

    except Exception as e:
        print(f"开始游戏失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": f"开始游戏失败: {str(e)}"
        }), 500


@bp.post("/api/runs/<run_id>/action")
def api_run_action(run_id):
    """玩家在 Run 中执行行动 (V2 - 使用游戏引擎和骰子判定)"""
    try:
        user_id = _get_user_id()
        data = request.get_json() or {}

        action_text = data.get("action", "").strip()
        if not action_text:
            return jsonify({"ok": False, "error": "行动不能为空"}), 400

        # 初始化游戏引擎
        engine = GameEngine()

        # 获取 Run、世界、角色信息
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        r.id as run_id, r.current_turn, r.max_turns, r.status,
                        r.run_title, r.mission_objective, r.current_quest_id,
                        r.current_location_id,
                        w.id as world_id, w.world_name, w.world_lore, w.world_description,
                        w.stability, w.danger, w.mystery,
                        c.id as character_id, c.char_name, c.char_class, c.background,
                        c.ability_combat, c.ability_social, c.ability_stealth,
                        c.ability_knowledge, c.ability_survival
                    FROM adventure_runs r
                    JOIN adventure_worlds w ON r.world_id = w.id
                    JOIN adventure_characters c ON r.character_id = c.id
                    WHERE r.id = %s
                """, (run_id,))
                run_data = cur.fetchone()

        if not run_data:
            return jsonify({"ok": False, "error": "Run 不存在"}), 404

        if run_data['status'] != 'active':
            return jsonify({"ok": False, "error": "Run 已结束"}), 400

        # 获取玩家进度
        progress = engine.state.get_or_create_player_progress(
            user_id,
            run_data['world_id']
        )

        # 获取对话历史
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT role, content FROM adventure_run_messages
                    WHERE run_id = %s
                    ORDER BY created_at ASC
                """, (run_id,))
                conversation_history = cur.fetchall()

        # 使用游戏引擎处理行动（骰子判定等）
        action_result = engine.process_player_action(
            run_data,
            run_data,  # character
            run_data,  # world
            action_text,
            progress
        )

        # 获取完整的世界上下文
        world_context = engine.get_world_context_for_ai(
            run_data,
            progress,
            run_data
        )

        # 【V2 新增】智能行为分析
        from .game_engine import ActionAnalyzer, CheckpointDetector

        analysis = ActionAnalyzer.analyze_action(
            action_text,
            world_context,
            run_data
        )

        # 【V2 新增】自动更新世界状态（NPC关系、地点探索）
        state_updates = ActionAnalyzer.auto_update_world_state(
            analysis,
            action_result,
            user_id,
            run_data['world_id'],
            run_id
        )

        # 【V2 新增】检查点完成检测
        checkpoint_completed = False
        checkpoint_message = ""
        current_quest = world_context.get('current_quest')
        quest_progress = world_context.get('quest_progress', {})

        if current_quest:
            checkpoints = current_quest.get('checkpoints', [])
            completed_ids = quest_progress.get('checkpoints_completed', []) if quest_progress else []

            # 找到当前检查点
            for cp in checkpoints:
                if cp.get('id') not in completed_ids:
                    # 检测是否完成
                    detection = CheckpointDetector.check_checkpoint_completion(
                        cp, analysis, action_result, world_context, user_id, run_data['world_id']
                    )

                    if detection['completed']:
                        # 更新任务进度
                        engine.quest.update_quest_progress(
                            user_id,
                            run_data['world_id'],
                            current_quest['id'],
                            cp['id']
                        )
                        checkpoint_completed = True
                        checkpoint_message = f"\n\n✅ **任务进度更新**：{detection['reason']}"

                        # 重新获取world_context以反映更新后的任务进度
                        world_context = engine.get_world_context_for_ai(
                            run_data,
                            engine.state.get_or_create_player_progress(user_id, run_data['world_id']),
                            run_data
                        )
                    break

        # 使用 V2 AI 服务生成 DM 响应
        dm_response = AdventureAIService.generate_dm_response_v2(
            world_context=world_context,
            character=run_data,
            player_action=action_text,
            conversation_history=conversation_history,
            action_result=action_result
        )

        # 如果检查点完成，在DM响应后添加系统消息
        if checkpoint_completed and checkpoint_message:
            dm_response = (dm_response or "") + checkpoint_message

        # 如果 AI 返回 None，使用默认响应
        if dm_response is None:
            if action_result.get('narrative'):
                dm_response = action_result['narrative']
            else:
                dm_response = f"(你执行了行动: {action_text[:50]}...)，周围的环境发生了一些变化..."

        # 更新回合
        current_turn = run_data['current_turn'] + 1

        # 保存玩家消息
        msg_id = str(uuid.uuid4())
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO adventure_run_messages
                    (id, run_id, role, content, turn_number, dice_result,
                     ability_used, success_level)
                    VALUES (%s, %s, 'player', %s, %s, %s, %s, %s)
                """, (
                    msg_id, run_id, action_text, current_turn,
                    action_result.get('dice_result', {}).get('roll') if action_result.get('requires_check') else None,
                    action_result.get('check_type'),
                    action_result.get('dice_result', {}).get('level') if action_result.get('requires_check') else None
                ))

                # 保存 DM 消息
                dm_msg_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO adventure_run_messages
                    (id, run_id, role, content, turn_number)
                    VALUES (%s, %s, 'dm', %s, %s)
                """, (dm_msg_id, run_id, dm_response, current_turn))

                # 更新 Run 的回合数
                cur.execute("""
                    UPDATE adventure_runs
                    SET current_turn = %s
                    WHERE id = %s
                """, (current_turn, run_id))

                conn.commit()

        # 记录行动到日志
        engine.state.log_player_action(
            run_id=run_id,
            user_id=user_id,
            world_id=run_data['world_id'],
            action_type=action_result.get('check_type', 'general'),
            action_content=action_text,
            location_id=run_data.get('current_location_id'),
            dice_result=action_result.get('dice_result', {}).get('roll') if action_result.get('requires_check') else None,
            success=action_result.get('success'),
            outcome=dm_response
        )

        # 检查是否达到回合上限
        run_ended = current_turn >= run_data['max_turns']

        return jsonify({
            "ok": True,
            "turn": current_turn,
            "dm_response": dm_response,
            "run_ended": run_ended,
            "dice_result": action_result.get('dice_result') if action_result.get('requires_check') else None,
            "narrative": action_result.get('narrative', '')
        })

    except Exception as e:
        print(f"执行行动失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": f"执行行动失败: {str(e)}"
        }), 500


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
