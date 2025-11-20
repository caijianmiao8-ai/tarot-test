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
                    cur.execute("""
                        SELECT * FROM world_quests WHERE id = %s
                    """, (run['current_quest_id'],))
                    current_quest = cur.fetchone()

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

                # 获取任务进度（在同一个连接中）
                quest_progress = None
                if run.get('current_quest_id'):
                    cur.execute("""
                        SELECT quest_progress FROM player_world_progress
                        WHERE user_id = %s AND world_id = %s
                    """, (progress.get('user_id'), world_id))
                    result = cur.fetchone()
                    if result and result.get('quest_progress'):
                        quest_progress = result['quest_progress'].get(str(run['current_quest_id']), {
                            'checkpoints_completed': [],
                            'current_checkpoint': 0
                        })

        context = {
            'world_name': world.get('world_name'),
            'world_lore': world.get('world_lore'),
            'current_location': current_location,
            'nearby_npcs': nearby_npcs,
            'current_quest': current_quest,
            'discovered_locations': discovered_locations,
            'quest_progress': quest_progress
        }

        return context


class ActionAnalyzer:
    """智能行为分析器 - 识别玩家行动类型并触发世界状态更新"""

    @staticmethod
    def analyze_action(action_text, world_context, character):
        """
        分析玩家行动，识别类型和目标

        返回: {
            'action_type': 'dialogue'/'explore'/'combat'/'investigate'/'other',
            'targets': ['npc_name'/  'location_name'/...],
            'keywords': [...]
        }
        """
        action_lower = action_text.lower()
        analysis = {
            'action_type': 'other',
            'targets': [],
            'keywords': []
        }

        # 对话关键词
        dialogue_keywords = ['询问', '交谈', '对话', '说话', '问', '告诉', '和', '与', '向', '说', '聊']
        # 探索关键词
        explore_keywords = ['前往', '走向', '去', '进入', '到达', '移动', '探索', '寻找']
        # 调查关键词
        investigate_keywords = ['调查', '搜索', '检查', '观察', '查看', '寻找', '搜寻']
        # 战斗关键词
        combat_keywords = ['攻击', '战斗', '打', '杀', '砍', '射', '刺']

        # 识别行动类型
        if any(kw in action_lower for kw in dialogue_keywords):
            analysis['action_type'] = 'dialogue'
        elif any(kw in action_lower for kw in explore_keywords):
            analysis['action_type'] = 'explore'
        elif any(kw in action_lower for kw in combat_keywords):
            analysis['action_type'] = 'combat'
        elif any(kw in action_lower for kw in investigate_keywords):
            analysis['action_type'] = 'investigate'

        # 识别目标NPC
        nearby_npcs = world_context.get('nearby_npcs', [])
        for npc in nearby_npcs:
            npc_name = npc.get('npc_name', '')
            if npc_name in action_text:
                analysis['targets'].append({
                    'type': 'npc',
                    'id': npc.get('id'),
                    'name': npc_name
                })

        # 识别目标地点（从世界中的所有地点）
        # 这里简化处理，实际应该从数据库查询
        current_location = world_context.get('current_location')
        if current_location:
            location_name = current_location.get('location_name', '')
            # 如果行动提到当前地点，标记为探索当前位置
            if location_name in action_text:
                analysis['targets'].append({
                    'type': 'location',
                    'id': current_location.get('id'),
                    'name': location_name
                })

        return analysis

    @staticmethod
    def auto_update_world_state(analysis, action_result, user_id, world_id, run_id):
        """
        根据行为分析自动更新世界状态
        """
        updates = []

        # 如果是对话行动且成功，更新NPC关系
        if analysis['action_type'] == 'dialogue':
            for target in analysis['targets']:
                if target['type'] == 'npc':
                    # 根据成功等级决定关系变化
                    quality = 'positive' if action_result.get('success') else 'neutral'
                    WorldStateTracker.record_npc_interaction(
                        user_id, world_id, target['id'], quality
                    )
                    updates.append(f"与{target['name']}的关系发生变化")

        # 如果是探索行动，可能发现新地点（这里简化，实际需要更复杂的逻辑）
        if analysis['action_type'] == 'explore':
            for target in analysis['targets']:
                if target['type'] == 'location':
                    WorldStateTracker.update_current_location(
                        user_id, world_id, target['id']
                    )
                    updates.append(f"探索了{target['name']}")

        return updates


class CheckpointDetector:
    """检查点完成检测器 - 自动识别玩家是否完成任务检查点"""

    @staticmethod
    def check_checkpoint_completion(checkpoint, analysis, action_result, world_context, user_id, world_id):
        """
        检测检查点是否完成

        checkpoint: 检查点数据
        analysis: 行为分析结果
        action_result: 行动结果（骰子等）
        world_context: 世界上下文

        返回: {
            'completed': True/False,
            'reason': '完成原因说明'
        }
        """
        result = {
            'completed': False,
            'reason': ''
        }

        description = checkpoint.get('description', '')
        required_location_id = checkpoint.get('location', '')
        requires = checkpoint.get('requires', {})

        # 1. 检查地点要求（使用ID匹配）
        location_ok = True
        if required_location_id:
            current_loc = world_context.get('current_location', {})
            current_loc_id = current_loc.get('id', '')
            location_ok = (current_loc_id == required_location_id)
            if not location_ok:
                result['reason'] = f"需要在{current_loc.get('location_name', '指定地点')}完成"
                return result

        # 2. 检查特殊要求（能力判定）
        if requires:
            required_ability = requires.get('ability')
            required_dc = requires.get('dc')
            if required_ability and required_dc:
                # 需要通过特定能力检定
                if not action_result.get('requires_check'):
                    result['reason'] = f"需要{required_ability}判定"
                    return result
                if not action_result.get('success'):
                    result['reason'] = f"判定失败（DC {required_dc}）"
                    return result

        # 3. 从description推断行动类型
        action_ok = False
        action_type = analysis.get('action_type', '')

        # 对话类检查点
        if '对话' in description or '了解' in description or '汇报' in description or '询问' in description:
            if action_type == 'dialogue':
                action_ok = True
            else:
                result['reason'] = "需要与NPC对话"

        # 前往类检查点
        elif '前往' in description or '到达' in description:
            if action_type in ['explore', 'investigate']:
                action_ok = True
            else:
                result['reason'] = "需要前往指定地点"

        # 搜寻/调查类检查点
        elif '搜寻' in description or '调查' in description or '搜索' in description:
            if action_type == 'investigate':
                action_ok = True
            else:
                result['reason'] = "需要调查或搜寻"

        # 追踪/战斗类检查点
        elif '追踪' in description or '夺回' in description or '击败' in description:
            if action_type in ['combat', 'investigate']:
                action_ok = True
            else:
                result['reason'] = "需要战斗或追踪"

        # 其他类型：只要在对的地方就算完成
        else:
            action_ok = location_ok

        # 4. 判断是否完成
        if location_ok and action_ok:
            # 如果有能力要求，必须成功
            if requires:
                if action_result.get('success', False):
                    result['completed'] = True
                    result['reason'] = f"完成了检查点：{description}"
                else:
                    result['reason'] = "行动失败，检查点未完成"
            else:
                # 没有特殊要求，直接完成
                result['completed'] = True
                result['reason'] = f"完成了检查点：{description}"

        return result
