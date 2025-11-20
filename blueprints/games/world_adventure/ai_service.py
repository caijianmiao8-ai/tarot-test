"""
AI 世界冒险游戏的 AI 服务层
支持多种 AI 提供商：OpenAI / Claude / Dify
"""
import os
import json
import requests


class AdventureAIService:
    """AI 服务统一接口"""

    @staticmethod
    def get_provider():
        """获取配置的 AI 提供商"""
        return os.getenv("ADVENTURE_AI_PROVIDER", "openrouter")  # 默认 OpenRouter

    @staticmethod
    def generate_world(template, world_name, user_prompt=None, stability=50, danger=50, mystery=50):
        """生成世界内容"""
        base_prompt = template.get('prompt_template', '')

        prompt = f"""你是一个专业的跑团 DM，正在为玩家生成一个冒险世界。

世界模板：{template['name']} ({template['description']})
世界名称：{world_name}
世界参数：稳定度 {stability}/100，危险度 {danger}/100，神秘度 {mystery}/100

{base_prompt}

玩家补充：{user_prompt if user_prompt else '无'}

请以 JSON 格式返回世界内容，包含：
{{
  "world_description": "世界的详细描述（100-200字）",
  "world_lore": "世界的背景故事和历史（150-300字）",
  "locations": [
    {{"name": "地点名", "type": "类型", "description": "描述"}}
  ],
  "factions": [
    {{"name": "势力名", "power": "影响力等级", "stance": "立场/目标"}}
  ],
  "npcs": [
    {{"name": "NPC名", "role": "身份", "personality": "性格", "secrets": "秘密/钩子"}}
  ]
}}

请直接返回 JSON，不要用 markdown 代码块。"""

        provider = AdventureAIService.get_provider()

        if provider == "openrouter":
            return AdventureAIService._call_openrouter(prompt)
        elif provider == "openai":
            return AdventureAIService._call_openai(prompt)
        elif provider == "claude":
            return AdventureAIService._call_claude(prompt)
        elif provider == "dify":
            return AdventureAIService._call_dify(prompt)
        else:
            # 默认降级方案
            return {
                "world_description": f"{world_name}是一个神秘的世界，等待勇敢的冒险者探索。",
                "world_lore": "关于这个世界的历史，还有许多未解之谜...",
                "locations": [],
                "factions": [],
                "npcs": []
            }

    @staticmethod
    def generate_dm_response_v2(world_context, character, player_action, conversation_history=None,
                                 action_result=None):
        """
        生成 DM 响应 (v2 - 使用完整世界上下文)

        world_context: 包含当前位置、NPC、任务等完整信息
        action_result: 骰子判定结果（如果有）
        """
        # 构建历史对话
        history_text = ""
        if conversation_history:
            history_text = "\n".join([
                f"{'DM' if msg['role'] == 'dm' else '玩家'}: {msg['content']}"
                for msg in conversation_history[-15:]  # 增加到15条
            ])

        # 构建世界信息
        world_info = f"""【世界背景】
世界名称：{world_context['world_name']}
世界传说：{world_context['world_lore'][:300]}"""

        # Phase 1: 网格信息（如果有）
        location_info = ""
        grid_constraint = ""
        current_grid = world_context.get('current_grid')

        if current_grid:
            # 使用网格数据构建位置信息
            connected_grids = current_grid.get('connected_grids', [])
            if isinstance(connected_grids, str):
                import json
                connected_grids = json.loads(connected_grids)

            interactive_objects = current_grid.get('interactive_objects', [])
            if isinstance(interactive_objects, str):
                interactive_objects = json.loads(interactive_objects)

            # 构建可前往的地点列表
            connections_text = ""
            if connected_grids:
                conn_list = [f"- {conn.get('direction', '')}：{conn.get('target_name', '')}"
                           for conn in connected_grids]
                connections_text = f"\n可前往：\n{chr(10).join(conn_list)}"

            # 构建可交互物体列表
            objects_text = ""
            if interactive_objects:
                obj_list = [f"- {obj.get('name', '')}：{obj.get('description', '')}"
                          for obj in interactive_objects[:5]]
                objects_text = f"\n可交互物体：\n{chr(10).join(obj_list)}"

            location_info = f"""
【📍 当前位置】
地点：{current_grid.get('grid_name', '')}
描述：{current_grid.get('description', '')}
氛围：{current_grid.get('atmosphere', '')}
光线：{current_grid.get('lighting', '')}{connections_text}{objects_text}"""

            # Phase 1: AI 约束指令（最重要） - 增强版
            # 明确列出存在的物品和NPC
            existing_objects = [obj.get('name', '') for obj in interactive_objects]
            nearby_npcs_temp = world_context.get('nearby_npcs', [])
            existing_npcs = [npc['npc_name'] for npc in nearby_npcs_temp] if nearby_npcs_temp else []

            objects_list_str = "、".join(existing_objects) if existing_objects else "无"
            npcs_list_str = "、".join(existing_npcs) if existing_npcs else "无"

            grid_constraint = f"""
🚫 **绝对约束 - 必须严格遵守** 🚫

【当前场景中存在的全部内容】
可交互物体：{objects_list_str}
在场人物：{npcs_list_str}

【禁止行为】
❌ 禁止创造不在上述列表中的物品、人物、线索
❌ 禁止提及纸条、痕迹、线索等不在列表中的东西
❌ 禁止编造商队、组织、事件等不在任务描述中的内容

【正确做法】
✓ 只描述上述列表中的物品和人物
✓ 如玩家调查周围，只描述【可交互物体】列表中的内容
✓ 如玩家找不到某物，明确告知「这里没有那样的东西」

【示例】
玩家：「调查周围」
错误回复：「你发现了焦黑的纸屑...」（❌ 不存在的物品）
正确回复：「你环顾四周，看到{objects_list_str}」（✓ 只描述实际存在的）
"""
        else:
            # Fallback: 旧版本位置信息
            current_loc = world_context.get('current_location')
            if current_loc:
                location_info = f"""
【当前位置】
地点：{current_loc['location_name']}
描述：{current_loc['description']}
危险等级：{current_loc.get('danger_level', 'unknown')}/10"""

        # 附近NPC信息（网格系统中包含活动信息）
        npcs_info = ""
        nearby_npcs = world_context.get('nearby_npcs', [])
        if nearby_npcs:
            if current_grid:
                # Phase 1: 使用网格中的活动信息
                npc_list = [f"- {npc['npc_name']} ({npc['role']})\n  活动：{npc.get('activity', '在此处')}\n  位置：{npc.get('position', '')}"
                           for npc in nearby_npcs[:5]]
            else:
                # Fallback: 旧版本
                npc_list = [f"- {npc['npc_name']} ({npc['role']}): {npc.get('personality', '')}"
                           for npc in nearby_npcs[:3]]
            npcs_info = f"""
【👥 附近的人物】
{chr(10).join(npc_list)}"""

        # 当前任务信息（强化版）
        quest_info = ""
        next_checkpoint = None
        checkpoint_requirement = ""
        current_quest = world_context.get('current_quest')
        quest_progress = world_context.get('quest_progress', {})

        if current_quest:
            checkpoints = current_quest.get('checkpoints', [])
            completed = quest_progress.get('checkpoints_completed', []) if quest_progress else []

            # 找到下一个未完成的检查点
            for cp in checkpoints:
                if cp.get('id') not in completed:
                    next_checkpoint = cp
                    break

            if next_checkpoint:
                # 构建检查点要求说明
                checkpoint_location = next_checkpoint.get('location', '')
                checkpoint_npc = next_checkpoint.get('npc', '')
                checkpoint_action = next_checkpoint.get('action', '')

                requirement_parts = []
                if checkpoint_location:
                    requirement_parts.append(f"前往{checkpoint_location}")
                if checkpoint_npc:
                    requirement_parts.append(f"与{checkpoint_npc}对话")
                if checkpoint_action:
                    requirement_parts.append(checkpoint_action)

                checkpoint_requirement = " → ".join(requirement_parts) if requirement_parts else next_checkpoint['description']

                quest_info = f"""
【🎯 当前任务 - 必须严格遵循】
任务名称：{current_quest['quest_name']}
任务描述：{current_quest.get('description', '')}
✅ 已完成：{len(completed)}/{len(checkpoints)} 个检查点
🔴 当前目标：{next_checkpoint['description']}
📍 完成条件：{checkpoint_requirement}
进度：{'▓' * len(completed)}{'░' * (len(checkpoints) - len(completed))}"""
            else:
                quest_info = f"""
【🎯 当前任务】
任务名称：{current_quest['quest_name']}
状态：✅ 所有检查点已完成！准备结束任务。"""

        # 角色信息
        character_info = f"""
【角色】
名字：{character.get('char_name')}
职业：{character.get('char_class')}
能力：⚔️战斗{character.get('ability_combat')}/10 | 💬社交{character.get('ability_social')}/10 | 🥷潜行{character.get('ability_stealth')}/10 | 📚知识{character.get('ability_knowledge')}/10 | 🏕️生存{character.get('ability_survival')}/10"""

        # 骰子判定结果（强化版 - 强制AI响应）
        dice_info = ""
        dice_enforcement = ""
        if action_result and action_result.get('requires_check'):
            dice_result = action_result.get('dice_result', {})
            level = dice_result.get('level', 'partial')

            dice_info = f"""
【🎲 判定结果 - 必须严格遵循】
{action_result.get('narrative', '')}
骰子：{dice_result.get('roll')} + {dice_result.get('modifier')} = {dice_result.get('total')} vs DC{dice_result.get('dc')}
结果：{level}"""

            # 根据成功等级给出强制性指令
            if level == 'critical':
                dice_enforcement = """
**⚠️ 大成功响应要求：**
- 必须描述令人印象深刻的成功场景
- 给予额外好处或发现
- NPC反应极为积极
"""
            elif level == 'success':
                dice_enforcement = """
**⚠️ 成功响应要求：**
- 描述行动顺利完成
- 达到预期效果
- 推进剧情
"""
            elif level == 'partial':
                dice_enforcement = """
**⚠️ 部分成功响应要求：**
- 描述行动勉强达成
- 但有小代价或并发症
- 例如：信息不完整、引起怀疑、消耗资源等
"""
            else:  # failure
                dice_enforcement = """
**⚠️ 失败响应要求：**
- 描述行动失败的具体情况
- 可能引起负面后果
- 但要给出其他尝试的机会
"""

        # 已探索的地点
        explored_info = ""
        discovered = world_context.get('discovered_locations', [])
        if discovered:
            loc_names = [loc['location_name'] for loc in discovered[:5]]
            explored_info = f"""
【已探索】
{', '.join(loc_names)}"""

        # 构建自然的 DM 引导
        dm_instruction = ""
        if next_checkpoint:
            dm_instruction = f"""
**你是经验丰富的 TRPG DM，正在主持一场引人入胜的冒险。**

【剧情当前重点】
{next_checkpoint['description']}

**你的任务：**
通过生动的叙述和自然的场景描写，引导玩家推进剧情。

**引导技巧（灵活运用，不要生硬）：**
- 让NPC的对话和行为透露线索
- 用环境细节和氛围暗示方向
- 通过事件的自然发展推动剧情

**核心原则：**
✓ 叙述要自然流畅，像在讲故事
✓ 根据骰子结果真实刻画成功/失败
✓ 保持世界的真实感和沉浸感
✗ 不要机械地列出"选项A/B/C"
✗ 不要生硬地提醒"当前目标是XX"
✗ 不要忽视玩家的实际行动
"""
        else:
            dm_instruction = """
**作为经验丰富的 DM，用生动的语言回应玩家：**

描述发生了什么，让世界鲜活起来。
通过叙述自然地展现接下来的可能性。
"""

        prompt = f"""{world_info}{location_info}{npcs_info}{quest_info}{character_info}{dice_info}{explored_info}

【最近对话】
{history_text if history_text else '(冒险刚刚开始)'}

【玩家行动】
{player_action}

---

{grid_constraint}

---

{dice_enforcement}{dm_instruction}

**回复格式要求**：
- 长度：150-250字
- 直接给出DM叙述，不要元信息
- 使用生动的场景描写
- 如果NPC说话，用引号："..."

DM回应："""

        provider = AdventureAIService.get_provider()

        if provider == "openrouter":
            return AdventureAIService._call_openrouter_chat(prompt)
        elif provider == "openai":
            return AdventureAIService._call_openai_chat(prompt)
        elif provider == "claude":
            return AdventureAIService._call_claude(prompt)
        elif provider == "dify":
            return AdventureAIService._call_dify(prompt)
        else:
            return f"(你执行了行动: {player_action[:50]}...)，周围的环境发生了一些变化..."

    @staticmethod
    def generate_dm_response(run, character, world, player_action, conversation_history=None):
        """生成 DM 响应 (v1 - 保持向后兼容)"""
        history_text = ""
        if conversation_history:
            history_text = "\n".join([
                f"{'DM' if msg['role'] == 'dm' else '玩家'}: {msg['content']}"
                for msg in conversation_history[-5:]
            ])

        prompt = f"""你是一个经验丰富的 TRPG DM，正在主持一场冒险。

【世界信息】
名称：{world.get('world_name')}
描述：{world.get('world_description', '')}
当前状态：稳定度 {world.get('stability')}/100，危险度 {world.get('danger')}/100

【角色信息】
名字：{character.get('char_name')}
职业：{character.get('char_class')}
能力：战斗 {character.get('ability_combat')}/10，社交 {character.get('ability_social')}/10，潜行 {character.get('ability_stealth')}/10，知识 {character.get('ability_knowledge')}/10，生存 {character.get('ability_survival')}/10

【任务信息】
标题：{run.get('run_title')}
目标：{run.get('mission_objective')}
当前回合：{run.get('current_turn')}/{run.get('max_turns')}

【最近对话】
{history_text if history_text else '(刚开始)'}

【玩家行动】
{player_action}

请作为 DM 回应玩家的行动：
1. 描述玩家行动的结果（成功/失败/部分成功）
2. 推进剧情，描述新的情况
3. 给玩家新的选择或挑战
4. 保持沉浸感和戏剧性

回复长度：100-200字。直接给出 DM 的叙述，不要元信息。"""

        provider = AdventureAIService.get_provider()

        if provider == "openrouter":
            return AdventureAIService._call_openrouter_chat(prompt)
        elif provider == "openai":
            return AdventureAIService._call_openai_chat(prompt)
        elif provider == "claude":
            return AdventureAIService._call_claude(prompt)
        elif provider == "dify":
            return AdventureAIService._call_dify(prompt)
        else:
            return f"(你执行了行动: {player_action[:50]}...)，周围的环境发生了一些变化..."

    # ========================================
    # OpenRouter API 调用
    # ========================================
    @staticmethod
    def _call_openrouter(prompt):
        """调用 OpenRouter API 生成 JSON"""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not configured")

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": os.getenv("SITE_URL", "https://ruoshuiclub.com"),
                    "X-Title": "AI World Adventure"
                },
                json={
                    "model": os.getenv("OPENROUTER_MODEL", "qwen/qwen-2.5-72b-instruct"),
                    "messages": [
                        {"role": "system", "content": "你是一个专业的 TRPG DM，擅长生成结构化的世界内容。请始终以纯 JSON 格式回复，不要使用 markdown 代码块。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.8,
                    "max_tokens": 2000,
                    "response_format": {"type": "json_object"}
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                # 尝试解析 JSON
                try:
                    return json.loads(content)
                except:
                    # 如果有 markdown 代码块，尝试提取
                    if '```json' in content:
                        start = content.index('```json') + 7
                        end = content.index('```', start)
                        content = content[start:end].strip()
                    elif '```' in content:
                        start = content.index('```') + 3
                        end = content.index('```', start)
                        content = content[start:end].strip()
                    return json.loads(content)
            else:
                print(f"OpenRouter API error: {response.status_code}, {response.text}")
                return None

        except Exception as e:
            print(f"OpenRouter API call failed: {e}")
            return None

    @staticmethod
    def _call_openrouter_chat(prompt):
        """调用 OpenRouter API 生成对话"""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not configured")

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": os.getenv("SITE_URL", "https://ruoshuiclub.com"),
                    "X-Title": "AI World Adventure"
                },
                json={
                    "model": os.getenv("OPENROUTER_MODEL", "qwen/qwen-2.5-72b-instruct"),
                    "messages": [
                        {"role": "system", "content": "你是一个经验丰富的 TRPG DM。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.9,
                    "max_tokens": 500
                },
                timeout=20
            )

            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                print(f"OpenRouter API error: {response.status_code}")
                return None

        except Exception as e:
            print(f"OpenRouter API call failed: {e}")
            return None

    # ========================================
    # OpenAI API 调用
    # ========================================
    @staticmethod
    def _call_openai(prompt):
        """调用 OpenAI API 生成 JSON"""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
                    "messages": [
                        {"role": "system", "content": "你是一个专业的 TRPG DM，擅长生成结构化的世界内容。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.8,
                    "max_tokens": 2000,
                    "response_format": {"type": "json_object"}  # 强制 JSON 输出
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                return json.loads(content)
            else:
                print(f"OpenAI API error: {response.status_code}, {response.text}")
                return None

        except Exception as e:
            print(f"OpenAI API call failed: {e}")
            return None

    @staticmethod
    def _call_openai_chat(prompt):
        """调用 OpenAI API 生成对话"""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
                    "messages": [
                        {"role": "system", "content": "你是一个经验丰富的 TRPG DM。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.9,
                    "max_tokens": 500
                },
                timeout=20
            )

            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                print(f"OpenAI API error: {response.status_code}")
                return None

        except Exception as e:
            print(f"OpenAI API call failed: {e}")
            return None

    # ========================================
    # Claude API 调用
    # ========================================
    @staticmethod
    def _call_claude(prompt):
        """调用 Claude API"""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": os.getenv("CLAUDE_MODEL", "claude-3-sonnet-20240229"),
                    "max_tokens": 2000,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                content = result['content'][0]['text']
                # 尝试解析 JSON
                try:
                    return json.loads(content)
                except:
                    return content
            else:
                print(f"Claude API error: {response.status_code}")
                return None

        except Exception as e:
            print(f"Claude API call failed: {e}")
            return None

    # ========================================
    # Dify API 调用（保留兼容）
    # ========================================
    @staticmethod
    def _call_dify(prompt):
        """调用 Dify API"""
        try:
            from services import DifyService
            response = DifyService.guided_chat(
                user_message=prompt,
                conversation_id=None,
                user_ref="world_gen",
                ai_personality='warm'
            )
            ai_text = response.get('answer', '{}')

            # 尝试提取 JSON
            if '```json' in ai_text:
                start = ai_text.index('```json') + 7
                end = ai_text.index('```', start)
                ai_text = ai_text[start:end].strip()
            elif '```' in ai_text:
                start = ai_text.index('```') + 3
                end = ai_text.index('```', start)
                ai_text = ai_text[start:end].strip()

            return json.loads(ai_text)
        except Exception as e:
            print(f"Dify API call failed: {e}")
            return None
