"""
业务逻辑层
处理核心业务逻辑，与框架无关
"""
import random
import hashlib
import requests
import json
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config
from database import UserDAO, ReadingDAO, CardDAO, ChatDAO

def convert_fortune_format(dify_data):
    """将 Dify 格式转换为前端期望的格式"""
    # 基础维度配置
    dimension_configs = {
        "事业运": {"icon": "fas fa-briefcase", "default_stars": 3},
        "财富运": {"icon": "fas fa-coins", "default_stars": 3},
        "爱情运": {"icon": "fas fa-heart", "default_stars": 3},
        "健康运": {"icon": "fas fa-heartbeat", "default_stars": 3},
        "贵人运": {"icon": "fas fa-hands-helping", "default_stars": 3}
    }
    
    # 构建维度数组
    dimensions = []
    dimension_advice = dify_data.get("dimension_advice", {})
    
    for name, config in dimension_configs.items():
        advice = dimension_advice.get(name, "")
        
        # 简单评分逻辑
        if any(word in advice for word in ["顺利", "良好", "助力", "极佳"]):
            stars = 4
            level = "良好"
        elif any(word in advice for word in ["稳步", "理性", "稳定"]):
            stars = 3
            level = "平稳"
        else:
            stars = 3
            level = "一般"
            
        dimensions.append({
            "name": name,
            "icon": config["icon"],
            "stars": stars,
            "level": level
        })
    
    # 计算总体评分
    avg_stars = sum(d["stars"] for d in dimensions) / len(dimensions)
    overall_score = int(avg_stars * 25)  # 转换为百分制
    
    if overall_score >= 80:
        overall_label = "大吉"
    elif overall_score >= 60:
        overall_label = "中吉"
    else:
        overall_label = "小吉"
    
    # 提取幸运元素
    lucky_elements = []
    do_list = dify_data.get("do", [])
    
    # 从建议中提取
    for item in do_list:
        if "西北" in item:
            lucky_elements.append({"name": "幸运方位", "icon": "fas fa-compass", "value": "西北"})
        if "银色" in item:
            lucky_elements.append({"name": "幸运颜色", "icon": "fas fa-palette", "value": "银色"})
        if "亥时" in item:
            lucky_elements.append({"name": "幸运时辰", "icon": "fas fa-clock", "value": "亥时"})
        if "8" in item:
            lucky_elements.append({"name": "幸运数字", "icon": "fas fa-hashtag", "value": "8"})
    
    # 默认幸运元素
    if not lucky_elements:
        lucky_elements = [
            {"name": "幸运颜色", "icon": "fas fa-palette", "value": "蓝色"},
            {"name": "幸运数字", "icon": "fas fa-hashtag", "value": "7"}
        ]
    
    return {
        "overall_score": overall_score,
        "overall_label": overall_label,
        "dimensions": dimensions,
        "lucky_elements": lucky_elements,
        "summary": dify_data.get("summary", "今日运势平稳，适合稳步前进。")
    }
    
class DateTimeService:
    """时间服务"""

    @staticmethod
    def get_beijing_date():
        """获取北京时间的日期"""
        beijing_tz = timezone(timedelta(hours=Config.TIMEZONE_OFFSET))
        return datetime.now(beijing_tz).date()

    @staticmethod
    def get_beijing_datetime():
        """获取北京时间的日期时间"""
        beijing_tz = timezone(timedelta(hours=Config.TIMEZONE_OFFSET))
        return datetime.now(beijing_tz)


class UserService:
    """用户服务"""

    @staticmethod
    def authenticate(username, password):
        """用户认证"""
        user = UserDAO.get_by_username(username)
        if user and check_password_hash(user['password_hash'], password):
            UserDAO.update_visit(user['id'])
            return user
        return None

    @staticmethod
    def register(username, password, device_id):
        """用户注册"""
        # 检查用户名是否存在
        if UserDAO.get_by_username(username):
            return None, "用户名已被使用"

        # 创建用户
        import uuid
        user_data = {
            'id': str(uuid.uuid4()),
            'username': username,
            'password_hash': generate_password_hash(password),
            'device_id': device_id
        }

        user = UserDAO.create(user_data)
        return user, None

    @staticmethod
    def generate_device_fingerprint(user_agent, accept_language):
        """生成设备指纹"""
        data = f"{user_agent}_{accept_language}"
        return hashlib.md5(data.encode()).hexdigest()


class TarotService:
    """塔罗牌服务"""

    @staticmethod
    def has_drawn_today(user_id, date):
        """检查用户今天是否已经抽过牌"""
        reading = ReadingDAO.get_today_reading(user_id, date)
        return reading is not None

    @staticmethod
    def draw_card():
        """抽取一张塔罗牌"""
        card = CardDAO.get_random()
        direction = random.choice(["正位", "逆位"])
        return card, direction

    @staticmethod
    def save_reading(user_id, date, card_id, direction):
        """保存占卜记录"""
        reading_data = {
            'user_id': user_id,
            'date': date,
            'card_id': card_id,
            'direction': direction
        }
        return ReadingDAO.create(reading_data)

    @staticmethod
    def get_today_reading(user_id, date):
        """获取今日占卜"""
        return ReadingDAO.get_today_reading(user_id, date)

    @staticmethod
    def get_user_stats(user_id):
        """获取用户统计信息"""
        total_readings = ReadingDAO.count_by_user(user_id)
        recent_readings = ReadingDAO.get_recent(user_id)
        return {
            'total_readings': total_readings,
            'recent_readings': recent_readings
        }

class ChatService:
    # 拟真的限制提示消息池
    LIMIT_MESSAGES = [
        "哎呀，我需要休息一下了，明天再来找我聊天吧～",
        "时间不早了，我要去冥想充电了，明天见！",
        "今天聊得很开心，但我的能量快用完了，明天再继续吧。",
        "月亮告诉我该休息了，期待明天与你的对话。",
        "塔罗牌需要时间恢复能量，我们明天再探索吧。"
    ]

    @staticmethod
    def can_start_chat(user_ref, session_id, is_guest=False):
        """检查是否可以开始聊天"""
        today = DateTimeService.get_beijing_date()
        limit = Config.CHAT_FEATURES['daily_limit_guest'] if is_guest else Config.CHAT_FEATURES['daily_limit_user']
        usage = ChatDAO.get_daily_usage(user_ref, session_id, today)
        return usage < limit, limit - usage

    @staticmethod
    def create_or_get_session(user_ref, session_id, card_info, date):
        """创建或获取聊天会话"""
        # 先查找现有会话
        existing = ChatDAO.get_session_by_date(user_ref, session_id, date)
        if existing:
            return existing

        # 创建新会话
        session_data = {
            'user_id': user_ref,
            'session_id': session_id,
            'card_id': card_info.get('card_id'),
            'card_name': card_info.get('name'),
            'card_direction': card_info.get('direction'),
            'date': date
        }
        return ChatDAO.create_session(session_data)

    @staticmethod
    def build_context(session_info, messages):
        """构建 AI 对话上下文"""
        context = {
            'card_name': session_info['card_name'],
            'card_direction': session_info['card_direction'],
            'date': session_info['date'].strftime('%Y-%m-%d'),
            'messages': []
        }

        # 只保留最近的 N 条消息作为上下文
        max_history = Config.CHAT_FEATURES['max_history_messages']
        recent_messages = messages[:max_history] if messages else []

        # 倒序排列（从旧到新）
        for msg in reversed(recent_messages):
            context['messages'].append({
                'role': msg['role'],
                'content': msg['content']
            })

        return context

    @staticmethod
    def process_message(session_id, user_message, user_ref, conversation_id=None):
        """处理用户消息并返回 AI 回复"""
        if not user_ref:
            raise ValueError("必须传入 user_ref（用户唯一标识）")

        # 获取会话信息
        session = ChatDAO.get_session_by_id(session_id)
        if not session:
            raise ValueError("会话不存在")

        # 保存用户消息
        ChatDAO.save_message({
            'session_id': session_id,
            'role': 'user',
            'content': user_message
        })

        # 增加使用次数
        today = DateTimeService.get_beijing_date()
        ChatDAO.increment_usage(
            user_id=user_ref,
            session_id=session_id,
            date=today
        )

        # 获取历史消息
        messages = ChatDAO.get_session_messages(session_id)

        # 构建上下文并调用 AI
        context = ChatService.build_context(session, messages)
        ai_response = DifyService.chat_tarot(
            user_message,
            context,
            user_ref=user_ref,
            conversation_id=conversation_id
        )

        # 保存 AI 回复
        ChatDAO.save_message({
            'session_id': session_id,
            'role': 'assistant',
            'content': ai_response.get("answer") if isinstance(ai_response, dict) else ai_response
        })

        return ai_response

        
class DifyService:
    """Dify AI 服务"""

    @staticmethod
    def generate_reading(card_name, direction, card_meaning="", user_ref=None):
        """生成塔罗解读"""
        prompt = f"""
        用户抽到了《{card_name}》这张牌，方向是{direction}。
        
        牌面意义：
        - {"正位" if direction == "正位" else "逆位"}含义：{card_meaning}
        
        请根据这张牌和方向，为用户生成今日洞察和具体指引。
        必须返回JSON格式，包含today_insight和guidance两个字段。
        """

        payload = {
            "inputs": {
        "card_name": card_name,      # 必填字段
        "direction": direction,
        "card_meaning": card_meaning
        },
            "response_mode": "blocking",
            "user": user_ref
        }

        headers = {
            "Authorization": f"Bearer {Config.DIFY_API_KEY}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                Config.DIFY_API_URL,
                json=payload,
                headers=headers,
                timeout=Config.DIFY_TIMEOUT
            )
            response.raise_for_status()

            # 解析响应
            data = response.json()
            answer = DifyService._extract_answer(data)

            if answer:
                return DifyService._parse_json_response(answer)

        except requests.exceptions.RequestException as e:
            print(f"Dify API error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

        # 返回默认值
        return {
            "today_insight": f"今日你抽到了{card_name}（{direction}），这张牌正在向你传递宇宙的信息。",
            "guidance": f"{'正位' if direction == '正位' else '逆位'}的{card_name}提醒你，要相信内心的声音。"
        }

    @staticmethod
    def _deterministic_uuid(*parts):
        """
        基于输入片段生成确定性的 UUID v5（合法 uuid 字符串，Dify 接受）。
        例：_deterministic_uuid(user_ref, date_str)
        """
        import uuid
        # 使用标准命名空间，保证是合法 UUID；name 保持稳定即可得到稳定 UUID
        name = "tarot|" + "|".join([str(p) for p in parts if p is not None])
        return str(uuid.uuid5(uuid.NAMESPACE_URL, name))

    @staticmethod
    def _build_history_snippet(context, max_turns=6, max_chars=1600):
        """
        从 context['messages'] 精简出最近若干轮的对话片段，避免请求过大。
        返回纯文本段，放进 system_prompt 中。
        """
        messages = (context or {}).get("messages", []) or []
        if not messages:
            return ""

        # 只取最近 max_turns 条（单条消息算一条，不是来回一轮）
        trimmed = messages[-max_turns:]

        def role_zh(role):
            if role == "user":
                return "用户"
            if role == "assistant":
                return "助手"
            return role or "未知"

        lines = []
        for m in trimmed:
            content = (m.get("content") or "").replace("\n", " ").strip()
            lines.append(f"{role_zh(m.get('role'))}: {content}")

        text = "\n".join(lines)
        # 若超长，仅保留尾部（最新部分）
        if len(text) > max_chars:
            text = text[-max_chars:]
        return text


    @staticmethod
    def chat_tarot(user_message, context, user_ref=None, conversation_id=None):
        """
        塔罗对话逻辑（Dify 会话管理）
        逻辑：
        - conversation_id 为空 → 新对话，传历史消息
        - conversation_id 不为空 → 续传会话，只传 conversation_id 和 user
        """
        today = DateTimeService.get_beijing_date().strftime('%Y-%m-%d')

        print("\n=== Dify Chat Debug ===")
        print(f"[Input] user_message: {user_message}")
        print(f"[Input] context: {json.dumps(context, ensure_ascii=False, indent=2)}")
        print(f"[Input] conversation_id: {conversation_id}")

        # 构建系统提示（新对话时使用）
        system_prompt = f"""你是一位专业的塔罗解读师。
用户今日抽到了《{context['card_name']}》（{context['card_direction']}）。
日期：{context['date']}

你的任务：
1. 基于用户抽到的塔罗牌，提供深入的解读和建议
2. 结合用户的具体问题，给出个性化的指导
3. 保持神秘而专业的语气，但要亲切友好
4. 不要偏离塔罗主题太远
5. 避免绝对性的预测，强调塔罗是指引而非命定

历史对话：
{json.dumps(context['messages'], ensure_ascii=False)}
"""

        payload = {
            "query": user_message,
            "response_mode": "blocking"
        }

        if conversation_id:
            # 已有会话，续传 conversation_id
            payload["conversation_id"] = conversation_id
            payload["user"] = user_ref
        else:
            # 新会话，传入系统提示和上下文
            payload["inputs"] = {
                "system_prompt": system_prompt,
                "card_name": context['card_name'],
                "card_direction": context['card_direction']
            }
            if user_ref:
                payload["user"] = user_ref

        print(f"[Payload] {json.dumps(payload, ensure_ascii=False, indent=2)}")

        headers = {
            "Authorization": f"Bearer {Config.DIFY_CHAT_API_KEY}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(
                Config.DIFY_CHAT_API_URL,
                json=payload,
                headers=headers,
                timeout=Config.DIFY_TIMEOUT
            )

            print(f"[Response] Status Code: {response.status_code}")
            print(f"[Response] Text: {response.text}")

            response.raise_for_status()
            data = response.json()

            # 从返回数据获取 conversation_id（新对话或续传都更新）
            new_conversation_id = data.get("conversation_id", conversation_id)
            print(f"[Success] conversation_id: {new_conversation_id}")

            # 提取回答
            answer = DifyService._extract_answer(data)
            if answer:
                return {"answer": answer, "conversation_id": new_conversation_id}
            else:
                return {"answer": "让我想想...这张牌对你的具体情况有特殊的启示。", "conversation_id": new_conversation_id}

        except requests.exceptions.RequestException as e:
            print(f"[Error] Request Exception: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[Error] Response Status: {e.response.status_code}")
                print(f"[Error] Response Body: {e.response.text}")
            return {"answer": "让我重新感受一下塔罗牌的能量，请稍后再试。", "conversation_id": conversation_id}

        except Exception as e:
            import traceback
            print(f"[Error] Unexpected Exception: {type(e).__name__}: {e}")
            traceback.print_exc()
            return {"answer": "星星暂时被云遮住了，请稍后再试。", "conversation_id": conversation_id}

        finally:
            print("=== End Dify Chat Debug ===\n")


    @staticmethod
    def _extract_answer(data):
        """从响应中提取答案"""
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], dict):
                outputs = data["data"].get("outputs", {})
                if isinstance(outputs, dict):
                    return outputs.get("text", "")
                elif isinstance(outputs, str):
                    return outputs
            elif "answer" in data:
                return data["answer"]
        return ""

    @staticmethod
    def _parse_json_response(text):
        """解析 JSON 响应"""
        # 尝试多种解析方式

        # 1. 直接解析
        try:
            return json.loads(text)
        except:
            pass

        # 2. 查找 ```json 块
        try:
            start = text.find("```json")
            if start != -1:
                end = text.find("```", start + 7)
                if end != -1:
                    json_str = text[start + 7:end].strip()
                    return json.loads(json_str)
        except:
            pass

        # 3. 查找 JSON 对象
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                json_str = text[start:end + 1]
                return json.loads(json_str)
        except:
            pass

        return None


class SessionService:
    """会话服务（处理访客逻辑）"""

    @staticmethod
    def save_guest_reading(session, card, direction, date):
        """保存访客占卜记录到会话"""
        session['last_card'] = {
            "card_id": card["id"],
            "name": card["name"],
            "image": card.get("image"),
            "meaning_up": card.get("meaning_up"),
            "meaning_rev": card.get("meaning_rev"),
            "direction": direction,
            "date": str(date),
            "timestamp": datetime.now().isoformat()
        }
        session.modified = True

    @staticmethod
    def get_guest_reading(session, date):
        """获取访客占卜记录"""
        last_card = session.get('last_card')
        if last_card and last_card.get("date") == str(date):
            return last_card
        return None

    @staticmethod
    def update_guest_insight(session, insight, guidance):
        """更新访客解读"""
        if 'last_card' in session:
            session['last_card']['today_insight'] = insight
            session['last_card']['guidance'] = guidance
            session.modified = True


class FortuneService:
    """运势服务 - 完整实现"""

    # 元素对应的幸运色
    ELEMENT_COLORS = {
        "火": ["红色", "橙色", "金色", "赤褐色"],
        "水": ["蓝色", "青色", "银色", "深蓝色"],
        "风": ["黄色", "白色", "浅蓝色", "淡紫色"],
        "土": ["绿色", "棕色", "深绿色", "土黄色"]
    }

    # 特殊事件文案
    SPECIAL_EVENT_MESSAGES = {
        "transformation": "死神牌带来转变的力量，旧的结束意味着新的开始",
        "breakthrough": "高塔时刻！突破性的改变即将到来",
        "perfect_day": "太阳照耀！今天是充满正能量的完美一天",
        "new_beginning": "愚者之旅开启，勇敢踏出第一步吧",
        "love_blessing": "爱神眷顾，感情运势达到巅峰",
        "valentine_lovers": "情人节遇见恋人牌，缘分天注定！",
        "morning_sun": "晨光中抽到太阳牌，一整天都会充满活力",
        "night_moon": "夜晚与月亮牌相遇，聆听内心的声音"
    }

    @staticmethod
    def calculate_fortune(card_id, card_name, direction, date, user_id=None):
        """
        计算完整的运势数据
        返回：包含所有运势信息的字典
        """
        from database import CardDAO

        # 1. 获取卡牌的能量数据
        card_data = CardDAO.get_by_id_with_energy(card_id)
        if not card_data:
            raise ValueError(f"Card not found: {card_id}")

        # 2. 提取基础能量值
        base_energies = [
            card_data.get('energy_career', 50),
            card_data.get('energy_wealth', 50),
            card_data.get('energy_love', 50),
            card_data.get('energy_health', 50),
            card_data.get('energy_social', 50)
        ]

        element = card_data.get('element', '土')
        special_effect = card_data.get('special_effect')

        # 3. 计算修正后的分数
        scores = FortuneService._calculate_scores(
            base_energies, direction, date, user_id
        )

        # 4. 转换为星级
        stars = FortuneService._scores_to_stars(scores)

        # 5. 生成幸运元素
        lucky_elements = FortuneService._generate_lucky_elements(
            element, date, user_id
        )

        # 6. 检查特殊事件
        special_events = FortuneService._check_special_events(
            card_name, special_effect, date
        )

        # 7. 构建维度数据
        dimensions = []
        dimension_names = ["事业运", "财富运", "爱情运", "健康运", "贵人运"]
        for i, name in enumerate(dimension_names):
            dimensions.append({
                "name": name,
                "score": scores[i],
                "stars": stars[i],
                "level": FortuneService._get_level(stars[i])
            })

        # 8. 计算总体分数
        overall_score = int(sum(scores) / len(scores))

        if overall_score >= 80:
            overall_label = "大吉"
        elif overall_score >= 60:
            overall_label = "中吉"
        else:
            overall_label = "小吉"

        # 9. 构建完整的运势数据
        fortune_data = {
            "card_id": card_id,
            "card_name": card_name,
            "direction": direction,
            "dimensions": dimensions,
            "lucky_elements": lucky_elements,
            "overall_score": overall_score,
            "overall_label": overall_label,
            "special_events": special_events,
            "element": element,
            "generated_at": datetime.now().isoformat()
        }

        return fortune_data

    @staticmethod
    def _calculate_scores(base_energies, direction, date, user_id):
        """计算修正后的分数"""
        # 生成稳定的随机种子
        seed_str = f"{direction}{date}{user_id or 'guest'}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        # 正逆位修正
        direction_modifier = 1.2 if direction == "正位" else 0.8

        # 日期波动（5-15%）
        daily_flux = [0.95 + rng.random() * 0.2 for _ in range(5)]

        # 计算最终分数
        scores = []
        for i, base in enumerate(base_energies):
            score = base * direction_modifier * daily_flux[i]
            # 确保在 0-100 范围内
            score = max(0, min(100, int(score)))
            scores.append(score)

        return scores

    @staticmethod
    def _scores_to_stars(scores):
        """将分数转换为星级（0.5-5星）"""
        stars = []
        for score in scores:
            if score >= 90:
                star = 5.0
            elif score >= 80:
                star = 4.5
            elif score >= 70:
                star = 4.0
            elif score >= 60:
                star = 3.5
            elif score >= 50:
                star = 3.0
            elif score >= 40:
                star = 2.5
            elif score >= 30:
                star = 2.0
            elif score >= 20:
                star = 1.5
            elif score >= 10:
                star = 1.0
            else:
                star = 0.5
            stars.append(star)
        return stars

    @staticmethod
    def _get_level(stars):
        """根据星级返回运势等级"""
        if stars >= 4.5:
            return "大吉"
        elif stars >= 3.5:
            return "中吉"
        elif stars >= 2.5:
            return "小吉"
        elif stars >= 1.5:
            return "平"
        else:
            return "需谨慎"

    @staticmethod
    def _generate_lucky_elements(element, date, user_id):
        """生成幸运元素"""
        # 使用日期和用户ID生成稳定的随机数
        seed_str = f"{element}{date}{user_id or 'guest'}_lucky"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        # 幸运色
        colors = FortuneService.ELEMENT_COLORS.get(element, ["紫色", "白色"])
        lucky_color = rng.choice(colors)

        # 幸运数字（1-9）
        lucky_number = rng.randint(1, 9)

        # 幸运时辰
        hours = [
            "子时(23-1时)", "丑时(1-3时)", "寅时(3-5时)",
            "卯时(5-7时)", "辰时(7-9时)", "巳时(9-11时)",
            "午时(11-13时)", "未时(13-15时)", "申时(15-17时)",
            "酉时(17-19时)", "戌时(19-21时)", "亥时(21-23时)"
        ]
        lucky_hour = rng.choice(hours)

        # 幸运方位
        directions = ["东", "南", "西", "北", "东南", "西南", "东北", "西北"]
        lucky_direction = rng.choice(directions)

        return {
            "color": lucky_color,
            "number": lucky_number,
            "hour": lucky_hour,
            "direction": lucky_direction
        }

    @staticmethod
    def _check_special_events(card_name, special_effect, date):
        """检查特殊事件和彩蛋"""
        events = []

        # 基础特殊效果
        if special_effect:
            events.append(special_effect)

        # 日期相关彩蛋
        current_time = DateTimeService.get_beijing_datetime()

        # 情人节 + 恋人牌
        if date.month == 2 and date.day == 14 and card_name in ["恋人", "The Lovers"]:
            events.append("valentine_lovers")

        # 月初 + 愚者
        if date.day == 1 and card_name in ["愚者", "The Fool"]:
            events.append("new_beginning")

        # 早晨 + 太阳
        if current_time.hour < 9 and card_name in ["太阳", "The Sun"]:
            events.append("morning_sun")

        # 夜晚 + 月亮
        if current_time.hour > 21 and card_name in ["月亮", "The Moon"]:
            events.append("night_moon")

        return events

    @staticmethod
    def _call_dify_fortune_api(card_name, prompt, user_ref=None):
        """调用运势专用的 Dify API（带详细调试日志，返回已解析的 dict 或 None）"""
        from config import Config
        import json
        import requests
        import traceback
        from datetime import datetime

        headers = {
            "Authorization": f"Bearer {Config.DIFY_FORTUNE_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "inputs": {
                "card_name": card_name,
                "query": prompt
            },
            "response_mode": "blocking",
            "user": user_ref
        }

        try:
            print("\n=== Calling Dify Fortune API ===")
            print(f"URL: {Config.DIFY_FORTUNE_API_URL}")
            print("Headers:", json.dumps(headers, ensure_ascii=False, indent=2))
            print("Payload:", json.dumps(payload, ensure_ascii=False, indent=2))

            resp = requests.post(
                Config.DIFY_FORTUNE_API_URL,
                json=payload,
                headers=headers,
                timeout=Config.DIFY_TIMEOUT,
            )

            print(f"[Dify] Response Status: {resp.status_code}")
            print(f"[Dify] Response Text: {resp.text}")

            # 如果响应码不是 2xx，会在这里抛出 HTTPError
            resp.raise_for_status()

            # 尝试解析 JSON
            data = resp.json()

            # 优先使用现有的抽取/解析工具（你项目里的 DifyService）
            try:
                text = DifyService._extract_answer(data)
            except Exception:
                text = None

            # 如果 extract 返回文本，尝试解析为 JSON（多种可能格式）
            if text:
                try:
                    parsed = DifyService._parse_json_response(text)
                    if isinstance(parsed, dict):
                        print("[Dify] Parsed response from extracted text.")
                        return parsed
                except Exception as e:
                    print(f"[Dify] Failed to parse extracted text: {e}")

            # 备选解析：直接检查常见字段（data.outputs / answer / outputs 列表等）
            try:
                # case: {"data": {"outputs": {"text": "..."} } }
                if isinstance(data, dict):
                    if "data" in data and isinstance(data["data"], dict):
                        outputs = data["data"].get("outputs")
                        # outputs is dict with text
                        if isinstance(outputs, dict):
                            txt = outputs.get("text") or outputs.get("content") or outputs.get("answer")
                            if txt:
                                parsed = DifyService._parse_json_response(txt) if isinstance(txt, str) else None
                                if isinstance(parsed, dict):
                                    print("[Dify] Parsed response from data.outputs dict.")
                                    return parsed
                        # outputs might be a list of chunks
                        if isinstance(outputs, list):
                            combined = []
                            for o in outputs:
                                if isinstance(o, dict):
                                    # try several keys
                                    candidate = o.get("text") or o.get("content") or o.get("answer")
                                    if candidate:
                                        combined.append(candidate)
                                elif isinstance(o, str):
                                    combined.append(o)
                            if combined:
                                combined_text = "\n".join(combined)
                                parsed = DifyService._parse_json_response(combined_text)
                                if isinstance(parsed, dict):
                                    print("[Dify] Parsed response from data.outputs list.")
                                    return parsed
                    # case: direct "answer" field
                    if "answer" in data and isinstance(data["answer"], (str, dict)):
                        if isinstance(data["answer"], dict):
                            return data["answer"]
                        else:
                            try:
                                parsed = DifyService._parse_json_response(data["answer"])
                                if isinstance(parsed, dict):
                                    return parsed
                            except:
                                pass
            except Exception as e:
                print(f"[Dify] Fallback parsing error: {e}")
                traceback.print_exc()

            # 如果上面都没有成功，记录原始返回以便排查
            print("[Dify] Unable to parse useful JSON from response. Raw response saved for debug.")
            print("Raw JSON:", json.dumps(data, ensure_ascii=False, indent=2))
            return None

        except requests.exceptions.HTTPError as e:
            print("HTTPError when calling Dify Fortune API:", e)
            if getattr(e, "response", None) is not None:
                print("HTTP Response Content:", e.response.text)
            print("Payload that caused error:", json.dumps(payload, ensure_ascii=False, indent=2))
            return None
        except Exception as e:
            print("Exception occurred while calling Dify Fortune API:", e)
            traceback.print_exc()
            print("Payload that caused exception:", json.dumps(payload, ensure_ascii=False, indent=2))
            return None


    @staticmethod
    def _call_dify_fortune_api(fortune_data, prompt):
        """
        调用 Dify 运势专用 API，传递所有必填字段
        fortune_data: dict, 包含 card_name, direction, overall_score 等
        prompt: str, LLM 提示词
        """
        from config import Config
        import json
        import requests
        import traceback
        from datetime import datetime

        # 构建 payload，保证必填字段都传
        payload = {
            "inputs": {
                "card_name": fortune_data.get("card_name", "未知牌"),
                "direction": fortune_data.get("direction", "正位"),
                "overall_score": str(fortune_data.get("overall_score", 50)),
                "dimensions": "\n".join(
                    f"{dim['name']}：{dim['stars']}星（{dim['level']}）"
                    for dim in fortune_data.get("dimensions", [])
                ),
                "lucky_color": fortune_data.get("lucky_elements", {}).get("color", ""),
                "lucky_number": str(fortune_data.get("lucky_elements", {}).get("number", "")),
                "lucky_hour": fortune_data.get("lucky_elements", {}).get("hour", ""),
                "lucky_direction": fortune_data.get("lucky_elements", {}).get("direction", ""),
                "special_messages": "\n".join(
                    FortuneService.SPECIAL_EVENT_MESSAGES.get(ev, "")
                    for ev in fortune_data.get("special_events", [])
                ),
                "query": prompt
            },
            "response_mode": "blocking",
            "user": f"fortune_{datetime.now().strftime('%Y-%m-%d')}"
        }

        headers = {
            "Authorization": f"Bearer {Config.DIFY_FORTUNE_API_KEY}",
            "Content-Type": "application/json"
        }

        try:
            print("\n=== Calling Dify Fortune API ===")
            print("Payload:", json.dumps(payload, ensure_ascii=False, indent=2))

            resp = requests.post(
                Config.DIFY_FORTUNE_API_URL,
                headers=headers,
                json=payload,
                timeout=Config.DIFY_TIMEOUT
            )
            print(f"[Dify] Status: {resp.status_code}, Response: {resp.text}")
            resp.raise_for_status()
            data = resp.json()

            text = DifyService._extract_answer(data)
            if text:
                parsed = DifyService._parse_json_response(text)
                if parsed:
                    print("[Dify] Parsed JSON:", json.dumps(parsed, ensure_ascii=False, indent=2))
                    return parsed

            print("[Dify] Failed to parse response, raw data:", json.dumps(data, ensure_ascii=False))
            return None

        except Exception as e:
            print("[Dify] Exception:", e)
            traceback.print_exc()
            return None


    @staticmethod
    def generate_fortune_text(fortune_data):
        """
        调用 Dify API 生成运势文案
        使用统一模板 {{变量}}
        """
        import json

        # 准备 prompt 模板
        try:
            dimensions_text = "\n".join(
                [f"{dim['name']}：{dim['stars']}星（{dim['level']}）" 
                 for dim in fortune_data.get("dimensions", [])]
            )
        except Exception:
            dimensions_text = ""

        special_messages_text = "\n".join(
            [FortuneService.SPECIAL_EVENT_MESSAGES.get(ev, "") 
             for ev in fortune_data.get("special_events", [])]
        )

        prompt = f"""
用户抽到塔罗牌：{{{{card_name}}}}（{{{{direction}}}}）
综合运势评分：{{{{overall_score}}}}/100

运势指数：
{{{{dimensions}}}}

幸运元素：
- 幸运色：{{{{lucky_color}}}}
- 幸运数字：{{{{lucky_number}}}}
- 幸运时辰：{{{{lucky_hour}}}}
- 幸运方位：{{{{lucky_direction}}}}

特殊提示：
{{{{special_messages}}}}

请根据以上信息生成：
1. 今日运势总评（50字以内）
2. 各维度的具体建议（每个维度30字以内）
3. 今日宜做的2件事
4. 今日忌做的2件事

要求：
- 结合塔罗牌含义和运势数据
- 语言积极正面，即使运势较低也要给出建设性建议
- 建议要具体可执行

返回 JSON 格式，字段：
- summary: 今日运势总评
- dimension_advice: 各维度建议
- do: 今日宜做
- dont: 今日忌做
"""

        # 调用 Dify API
        result = FortuneService._call_dify_fortune_api(fortune_data, prompt)

        # 解析结果
        if result and isinstance(result, dict):
            if all(k in result for k in ["summary", "dimension_advice", "do", "dont"]):
                fortune_data['fortune_text'] = result
            else:
                print("[FortuneService] Unexpected format, using default text.")
                fortune_data['fortune_text'] = FortuneService._generate_default_text(fortune_data)
        else:
            fortune_data['fortune_text'] = FortuneService._generate_default_text(fortune_data)

        return fortune_data


    @staticmethod
    def _generate_default_text(fortune_data):
        """生成默认的运势文案"""
        overall = fortune_data.get('overall_score', 50)

        if overall >= 80:
            summary = "今日运势极佳，万事皆宜，把握机会勇敢前行！"
            do_list = ["开展重要计划", "主动社交拓展人脉"]
            dont_list = ["过度谨慎错失良机", "独享成功忘记感恩"]
        elif overall >= 60:
            summary = "今日运势良好，稳中有进，适合循序渐进。"
            do_list = ["按计划推进事务", "保持积极心态"]
            dont_list = ["冒险激进", "忽视细节"]
        elif overall >= 40:
            summary = "今日运势平稳，宜守不宜攻，专注当下。"
            do_list = ["整理现有事务", "充电学习"]
            dont_list = ["开启新项目", "重大决策"]
        else:
            summary = "今日宜静养生息，调整状态，为明天蓄力。"
            do_list = ["休息放松", "反思总结"]
            dont_list = ["强行推进", "情绪化决定"]

        # 维度建议
        dimension_advice = {}
        for dim in fortune_data.get('dimensions', []):
            name = dim.get('name', '')
            stars = dim.get('stars', 3)
            advice = ""
            if name == "事业运":
                advice = "工作效率高，适合处理重要事务" if stars >= 4 else "按部就班，保持专注即可" if stars >= 3 else "避免重大决策，以观察为主"
            elif name == "财富运":
                advice = "财运亨通，投资理财好时机" if stars >= 4 else "收支平衡，理性消费" if stars >= 3 else "谨慎理财，避免大额支出"
            elif name == "爱情运":
                advice = "桃花朵朵，感情甜蜜" if stars >= 4 else "感情稳定，细水长流" if stars >= 3 else "多些理解，少些要求"
            elif name == "健康运":
                advice = "精力充沛，适合运动" if stars >= 4 else "身体无恙，保持作息" if stars >= 3 else "注意休息，避免劳累"
            elif name == "贵人运":
                advice = "贵人相助，把握机会" if stars >= 4 else "人际和谐，维护关系" if stars >= 3 else "低调行事，避免纷争"
            dimension_advice[name] = advice

        return {
            "summary": summary,
            "dimension_advice": dimension_advice,
            "do": do_list,
            "dont": dont_list
        }

    @staticmethod
    def save_fortune(user_id, date, fortune_data):
        """保存运势数据到数据库"""
        from database import ReadingDAO
        ReadingDAO.update_fortune(user_id, date, fortune_data)

    @staticmethod
    def get_fortune(user_id, date):
        """获取已保存的运势数据"""
        from database import ReadingDAO
        result = ReadingDAO.get_fortune(user_id, date)
        if result and result['fortune_data']:
            return result['fortune_data']
        return None
