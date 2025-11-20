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
    def generate_dm_response(run, character, world, player_action, conversation_history=None):
        """生成 DM 响应"""
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
