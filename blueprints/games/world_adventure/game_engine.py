"""
游戏引擎核心 - v2 共享持久世界系统
包含：任务系统、骰子判定、状态追踪、世界扩展
"""
import random
import json
from datetime import datetime
from database import DatabaseManager


class DiceSystem:
    """骰子判定系统"""

    @staticmethod
    def roll_d20():
        """投掷20面骰"""
        return random.randint(1, 20)

    @staticmethod
    def roll_ability_check(ability_score, difficulty_class=10):
        """
        能力检定
        ability_score: 能力值 (1-10)
        difficulty_class: 难度值 (DC)

        返回: {
            'roll': 骰子结果,
            'total': 总值,
            'success': 是否成功,
            'level': 'critical'/'success'/'partial'/'failure'
        }
        """
        roll = DiceSystem.roll_d20()
        modifier = ability_score - 5  # 5是基准，+/- 修正
        total = roll + modifier

        # 判定结果
        if roll == 20:
            level = 'critical'  # 大成功
            success = True
        elif roll == 1:
            level = 'failure'  # 大失败
            success = False
        elif total >= difficulty_class + 5:
            level = 'success'  # 成功
            success = True
        elif total >= difficulty_class:
            level = 'partial'  # 部分成功
            success = True
        else:
            level = 'failure'  # 失败
            success = False

        return {
            'roll': roll,
            'modifier': modifier,
            'total': total,
            'dc': difficulty_class,
            'success': success,
            'level': level
        }


class QuestSystem:
    """任务系统"""

    @staticmethod
    def get_quest(quest_id):
        """获取任务详情"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM world_quests WHERE id = %s
                """, (quest_id,))
                return cur.fetchone()

    @staticmethod
    def get_player_quest_progress(user_id, world_id, quest_id):
        """获取玩家任务进度"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT quest_progress FROM player_world_progress
                    WHERE user_id = %s AND world_id = %s
                """, (user_id, world_id))
                result = cur.fetchone()
                if result:
                    progress = result.get('quest_progress', {})
                    return progress.get(quest_id, {
                        'checkpoints_completed': [],
                        'current_checkpoint': 0
                    })
        return {'checkpoints_completed': [], 'current_checkpoint': 0}

    @staticmethod
    def update_quest_progress(user_id, world_id, quest_id, checkpoint_id):
        """更新任务进度"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                # 获取当前进度
                cur.execute("""
                    SELECT quest_progress FROM player_world_progress
                    WHERE user_id = %s AND world_id = %s
                """, (user_id, world_id))
                result = cur.fetchone()

                if result:
                    quest_progress = result.get('quest_progress', {})
                else:
                    quest_progress = {}

                # 更新检查点
                if quest_id not in quest_progress:
                    quest_progress[quest_id] = {
                        'checkpoints_completed': [],
                        'current_checkpoint': 0
                    }

                if checkpoint_id not in quest_progress[quest_id]['checkpoints_completed']:
                    quest_progress[quest_id]['checkpoints_completed'].append(checkpoint_id)
                    quest_progress[quest_id]['current_checkpoint'] = checkpoint_id

                # 保存到数据库
                cur.execute("""
                    UPDATE player_world_progress
                    SET quest_progress = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s AND world_id = %s
                """, (json.dumps(quest_progress), user_id, world_id))
                conn.commit()

                return quest_progress[quest_id]

    @staticmethod
    def check_quest_completion(quest, progress):
        """检查任务是否完成"""
        if not quest or not progress:
            return False

        checkpoints = quest.get('checkpoints', [])
        completed = progress.get('checkpoints_completed', [])

        # 所有检查点都完成
        return len(completed) >= len(checkpoints)

    @staticmethod
    def get_next_checkpoint(quest, progress):
        """获取下一个检查点"""
        checkpoints = quest.get('checkpoints', [])
        completed = progress.get('checkpoints_completed', [])

        for checkpoint in checkpoints:
            if checkpoint['id'] not in completed:
                return checkpoint
        return None


class WorldStateTracker:
    """世界状态追踪器"""

    @staticmethod
    def get_or_create_player_progress(user_id, world_id):
        """获取或创建玩家进度"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM player_world_progress
                    WHERE user_id = %s AND world_id = %s
                """, (user_id, world_id))
                progress = cur.fetchone()

                if not progress:
                    # 创建新进度记录
                    import uuid
                    progress_id = str(uuid.uuid4())
                    cur.execute("""
                        INSERT INTO player_world_progress
                        (id, user_id, world_id, discovered_locations, visited_npcs,
                         active_quests, completed_quests, quest_progress, npc_relationships, faction_reputation)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING *
                    """, (
                        progress_id, user_id, world_id,
                        '[]', '[]', '[]', '[]', '{}', '{}', '{}'
                    ))
                    progress = cur.fetchone()
                    conn.commit()

                return progress

    @staticmethod
    def update_current_location(user_id, world_id, location_id):
        """更新玩家当前位置"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                # 更新当前位置
                cur.execute("""
                    UPDATE player_world_progress
                    SET current_location_id = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s AND world_id = %s
                """, (location_id, user_id, world_id))

                # 添加到已发现列表
                cur.execute("""
                    UPDATE player_world_progress
                    SET discovered_locations =
                        CASE
                            WHEN discovered_locations ? %s THEN discovered_locations
                            ELSE discovered_locations || %s::jsonb
                        END
                    WHERE user_id = %s AND world_id = %s
                """, (location_id, json.dumps([location_id]), user_id, world_id))

                # 更新地点访问统计
                cur.execute("""
                    UPDATE world_locations
                    SET visit_count = visit_count + 1,
                        is_discovered = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND NOT is_discovered
                """, (location_id,))

                conn.commit()

    @staticmethod
    def record_npc_interaction(user_id, world_id, npc_id, interaction_quality='neutral'):
        """记录NPC互动"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                # 添加到已见NPC列表
                cur.execute("""
                    UPDATE player_world_progress
                    SET visited_npcs =
                        CASE
                            WHEN visited_npcs ? %s THEN visited_npcs
                            ELSE visited_npcs || %s::jsonb
                        END
                    WHERE user_id = %s AND world_id = %s
                """, (npc_id, json.dumps([npc_id]), user_id, world_id))

                # 更新关系值
                reputation_change = {
                    'positive': 10,
                    'neutral': 0,
                    'negative': -10
                }.get(interaction_quality, 0)

                if reputation_change != 0:
                    cur.execute("""
                        UPDATE player_world_progress
                        SET npc_relationships =
                            jsonb_set(
                                COALESCE(npc_relationships::jsonb, '{}'::jsonb),
                                ARRAY[%s, 'reputation'],
                                to_jsonb(
                                    COALESCE(
                                        (npc_relationships::jsonb -> %s ->> 'reputation')::int,
                                        50
                                    ) + %s
                                )
                            )::text
                        WHERE user_id = %s AND world_id = %s
                    """, (npc_id, npc_id, reputation_change, user_id, world_id))

                # 更新NPC互动统计
                cur.execute("""
                    UPDATE world_npcs
                    SET interaction_count = interaction_count + 1,
                        last_interaction_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (npc_id,))

                conn.commit()

    @staticmethod
    def log_player_action(run_id, user_id, world_id, action_type, action_content,
                          location_id=None, target_npc_id=None, dice_result=None,
                          success=None, outcome=None):
        """记录玩家行动"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO player_action_log
                    (run_id, user_id, world_id, action_type, action_content,
                     location_id, target_npc_id, dice_roll, success, outcome)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    run_id, user_id, world_id, action_type, action_content,
                    location_id, target_npc_id, dice_result, success, outcome
                ))
                conn.commit()


class WorldExpansionEngine:
    """世界扩展引擎 - AI动态生成新内容"""

    @staticmethod
    def should_expand_world(world_id, context):
        """判断是否需要扩展世界"""
        # 简化版：当玩家探索未知区域时
        if 'unknown' in context.lower() or '探索' in context:
            return True
        return False

    @staticmethod
    def generate_new_location(world_id, generation_context):
        """AI生成新地点（由AI服务调用）"""
        import uuid
        location_id = str(uuid.uuid4())

        # 这里会调用AI服务生成地点详情
        # 当前返回占位数据
        return {
            'id': location_id,
            'world_id': world_id,
            'location_name': '未知区域',
            'description': '一片等待探索的神秘之地...',
            'is_ai_generated': True,
            'generation_context': generation_context
        }

    @staticmethod
    def save_new_location(location_data):
        """保存新生成的地点"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO world_locations
                    (id, world_id, location_name, location_type, description,
                     danger_level, is_ai_generated, generation_context)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                """, (
                    location_data['id'],
                    location_data['world_id'],
                    location_data['location_name'],
                    location_data.get('location_type', 'wilderness'),
                    location_data.get('description', ''),
                    location_data.get('danger_level', 5),
                    location_data.get('is_ai_generated', False),
                    location_data.get('generation_context', '')
                ))
                location = cur.fetchone()
                conn.commit()
                return location


class GameEngine:
    """游戏引擎主类 - 整合所有系统"""

    def __init__(self):
        self.dice = DiceSystem()
        self.quest = QuestSystem()
        self.state = WorldStateTracker()
        self.expansion = WorldExpansionEngine()

    def process_player_action(self, run, character, world, action_text, progress):
        """
        处理玩家行动 - 核心游戏逻辑

        返回: {
            'requires_check': bool,  # 是否需要能力检定
            'check_type': str,       # 检定类型（combat/social等）
            'check_dc': int,         # 难度值
            'dice_result': dict,     # 骰子结果
            'success': bool,         # 是否成功
            'narrative': str,        # 叙事文本（给DM参考）
            'state_changes': dict    # 状态变化
        }
        """
        result = {
            'requires_check': False,
            'check_type': None,
            'check_dc': 10,
            'dice_result': None,
            'success': True,
            'narrative': '',
            'state_changes': {}
        }

        # 分析行动类型（简化版）
        action_lower = action_text.lower()

        # 检测是否需要能力检定
        if any(word in action_lower for word in ['攻击', '战斗', 'fight', 'attack']):
            result['requires_check'] = True
            result['check_type'] = 'combat'
            result['check_dc'] = 12
        elif any(word in action_lower for word in ['说服', '交涉', 'persuade', 'negotiate']):
            result['requires_check'] = True
            result['check_type'] = 'social'
            result['check_dc'] = 13
        elif any(word in action_lower for word in ['潜行', '隐藏', 'sneak', 'hide']):
            result['requires_check'] = True
            result['check_type'] = 'stealth'
            result['check_dc'] = 14
        elif any(word in action_lower for word in ['调查', '研究', 'investigate', 'research']):
            result['requires_check'] = True
            result['check_type'] = 'knowledge'
            result['check_dc'] = 11

        # 执行能力检定
        if result['requires_check']:
            ability_score = character.get(f"ability_{result['check_type']}", 5)
            check_result = self.dice.roll_ability_check(ability_score, result['check_dc'])
            result['dice_result'] = check_result
            result['success'] = check_result['success']

            # 生成叙事提示
            if check_result['level'] == 'critical':
                result['narrative'] = f"🎲 大成功！(骰出 {check_result['roll']}) - 行动超出预期地成功了！"
            elif check_result['level'] == 'success':
                result['narrative'] = f"🎲 成功 (骰出 {check_result['roll']}, 总计 {check_result['total']} vs DC {check_result['dc']}) - 行动顺利完成。"
            elif check_result['level'] == 'partial':
                result['narrative'] = f"🎲 部分成功 (骰出 {check_result['roll']}, 总计 {check_result['total']} vs DC {check_result['dc']}) - 行动勉强达成，但有代价。"
            else:
                result['narrative'] = f"🎲 失败 (骰出 {check_result['roll']}, 总计 {check_result['total']} vs DC {check_result['dc']}) - 行动未能成功。"

        return result

    def get_world_context_for_ai(self, world, progress, run):
        """
        为AI生成完整的世界上下文
        """
        world_id = world.get('id')

        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                # 获取当前位置
                current_location = None
                if progress.get('current_location_id'):
                    cur.execute("""
                        SELECT * FROM world_locations WHERE id = %s
                    """, (progress['current_location_id'],))
                    current_location = cur.fetchone()

                # 获取当前任务
                current_quest = None
                if run.get('current_quest_id'):
                    current_quest = self.quest.get_quest(run['current_quest_id'])

                # 获取附近的NPC
                nearby_npcs = []
                if current_location:
                    cur.execute("""
                        SELECT * FROM world_npcs
                        WHERE current_location_id = %s AND is_alive = TRUE
                        LIMIT 5
                    """, (current_location['id'],))
                    nearby_npcs = cur.fetchall()

                # 获取已访问的地点
                discovered_locations = []
                discovered_ids = progress.get('discovered_locations', [])
                if isinstance(discovered_ids, str):
                    discovered_ids = json.loads(discovered_ids)
                if discovered_ids:
                    cur.execute("""
                        SELECT location_name, description FROM world_locations
                        WHERE id = ANY(%s)
                    """, (discovered_ids,))
                    discovered_locations = cur.fetchall()

        context = {
            'world_name': world.get('world_name'),
            'world_lore': world.get('world_lore'),
            'current_location': current_location,
            'nearby_npcs': nearby_npcs,
            'current_quest': current_quest,
            'discovered_locations': discovered_locations,
            'quest_progress': self.quest.get_player_quest_progress(
                progress.get('user_id'),
                world_id,
                run.get('current_quest_id')
            ) if run.get('current_quest_id') else None
        }

        return context
