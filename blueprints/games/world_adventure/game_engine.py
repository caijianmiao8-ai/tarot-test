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
        """更新玩家当前位置（Phase 1: 同时设置起始网格）"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                # Phase 1: 查找该地点的起始网格（如果有）
                cur.execute("""
                    SELECT id FROM location_grids
                    WHERE location_id = %s
                    ORDER BY grid_position->>'x', grid_position->>'y'
                    LIMIT 1
                """, (location_id,))
                start_grid = cur.fetchone()
                start_grid_id = start_grid['id'] if start_grid else None

                # 更新当前位置和网格
                if start_grid_id:
                    cur.execute("""
                        UPDATE player_world_progress
                        SET current_location_id = %s,
                            current_grid_id = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = %s AND world_id = %s
                    """, (location_id, start_grid_id, user_id, world_id))
                else:
                    # Fallback: 没有网格的地点，只更新位置
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
                                COALESCE(npc_relationships, '{}'::jsonb),
                                ARRAY[%s, 'reputation'],
                                to_jsonb(
                                    COALESCE(
                                        (npc_relationships -> %s ->> 'reputation')::int,
                                        50
                                    ) + %s
                                )
                            )
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


class GridMovementSystem:
    """网格移动系统 - Phase 1"""

    @staticmethod
    def get_grid_by_id(grid_id):
        """获取网格数据"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM location_grids WHERE id = %s
                """, (grid_id,))
                return cur.fetchone()

    @staticmethod
    def get_grids_by_location(location_id):
        """获取某个地点的所有网格"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM location_grids WHERE location_id = %s
                """, (location_id,))
                return cur.fetchall()

    @staticmethod
    def find_path_to_grid(start_grid_id, target_grid_id, max_depth=3):
        """
        使用BFS查找从起始grid到目标grid的路径

        返回: {
            'found': bool,
            'path': [grid_id1, grid_id2, ...],  # 包含所有途经grid，最后一个是目标
            'names': [name1, name2, ...]  # 途经地点名称
        }
        """
        if start_grid_id == target_grid_id:
            return {'found': True, 'path': [], 'names': []}

        from collections import deque

        # BFS队列: (current_grid_id, path_ids, path_names)
        queue = deque([(start_grid_id, [], [])])
        visited = {start_grid_id}

        while queue:
            current_id, path_ids, path_names = queue.popleft()

            # 限制最大深度
            if len(path_ids) >= max_depth:
                continue

            # 获取当前grid
            current_grid = GridMovementSystem.get_grid_by_id(current_id)
            if not current_grid:
                continue

            connected = current_grid.get('connected_grids', [])
            if isinstance(connected, str):
                connected = json.loads(connected)

            for conn in connected:
                next_id = conn.get('grid_id')
                if not next_id or next_id in visited:
                    continue

                # 获取下一个grid的名称
                next_grid = GridMovementSystem.get_grid_by_id(next_id)
                if not next_grid:
                    continue

                next_name = next_grid.get('grid_name', '')
                new_path_ids = path_ids + [next_id]
                new_path_names = path_names + [next_name]

                # 找到目标！
                if next_id == target_grid_id:
                    return {
                        'found': True,
                        'path': new_path_ids,
                        'names': new_path_names
                    }

                visited.add(next_id)
                queue.append((next_id, new_path_ids, new_path_names))

        return {'found': False, 'path': [], 'names': []}

    @staticmethod
    def detect_movement(action_text, current_grid_id):
        """
        检测玩家是否尝试移动到其他网格（支持跨grid路径查找）

        返回: {
            'target_grid_id': str,
            'is_direct': bool,  # 是否直接连接
            'path': [],  # 如果非直接，包含途经的grid IDs
            'path_names': []  # 途经地点名称
        } 或 None
        """
        if not current_grid_id:
            return None

        current_grid = GridMovementSystem.get_grid_by_id(current_grid_id)
        if not current_grid:
            return None

        connected = current_grid.get('connected_grids', [])
        if isinstance(connected, str):
            connected = json.loads(connected)

        # 方向关键词映射
        direction_keywords = {
            'north': ['北', '北面', '往北', '向北', '北边'],
            'south': ['南', '南面', '往南', '向南', '南边'],
            'east': ['东', '东面', '往东', '向东', '东边'],
            'west': ['西', '西面', '往西', '向西', '西边']
        }

        # 移动关键词
        move_keywords = ['前往', '走向', '去', '进入', '到达', '移动', '走进', '走到', '来到']
        has_move_intent = any(kw in action_text for kw in move_keywords)

        # 特殊：离开当前位置的关键词
        exit_keywords = ['出', '离开', '走出', '退出', '出去', '离去']
        has_exit_intent = any(kw in action_text for kw in exit_keywords)

        for conn in connected:
            direction = conn.get('direction')
            target_grid_id = conn.get('grid_id')
            target_name = conn.get('target_name', '')

            # 特殊处理：如果玩家说"出酒馆"、"离开"等，检测当前grid名称
            if has_exit_intent:
                # 检查玩家是否提到当前位置的名称（如"出酒馆"中的"酒馆"）
                current_name = current_grid.get('grid_name', '')

                # 提取当前名称的关键词（去掉"内部"、"入口"等）
                current_keywords = current_name.replace('内部', '').replace('入口', '').replace('广场', '').replace('街区', '').strip()

                # 如果玩家说"出XX"且XX匹配当前位置，则尝试找到"入口"或相反方向
                if current_keywords and current_keywords in action_text:
                    # 优先选择名称包含"入口"的连接
                    if '入口' in target_name:
                        return {'target_grid_id': target_grid_id, 'is_direct': True, 'path': [], 'path_names': []}
                    # 或者选择第一个连接（通常是出口）
                    if direction == 'north' or direction == 'south':
                        return {'target_grid_id': target_grid_id, 'is_direct': True, 'path': [], 'path_names': []}

            # 检查方向关键词
            if direction in direction_keywords:
                keywords = direction_keywords[direction]
                if any(kw in action_text for kw in keywords):
                    return {'target_grid_id': target_grid_id, 'is_direct': True, 'path': [], 'path_names': []}

            # 检查目标网格名称（精确匹配）
            if target_name and target_name in action_text:
                return {'target_grid_id': target_grid_id, 'is_direct': True, 'path': [], 'path_names': []}

            # 模糊匹配：提取目标名称的关键词
            if has_move_intent and target_name:
                # 提取名称中的关键词（去掉"入口"等修饰词）
                name_keywords = target_name.replace('入口', '').replace('内部', '').replace('广场', '').replace('街区', '').strip()

                # 分词匹配：例如 "酒馆" 匹配 "酒馆入口"
                if name_keywords and name_keywords in action_text:
                    return {'target_grid_id': target_grid_id, 'is_direct': True, 'path': [], 'path_names': []}

                # 逐字匹配：例如 "商业街" 匹配 "商业街区"
                for i in range(len(name_keywords)):
                    for j in range(i+2, len(name_keywords)+1):
                        keyword = name_keywords[i:j]
                        if keyword in action_text:
                            return {'target_grid_id': target_grid_id, 'is_direct': True, 'path': [], 'path_names': []}

        # 如果直接连接中没找到，尝试跨grid路径查找
        if has_move_intent:
            # 获取当前location的所有grids
            current_location_id = current_grid.get('location_id')
            if current_location_id:
                all_grids = GridMovementSystem.get_grids_by_location(current_location_id)

                # 在所有grids中查找名称匹配的
                for grid in all_grids:
                    if grid['id'] == current_grid_id:
                        continue  # 跳过当前grid

                    grid_name = grid.get('grid_name', '')

                    # 提取关键词
                    name_keywords = grid_name.replace('入口', '').replace('内部', '').replace('广场', '').replace('街区', '').strip()

                    # 检查是否匹配
                    if (grid_name in action_text) or (name_keywords and name_keywords in action_text):
                        # 找到目标grid！使用BFS查找路径
                        path_result = GridMovementSystem.find_path_to_grid(
                            current_grid_id,
                            grid['id'],
                            max_depth=3
                        )

                        if path_result['found']:
                            return {
                                'target_grid_id': grid['id'],
                                'is_direct': False,
                                'path': path_result['path'],
                                'path_names': path_result['names']
                            }

        return None

    @staticmethod
    def get_player_current_grid(user_id, world_id):
        """获取玩家当前网格"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT current_grid_id FROM player_world_progress
                    WHERE user_id = %s AND world_id = %s
                """, (user_id, world_id))
                result = cur.fetchone()
                if result:
                    return result.get('current_grid_id')
        return None

    @staticmethod
    def check_first_visit(user_id, world_id, grid_id):
        """检查是否首次访问某个网格"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT discovered_locations FROM player_world_progress
                    WHERE user_id = %s AND world_id = %s
                """, (user_id, world_id))
                result = cur.fetchone()
                if result:
                    visited_grids = result.get('discovered_locations', [])
                    if isinstance(visited_grids, str):
                        visited_grids = json.loads(visited_grids)
                    # 使用 grid_id 作为访问标记
                    return grid_id not in visited_grids
        return True

    @staticmethod
    def record_grid_visit(user_id, world_id, grid_id):
        """记录网格访问"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE player_world_progress
                    SET discovered_locations =
                        CASE
                            WHEN discovered_locations ? %s THEN discovered_locations
                            ELSE discovered_locations || %s::jsonb
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s AND world_id = %s
                """, (grid_id, json.dumps([grid_id]), user_id, world_id))
                conn.commit()

    @staticmethod
    def execute_movement(user_id, world_id, new_grid_id):
        """
        执行移动，更新数据库

        返回: {
            'moved': True,
            'new_grid': grid_data,
            'description': str,
            'is_first_visit': bool
        }
        """
        new_grid = GridMovementSystem.get_grid_by_id(new_grid_id)
        if not new_grid:
            return {'moved': False, 'error': 'Grid not found'}

        # 更新玩家当前网格
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE player_world_progress
                    SET current_grid_id = %s,
                        current_location_id = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s AND world_id = %s
                """, (new_grid_id, new_grid['location_id'], user_id, world_id))
                conn.commit()

        # 检查是否首次访问
        is_first_visit = GridMovementSystem.check_first_visit(user_id, world_id, new_grid_id)

        if is_first_visit:
            GridMovementSystem.record_grid_visit(user_id, world_id, new_grid_id)
            description = new_grid.get('first_visit_description') or new_grid.get('description')
        else:
            description = new_grid.get('description')

        return {
            'moved': True,
            'new_grid': new_grid,
            'description': description,
            'is_first_visit': is_first_visit
        }


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
        为AI生成完整的世界上下文（Phase 1 - 包含网格信息）
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

                # Phase 1: 获取当前网格
                current_grid = None
                if progress.get('current_grid_id'):
                    cur.execute("""
                        SELECT * FROM location_grids WHERE id = %s
                    """, (progress['current_grid_id'],))
                    current_grid = cur.fetchone()

                    # 如果有当前网格，从网格数据中获取 NPC 信息
                    if current_grid:
                        npcs_present = current_grid.get('npcs_present', [])
                        if isinstance(npcs_present, str):
                            npcs_present = json.loads(npcs_present)

                        # 获取这些NPC的详细信息
                        nearby_npcs = []
                        npc_ids = [npc.get('npc_id') for npc in npcs_present if npc.get('npc_id')]
                        if npc_ids:
                            cur.execute("""
                                SELECT * FROM world_npcs
                                WHERE id = ANY(%s) AND is_alive = TRUE
                            """, (npc_ids,))
                            npc_details = {npc['id']: npc for npc in cur.fetchall()}

                            # 合并网格中的活动信息和数据库中的NPC详情
                            for npc_info in npcs_present:
                                npc_id = npc_info.get('npc_id')
                                if npc_id in npc_details:
                                    npc = dict(npc_details[npc_id])
                                    npc['activity'] = npc_info.get('activity', '')
                                    npc['position'] = npc_info.get('position', '')
                                    nearby_npcs.append(npc)
                else:
                    # Fallback: 旧版本逻辑，基于地点获取NPC
                    nearby_npcs = []
                    if current_location:
                        cur.execute("""
                            SELECT * FROM world_npcs
                            WHERE current_location_id = %s AND is_alive = TRUE
                            LIMIT 5
                        """, (current_location['id'],))
                        nearby_npcs = cur.fetchall()

                # 获取当前任务
                current_quest = None
                if run.get('current_quest_id'):
                    cur.execute("""
                        SELECT * FROM world_quests WHERE id = %s
                    """, (run['current_quest_id'],))
                    current_quest = cur.fetchone()

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
            'current_grid': current_grid,  # Phase 1: 添加当前网格
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
    """检查点完成检测器 - 基于网格系统的精确检测"""

    @staticmethod
    def check_checkpoint_completion(checkpoint, analysis, action_result, world_context, user_id, world_id):
        """
        检测检查点是否完成（Phase 1 - 基于网格ID的精确验证）

        checkpoint: 检查点数据（包含 grid_id）
        analysis: 行为分析结果
        action_result: 行动结果（骰子等）
        world_context: 世界上下文（包含 current_grid）

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
        required_grid_id = checkpoint.get('grid_id', '')
        required_action = checkpoint.get('action_type', checkpoint.get('required_action', ''))  # 兼容两种字段名
        target_npc = checkpoint.get('target_npc', '')
        requires = checkpoint.get('requires', {})

        # 调试日志
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[检查点检测] 检查点要求: grid_id={required_grid_id}, action={required_action}, npc={target_npc}")
        logger.info(f"[检查点检测] 当前上下文: grid={world_context.get('current_grid', {}).get('id')}")
        logger.info(f"[检查点检测] 行为分析: type={analysis.get('action_type')}, targets={analysis.get('targets', [])}")

        # Phase 1: 如果有 grid_id，使用精确的网格验证
        if required_grid_id:
            # 1. 网格验证（最重要）
            current_grid = world_context.get('current_grid', {})
            current_grid_id = current_grid.get('id', '')

            if current_grid_id != required_grid_id:
                result['reason'] = f"需要前往指定地点（当前: {current_grid.get('grid_name', '未知')}, 需要: 检查点位置）"
                logger.info(f"[检查点检测] ❌ 网格不匹配: {current_grid_id} != {required_grid_id}")
                return result

            logger.info(f"[检查点检测] ✓ 网格匹配: {current_grid_id}")

            # 2. 行动类型验证
            action_type = analysis.get('action_type', '')

            if required_action == 'dialogue':
                if action_type != 'dialogue':
                    result['reason'] = "需要与NPC对话"
                    logger.info(f"[检查点检测] ❌ 行动类型不匹配: {action_type} != dialogue")
                    return result
            elif required_action == 'investigation':
                if action_type not in ['dialogue', 'investigate', 'other']:
                    result['reason'] = "需要调查或收集情报"
                    logger.info(f"[检查点检测] ❌ 行动类型不匹配: {action_type} not in [dialogue, investigate, other]")
                    return result
            elif required_action == 'exploration':
                # 探索类型较宽松，到达网格即可
                pass
            elif required_action == 'combat':
                if action_type != 'combat':
                    result['reason'] = "需要战斗行动"
                    logger.info(f"[检查点检测] ❌ 行动类型不匹配: {action_type} != combat")
                    return result

            logger.info(f"[检查点检测] ✓ 行动类型匹配: {action_type}")

            # 3. 目标NPC验证（如果需要）
            if target_npc:
                action_targets = analysis.get('targets', [])
                logger.info(f"[检查点检测] 需要验证NPC: {target_npc}, 当前targets: {action_targets}")
                # 修复：target_npc可能是名字或ID，都要检查
                npc_found = any(
                    t.get('type') == 'npc' and (
                        t.get('id') == target_npc or  # 匹配ID
                        t.get('name') == target_npc   # 匹配名字
                    )
                    for t in action_targets
                )
                if not npc_found:
                    result['reason'] = f"需要与{target_npc}对话"
                    logger.info(f"[检查点检测] ❌ NPC不匹配: 未找到 {target_npc}")
                    return result
                logger.info(f"[检查点检测] ✓ NPC匹配: {target_npc}")

            # 4. 能力判定验证（如果需要）
            if requires:
                required_ability = requires.get('ability')
                required_dc = requires.get('dc')
                if required_ability and required_dc:
                    if not action_result.get('success'):
                        result['reason'] = f"判定失败（需要DC {required_dc}）"
                        logger.info(f"[检查点检测] ❌ 判定失败: DC {required_dc}")
                        return result
                    logger.info(f"[检查点检测] ✓ 判定成功: DC {required_dc}")

            # 所有条件满足
            result['completed'] = True
            result['reason'] = f"✅ 完成了检查点：{description}"
            logger.info(f"[检查点检测] ✅ 检查点完成! {description}")
            return result

        else:
            # Fallback: 旧版本检查点（没有 grid_id）
            required_location_id = checkpoint.get('location', '')

            # 1. 如果有特殊要求（能力判定），必须通过
            if requires:
                required_ability = requires.get('ability')
                required_dc = requires.get('dc')
                if required_ability and required_dc:
                    if not action_result.get('success'):
                        result['reason'] = f"判定失败（需要DC {required_dc}）"
                        return result

            # 2. 检查地点（如果有要求）
            location_ok = True
            if required_location_id:
                current_loc = world_context.get('current_location', {})
                current_loc_id = current_loc.get('id', '')
                location_ok = (current_loc_id == required_location_id)

            # 3. 宽松的行动类型匹配
            action_type = analysis.get('action_type', '')
            action_ok = True  # 默认宽松

            # 只对明确的行动类型要求才检查
            if '对话' in description or '了解' in description or '汇报' in description:
                # 对话类检查点
                if action_type != 'dialogue':
                    action_ok = False
            elif '前往' in description:
                # 前往类检查点 - 任何行动都算（宽松）
                action_ok = True
            elif '搜寻' in description or '调查' in description:
                # 调查类检查点
                if action_type not in ['investigate', 'dialogue', 'other']:
                    action_ok = False
            elif '追踪' in description or '夺回' in description or '击败' in description:
                # 战斗类检查点
                if action_type not in ['combat', 'investigate']:
                    action_ok = False

            # 4. 综合判断
            if location_ok and action_ok:
                result['completed'] = True
                result['reason'] = f"完成了检查点：{description}"
            else:
                if not location_ok:
                    result['reason'] = f"需要前往指定地点"
                else:
                    result['reason'] = f"行动类型不符合要求"

            return result
