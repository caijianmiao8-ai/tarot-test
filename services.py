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
from database import UserDAO, ReadingDAO, CardDAO, ChatDAO, DatabaseManager, SpreadDAO, ShareDAO
import hmac, hashlib, base64, time

def _norm(s):  # 简易归一
    return (s or '').strip().lower()

def _depth_window(depth):
    if depth == 'short':   return (1, 3)
    if depth == 'medium':  return (4, 6)
    if depth == 'full':    return (7, 99)
    return (1, 10)

def _difficulty_rank(s):
    order = {'简单': 1, '普通': 2, '进阶': 3}
    return order.get(s, 2)

def _fit_bucket(val, target):
    # 完全命中1，邻近0.6，其他0.2
    return 1.0 if val == target else 0.6 if abs(val - target) == 1 else 0.2

def _special_rule_boost(name, desc, question):
    text = f"{name} {desc}".lower()
    q = (question or '').lower()
    boost = 0.0
    # 是/否
    if any(k in q for k in ['是否','能不能','要不要','可不可以','yes or no','yes/no']):
        if any(k in text for k in ['是否','yes','no']): boost += 1.0
    # 时间/时机
    if any(k in q for k in ['什么时候','多久','何时','时机','时间','未来几','近三月','时间线']):
        if any(k in text for k in ['时间','时机','流向','时间线']): boost += 0.8
    # 选择题
    if any(k in q for k in ['还是','两者','二选一','抉择','选择题']):
        if any(k in text for k in ['选择','抉择','二选一']): boost += 0.8
    # 关系/全景
    if any(k in q for k in ['他对我','关系','现状','阻碍','全貌','全景','综合']):
        if any(k in text for k in ['凯尔特','十字','马掌','关系','全景']): boost += 0.6
    return min(boost, 1.2)

def _sign_candidate_ids(spread_ids, user_ref):
    payload = json.dumps({
        'ids': spread_ids,
        'user': user_ref,
        'ts': int(time.time())
    }, ensure_ascii=False, separators=(',',':')).encode('utf-8')
    sig = hmac.new(Config.SECRET_KEY.encode('utf-8'), payload, hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(payload + b'.' + sig).decode('ascii')
    return token

def _verify_candidate_ids(token, max_age=1800):
    raw = base64.urlsafe_b64decode(token.encode('ascii'))
    payload, sig = raw.rsplit(b'.', 1)
    expect = hmac.new(Config.SECRET_KEY.encode('utf-8'), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expect):
        return None
    data = json.loads(payload.decode('utf-8'))
    if int(time.time()) - int(data.get('ts', 0)) > max_age:
        return None
    return data  # {'ids': [...], 'user': '...', 'ts': ...}

def _as_list(val):
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return list(val)
    if isinstance(val, dict):
        return [val]
    if isinstance(val, (bytes, bytearray)):
        try:
            return json.loads(val.decode("utf-8"))
        except:
            return []
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        try:
            return _as_list(json.loads(s))
        except:
            return []
    return []
    
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

class ShareService:
    @staticmethod
    def save_share_data(share_id: str, payload: dict):
        ShareDAO.save_share(
            share_id=share_id,
            user_id=payload.get("user_id"),
            user_name=payload.get("user_name"),
            reading=payload.get("reading") or {},
            fortune=payload.get("fortune") or {},
            created_at=payload.get("created_at") or datetime.utcnow(),
            expires_at=payload.get("expires_at") or (datetime.utcnow() + timedelta(days=30)),
        )

    @staticmethod
    def get_share_data(share_id: str):
        data = ShareDAO.get_share(share_id)
        if not data:
            return None
        # 过期检查
        exp = data.get("expires_at")
        if isinstance(exp, datetime) and exp < datetime.utcnow():
            return None
        return data

    @staticmethod
    def increment_view_count(share_id: str):
        ShareDAO.increment_view(share_id)

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
    def create_or_get_session(user_ref, session_id, card_info, date, ai_personality=None):
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
            'date': date,
            'ai_personality': ai_personality
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
    def process_message(session_id, user_message, user_ref, conversation_id=None, ai_personality=None):
        """处理用户消息并返回 AI 回复，同时保证 conversation_id 持久化"""
        if not user_ref:
            raise ValueError("必须传入 user_ref（用户唯一标识）")

        # 获取会话信息
        chat_session = ChatDAO.get_session_by_id(session_id)
        if not chat_session:
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
        context = ChatService.build_context(chat_session, messages)

        personality = ai_personality or chat_session.get('ai_personality', 'warm')

        ai_response = DifyService.chat_tarot(
            user_message,
            context,
            user_ref=user_ref,
            conversation_id=conversation_id or chat_session.get('conversation_id'),
            ai_personality=personality
        )

        # 提取 AI 返回的 conversation_id
        conv_id = None
        if isinstance(ai_response, dict):
            conv_id = ai_response.get("conversation_id")

        # 保存 conversation_id 到数据库 & session
        if conv_id and conv_id != chat_session.get('conversation_id'):
            from flask import session as flask_session
            flask_session['conversation_id'] = conv_id
            flask_session.modified = True

            with DatabaseManager.get_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        UPDATE chat_sessions
                        SET conversation_id = %s
                        WHERE id = %s
                    """, (conv_id, session_id))
                    conn.commit()

        # 保存 AI 回复
        ChatDAO.save_message({
            'session_id': session_id,
            'role': 'assistant',
            'content': ai_response.get("answer") if isinstance(ai_response, dict) else ai_response
        })

        return ai_response

class PersonaService:
    """
    将前端/URL里的 persona_id（UI别名）映射为 Dify 需要的 ai_personality（提示词风格名）。
    你可以把映射挪到数据库；此处给一个安全默认。
    """
    MAP = {
        "warm":   "warm",        # 温柔疗愈
        "wisdom": "wisdom",      # 理性分析
        "mystic": "mystic",      # 神秘直觉
        # 兼容中文别名（如有）
        "温柔疗愈": "warm",
        "理性分析": "wisdom",
        "神秘直觉": "mystic",
    }

    @staticmethod
    def resolve_ai(value: str | None) -> str:
        if not value:
            return "warm"
        key = str(value).strip()
        # 已经是 ai_personality 就直通；否则查映射；都查不到就用原值（允许自定义）
        return PersonaService.MAP.get(key, key)
                
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
    def guided_chat(user_message,
                    user_ref=None,
                    conversation_id=None,
                    ai_personality='warm',
                    phase=None,
                    **kwargs):
        """
        统一入口：把所有对话上下文透传到 Chatflow
        kwargs 可包含：spread_id / reading_id / question / candidate_set_id ...
        """
        # 组 inputs：最少有 ai_personality，其它有就带
        inputs = {"ai_personality": ai_personality}

        # phase 可选：不传或传 'auto' 时，不强控分支，让 Chatflow 自判
        if phase and phase != 'auto':
            inputs["phase"] = phase

        # 透传额外上下文
        for key in ("spread_id", "reading_id", "question", "candidate_set_id"):
            val = kwargs.get(key, None)
            if val is not None:
                inputs[key] = val

        payload = {
            "inputs": inputs,
            "query": user_message or "",
            "response_mode": "blocking"
        }
        if user_ref:
            payload["user"] = user_ref
        if conversation_id:
            payload["conversation_id"] = conversation_id

        headers = {
            "Authorization": f"Bearer {Config.DIFY_GUIDED_API_KEY}",
            "Content-Type": "application/json"
        }

        try:
            import requests, json
            if getattr(Config, "DIFY_DEBUG", False):
                print("\n=== Dify guided_chat Debug ===")
                print("URL:", Config.DIFY_GUIDED_API_URL)
                print("Headers:", json.dumps(headers, ensure_ascii=False))
                print("Payload:", json.dumps(payload, ensure_ascii=False))

            resp = requests.post(
                Config.DIFY_GUIDED_API_URL,
                json=payload,
                headers=headers,
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            answer = DifyService._extract_answer(data)
            new_cid = data.get("conversation_id", conversation_id)
            return {"answer": answer or "", "conversation_id": new_cid}
        except Exception as e:
            print(f"[Dify] guided_chat error: {e}")
            return {"answer": "抱歉，我这边信号有点弱，稍后再试试。", "conversation_id": conversation_id}

    @staticmethod
    def spread_initial_reading(spread_name, spread_description, question, cards, user_ref=None, ai_personality='warm'):
        """牌阵初始解读（新会话）"""
        # 构建牌阵描述
        cards_desc = []
        for i, card in enumerate(cards):
            cards_desc.append(
                f"位置{i+1} - {card['position_name']}（{card['position_meaning']}）：\n" +
                f"  {card['card_name']}（{card['direction']}）"
            )
        
        payload = {
            "inputs": {
                "spread_name": spread_name,
                "spread_description": spread_description,
                "question": question or "请给出整体指引",
                "cards_layout": "\n\n".join(cards_desc),
                "ai_personality": ai_personality
            },
            "query": "请根据这个牌阵给出深入的解读",
            "response_mode": "blocking",
            "user": user_ref
        }
        
        headers = {
            "Authorization": f"Bearer {Config.DIFY_SPREAD_API_KEY}",
            "Content-Type": "application/json"
        }
        
        try:
            print("\n=== Dify Spread Initial Reading Debug ===")
            print(f"URL: {Config.DIFY_SPREAD_API_URL}")
            print("Headers:", json.dumps(headers, ensure_ascii=False, indent=2))
            print("Payload:", json.dumps(payload, ensure_ascii=False, indent=2))

            response = requests.post(
                Config.DIFY_SPREAD_API_URL,
                json=payload,
                headers=headers,
                timeout=30
            )

            print(f"[Response] Status Code: {response.status_code}")
            print(f"[Response] Text: {response.text}")
            
            response.raise_for_status()
            data = response.json()
            
            # 提取回答和 conversation_id
            answer = DifyService._extract_answer(data)
            conversation_id = data.get("conversation_id")
            
            return {
                "answer": answer or "让我感受一下这个牌阵的能量...",
                "conversation_id": conversation_id
            }
            
        except Exception as e:
            print(f"Spread initial reading error: {e}")
            return {
                "answer": "牌阵的能量正在汇聚，请稍后再试...",
                "conversation_id": None
            }
    
    @staticmethod
    def spread_chat(user_message, user_ref=None, conversation_id=None, ai_personality='warm'):
        """牌阵对话（续聊，使用 conversation_id）"""
        payload = {
            "inputs": {
                "ai_personality": ai_personality
            },
            "query": user_message,
            "response_mode": "blocking",
            "user": user_ref
        }
        
        # 如果有 conversation_id，加入 payload
        if conversation_id:
            payload["conversation_id"] = conversation_id
        
        headers = {
            "Authorization": f"Bearer {Config.DIFY_SPREAD_API_KEY}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                Config.DIFY_SPREAD_API_URL,
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            answer = DifyService._extract_answer(data)
            new_conversation_id = data.get("conversation_id", conversation_id)
            
            return {
                "answer": answer or "让我想想...",
                "conversation_id": new_conversation_id
            }
            
        except Exception as e:
            print(f"Spread chat error: {e}")
            return {
                "answer": "抱歉，我需要重新连接能量场，请稍后再试。",
                "conversation_id": conversation_id
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
    def chat_tarot(user_message, context, user_ref=None, conversation_id=None, ai_personality='warm'):
        """
        塔罗对话逻辑（Dify 会话管理）
        改进：
        - 无论新对话还是续传，payload 都保证包含 inputs
        - 新对话传历史消息和系统提示
        - 续传会话也包含 user_message，避免 API 报错
        """
        today = DateTimeService.get_beijing_date().strftime('%Y-%m-%d')
    
        print("\n=== Dify Chat Debug ===")
        print(f"[Input] user_message: {user_message}")
        print(f"[Input] context: {json.dumps(context, ensure_ascii=False, indent=2)}")
        print(f"[Input] conversation_id: {conversation_id}")
    


        # payload 始终包含 inputs
        payload = {
            "inputs": {
                "card_name": context['card_name'],
                "card_direction": context['card_direction'],
                "history": context['messages'],
                "ai_personality": ai_personality
            },
            "query": user_message,
            "response_mode": "blocking"
        }

        # 续传会话加上 conversation_id 和 user
        if conversation_id:
            payload["conversation_id"] = conversation_id
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

            # 获取 conversation_id
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

# services.py 中新增 SpreadService 类

class SpreadService:
    """牌阵占卜服务"""
    

    
    # 每日占卜次数限制
    DAILY_SPREAD_LIMITS = {
        'guest': 1,
        'user': 3
    }
    
    # 每日对话次数限制（与普通塔罗对话共享）
    DAILY_CHAT_LIMITS = {
        'guest': 10,
        'user': 50
    }
    
    @staticmethod
    def can_divine_today(user_id, session_id, is_guest=True):
        """检查今日是否还能进行牌阵占卜"""
        today = DateTimeService.get_beijing_date()
        limit = SpreadService.DAILY_SPREAD_LIMITS['guest' if is_guest else 'user']
        
        # 获取今日占卜次数
        count = SpreadDAO.get_today_spread_count(user_id, session_id, today)
        return count < limit, limit - count
    
    
    @staticmethod
    def create_reading_fast(user_ref, session_id, spread_id, question, ai_personality='warm'):
        """
        仅抽牌+入库，不触发 LLM。status=init
        """
        import uuid, json, random
        spread_config = SpreadDAO.get_spread_by_id(spread_id)
        if not spread_config:
            raise ValueError(f"Invalid spread_id: {spread_id}")

        positions_raw = spread_config.get('positions')
        if isinstance(positions_raw, str):
            try:
                positions = json.loads(positions_raw)
            except Exception:
                positions = []
        elif isinstance(positions_raw, list):
            positions = positions_raw
        elif isinstance(positions_raw, dict):
            positions = [positions_raw[str(i)] for i in sorted(map(int, positions_raw.keys()))]
        else:
            positions = []

        card_count = int(spread_config['card_count'])
        all_cards = CardDAO.get_all()
        if len(all_cards) < card_count:
            raise ValueError("Not enough cards in database")
        selected_cards = random.sample(all_cards, card_count)

        cards_data = []
        for i, card in enumerate(selected_cards):
            direction = random.choice(["正位", "逆位"])
            cards_data.append({
                'position': i,
                'card_id': card['id'],
                'card_name': card['name'],
                'direction': direction,
                'image': card.get('image'),
                'meaning_up': card.get('meaning_up'),
                'meaning_rev': card.get('meaning_rev')
            })

        today = DateTimeService.get_beijing_date()
        reading_data = {
            'id': str(uuid.uuid4()),
            'user_id': user_ref,
            'session_id': session_id,
            'spread_id': spread_id,
            'cards': cards_data,
            'question': question or "",
            'ai_personality': ai_personality,
            'date': today,
            'status': 'init'
        }
        return SpreadDAO.create(reading_data)

    @staticmethod
    def can_chat_today(user_id, session_id, is_guest=True):
        """检查今日是否还能对话（包括普通塔罗和牌阵）"""
        today = DateTimeService.get_beijing_date()
        limit = SpreadService.DAILY_CHAT_LIMITS['guest' if is_guest else 'user']
        
        # 获取今日总对话次数（普通塔罗 + 牌阵对话）
        normal_chat_count = ChatDAO.get_daily_usage(user_id, session_id, today)
        spread_chat_count = SpreadDAO.get_today_chat_count(user_id, session_id, today)
        total_count = normal_chat_count + spread_chat_count
        
        return total_count < limit, limit - total_count
    
    @staticmethod
    def perform_divination(user_ref, session_id, spread_id, question, ai_personality='warm'):
        """执行牌阵占卜"""
        import uuid
        print("[Draw] begin perform_divination", user_ref, session_id, spread_id)
        # 从数据库获取牌阵配置
        spread_config = SpreadDAO.get_spread_by_id(spread_id)
        if not spread_config:
            raise ValueError(f"Invalid spread_id: {spread_id}")
        print("[Draw] spread_config loaded:", bool(spread_config))
        # 解析位置信息（兼容 str / list / dict）
        positions_raw = spread_config.get('positions')
        if isinstance(positions_raw, str):
            try:
                positions = json.loads(positions_raw)
            except Exception as e:
                print(f"[Error] Failed to parse positions JSON: {positions_raw}, error: {e}")
                positions = []
        elif isinstance(positions_raw, list):
            positions = positions_raw
        elif isinstance(positions_raw, dict):
            positions = [positions_raw[str(i)] for i in sorted(map(int, positions_raw.keys()))]
        else:
            positions = []

        card_count = int(spread_config['card_count'])

        all_cards = CardDAO.get_all()
        if len(all_cards) < card_count:
            raise ValueError("Not enough cards in database")

        selected_cards = random.sample(all_cards, card_count)

        # 构建牌数据
        cards_data = []
        for i, card in enumerate(selected_cards):
            direction = random.choice(["正位", "逆位"])
            cards_data.append({
                'position': i,
                'card_id': card['id'],
                'card_name': card['name'],
                'direction': direction,
                'image': card.get('image'),
                'meaning_up': card.get('meaning_up'),
                'meaning_rev': card.get('meaning_rev')
            })
        print("[Draw] cards_data len:", len(cards_data))    

        # 创建占卜记录
        today = DateTimeService.get_beijing_date()
        reading_data = {
            'id': str(uuid.uuid4()),
            'user_id': user_ref,
            'session_id': session_id,
            'spread_id': spread_id,
            'cards': cards_data,
            'question': question,
            'ai_personality': ai_personality,
            'date': today
        }

        try:
            reading = SpreadDAO.create(reading_data)
            print("[Draw] DB insert ok, reading_id:", reading['id'])
        except Exception as e:
            import traceback
            print("[Draw][DB ERROR]", e)
            traceback.print_exc()
            raise  # 让上层捕获并返回 500

        try:
            print("[Draw] gen initial interpretation start")
            initial = SpreadService.generate_initial_interpretation(reading['id'], ai_personality)
            print("[Draw] gen initial interpretation ok, conv_id:", initial.get('conversation_id'))
        except Exception as e:
            import traceback
            print("[Draw][GEN ERROR]", e)
            traceback.print_exc()
            # 不 raise 也行，但建议抛给上层，前端能看到明确错误
            raise

        return reading

    @staticmethod    
    def generate_initial_interpretation(reading_id, ai_personality):
        print("[Init] start, reading_id:", reading_id)
        reading = SpreadDAO.get_by_id(reading_id)
        print("[Init] reading loaded:", bool(reading))

        spread_config = SpreadDAO.get_spread_by_id(reading['spread_id'])
        print("[Init] spread loaded:", bool(spread_config))

        # 解析位置信息
        positions_raw = spread_config.get('positions')
        if isinstance(positions_raw, str):
            try:
                positions = json.loads(positions_raw)
            except Exception as e:
                print(f"[Error] Failed to parse positions JSON: {positions_raw}, error: {e}")
                positions = []
        elif isinstance(positions_raw, list):
            positions = positions_raw
        elif isinstance(positions_raw, dict):
            positions = [positions_raw[str(i)] for i in sorted(map(int, positions_raw.keys()))]
        else:
            positions = []

        cards = json.loads(reading['cards']) if isinstance(reading['cards'], str) else reading['cards']

        # 构建牌阵详细信息
        cards_desc = []
        for card in cards:
            position = positions[card['position']] if card['position'] < len(positions) else {"name": "未知", "meaning": ""}
            cards_desc.append({
                'position_name': position['name'],
                'position_meaning': position['meaning'],
                'card_name': card['card_name'],
                'direction': card['direction']
            })

        # 打印调试日志
        print("\n=== Spread Initial Reading Debug ===")
        print(f"Spread Name: {spread_config['name']}")
        print(f"Spread Description: {spread_config['description']}")
        print("Cards Desc:", json.dumps(cards_desc, ensure_ascii=False, indent=2))

        print("[Init] calling DifyService.spread_initial_reading ...")
        # 调用 Dify，开始新会话
        response = DifyService.spread_initial_reading(
            spread_name=spread_config['name'],
            spread_description=spread_config['description'],
            question=reading.get('question', ''),
            cards=cards_desc,
            user_ref=reading['user_id'],
            ai_personality=ai_personality
        )
        print("[Init] Dify returned, conv_id:", response.get("conversation_id"))
        
        # 保存初始解读和 conversation_id
        SpreadDAO.update_initial_interpretation(reading_id, response['answer'])
        if response.get('conversation_id'):
            SpreadDAO.update_conversation_id(reading_id, response['conversation_id'])

        # 保存为第一条消息
        SpreadDAO.save_message({
            'reading_id': reading_id,
            'role': 'assistant',
            'content': response['answer']
        })

        return response
    
    @staticmethod
    def process_chat_message(reading_id, user_message, user_ref):
        """处理牌阵对话消息（使用 conversation_id，不传历史记录）"""
        reading = SpreadDAO.get_by_id(reading_id)
        if not reading:
            raise ValueError("Reading not found")
        
        # 保存用户消息
        SpreadDAO.save_message({
            'reading_id': reading_id,
            'role': 'user',
            'content': user_message
        })
        
        # 增加对话次数
        today = DateTimeService.get_beijing_date()
        SpreadDAO.increment_chat_usage(
            user_id=user_ref,
            session_id=reading['session_id'],
            date=today
        )
        
        # 调用 Dify（使用 conversation_id 续聊）
        response = DifyService.spread_chat(
            user_message=user_message,
            user_ref=user_ref,
            conversation_id=reading.get('conversation_id'),
            ai_personality=reading.get('ai_personality', 'warm')
        )
        
        # 更新 conversation_id（如果变化）
        if response.get('conversation_id') and response['conversation_id'] != reading.get('conversation_id'):
            SpreadDAO.update_conversation_id(reading_id, response['conversation_id'])
        
        # 保存 AI 回复
        SpreadDAO.save_message({
            'reading_id': reading_id,
            'role': 'assistant',
            'content': response['answer']
        })
        
        return response
    
    @staticmethod
    def get_reading(reading_id):
        """获取占卜记录详情"""
        reading = SpreadDAO.get_by_id(reading_id)
        if reading and reading.get('cards'):
            reading['cards'] = json.loads(reading['cards']) if isinstance(reading['cards'], str) else reading['cards']
        return reading
    
    @staticmethod
    def get_chat_messages(reading_id):
        """获取对话历史（仅用于前端展示）"""
        messages = SpreadDAO.get_all_messages(reading_id)
        return [
            {'role': msg['role'], 'content': msg['content']}
            for msg in messages
        ] if messages else []

    @staticmethod
    def get_card_at(reading_id, index: int):
        """
        读取既有 reading.cards 的第 index 张，并补充该位置的位置信息（name/meaning）。
        """
        reading = SpreadDAO.get_by_id(reading_id)
        if not reading:
            raise ValueError("reading not found")

        # 归一化 cards
        cards = reading.get('cards') or []
        if isinstance(cards, str):
            import json
            try:
                cards = json.loads(cards) or []
            except Exception:
                cards = []

        if index < 0 or index >= len(cards):
            raise IndexError("card index out of range")

        card = dict(cards[index])  # 复制以免副作用

        # 取 positions
        spread = SpreadDAO.get_spread_by_id(reading['spread_id'])
        positions = (spread or {}).get('positions') or []
        pos = positions[index] if index < len(positions) else {"index": index, "name": f"位置{index+1}", "meaning": ""}

        card['position_info'] = {
            "index": pos.get("index", index),
            "name": pos.get("name", f"位置{index+1}"),
            "meaning": pos.get("meaning", "")
        }
        return card

    @staticmethod
    def reveal_card(reading_id, index: int):
        """
        揭示一张卡：返回卡信息，并以 system 角色落一条“揭示日志”到 spread_messages。
        """
        card = SpreadService.get_card_at(reading_id, index)
        # 记录系统消息（便于后续回溯）
        name = card.get('card_name') or '未知牌'
        direction = card.get('direction') or ''
        pos = card.get('position_info', {})
        pos_name = pos.get('name') or f"位置{index+1}"
        log = f"【揭示】{pos_name}：{name}（{direction}）"
        SpreadDAO.save_message({
            "reading_id": reading_id,
            "role": "system",
            "content": log
        })
        return card

    @staticmethod
    def create_guided_reading(user_ref, session_id, spread_id, question, ai_personality='warm'):
        """
        引导模式下创建 reading：只抽牌+入库，不触发 LLM。
        直接复用 create_reading_fast。
        """
        return SpreadService.create_reading_fast(
            user_ref=user_ref,
            session_id=session_id,
            spread_id=spread_id,
            question=question,
            ai_personality=ai_personality
        )

    @staticmethod
    def suggest_spreads(user_ref, topic, depth, difficulty, question, avoid_recent_user_id=None, topn=3):
        # 1) 映射 depth -> card_count 区间
        min_c, max_c = _depth_window(depth or 'short')

        # 2) 取初筛候选
        cands = SpreadDAO.suggest_candidates(
            topic=topic or None,
            min_cards=min_c, max_cards=max_c,
            max_difficulty=difficulty or None
        )
        if not cands:
            # 兜底：不限制长度与难度，仅按 category=topic|通用
            cands = SpreadDAO.suggest_candidates(topic=topic)

        if not cands:
            return {'candidate_set_id': _sign_candidate_ids([], user_ref), 'items': []}

        ids = [c['id'] for c in cands]
        pop = SpreadDAO.get_popularity(ids, days=30)
        recent = SpreadDAO.used_recently(avoid_recent_user_id, ids, days=14) if avoid_recent_user_id else set()

        # 3) 打分
        # 归一化人气
        max_pop = max(pop.values()) if pop else 0
        def norm_pop(x): 
            return (pop.get(x, 0) / max_pop) if max_pop else 0.0

        depth_target = 1 if max_c<=3 else 2 if max_c<=6 else 3
        w = dict(topic=0.30, depth=0.20, diff=0.15, rule=0.20, sim=0.10, pop=0.10, repeat=0.25)

        scored = []
        for s in cands:
            topic_fit = 1.0 if _norm(s['category']) == _norm(topic) else (0.6 if _norm(s['category'])=='通用' else 0.2)
            depth_fit = _fit_bucket( 1 if s['card_count']<=3 else 2 if s['card_count']<=6 else 3, depth_target)
            diff_fit = _fit_bucket(_difficulty_rank(s['difficulty']), _difficulty_rank(difficulty or '简单'))
            rule = _special_rule_boost(s['name'], s.get('description',''), question or '')
            sim = 0.0  # 如需，可接 pg_trgm 相似度结果（此处先置 0）
            p = norm_pop(s['id'])
            rep = 1.0 if s['id'] in recent else 0.0

            score = w['topic']*topic_fit + w['depth']*depth_fit + w['diff']*diff_fit + \
                    w['rule']*rule + w['sim']*sim + w['pop']*p - w['repeat']*rep

            scored.append((score, s))

        scored.sort(key=lambda x: x[0], reverse=True)
        items = [
            {
              'spread_id': s['id'],
              'spread_name': s['name'],
              'card_count': s['card_count'],
              'purpose': s.get('description','')[:60],
              'difficulty': s['difficulty'],
              'category': s['category'],
              'score': round(score, 3)
            }
            for score, s in scored[:max(topn, 2)]
        ]

        token = _sign_candidate_ids([it['spread_id'] for it in items], user_ref)
        return {'candidate_set_id': token, 'items': items}

    @staticmethod
    def verify_candidate_and_create(user_ref, session_id, spread_id, question, ai_personality, candidate_set_id):
        data = _verify_candidate_ids(candidate_set_id or '')
        if not data or spread_id not in set(data.get('ids', [])):
            raise ValueError('spread not in last candidate set')
        # 进入你已有的创建流程（只抽牌+入库）
        return SpreadService.create_reading_fast(
            user_ref=user_ref,
            session_id=session_id,
            spread_id=spread_id,
            question=question,
            ai_personality=ai_personality
        )

    @staticmethod
    def resolve_spreads_from_llm(user_ref, normalized, recommended, question, topn=3):
        """
        根据 LLM 推断（名称/别名/标签/张数范围+normalized 偏好）从数据库挑选候选并打分。
        只返回 DB 中真实存在的牌阵，并签名 candidate_set_id。
        """
        topic = (normalized or {}).get('topic') or None
        depth = (normalized or {}).get('depth') or None
        difficulty = (normalized or {}).get('difficulty') or None
        min_cards, max_cards = _depth_window(depth)

        # 1) DB 初筛（只从库里取）
        cands = SpreadDAO.suggest_candidates(
            topic=topic,
            min_cards=min_cards,
            max_cards=max_cards,
            max_difficulty=difficulty
        )

        if not cands:
            # 兜底：只按 topic/通用再取一次
            cands = SpreadDAO.suggest_candidates(topic=topic)

        # 2) 把 LLM 推荐整理为易用的匹配词
        #    names/aka/tags 全部小写，min/max_cards 做容差
        recs = []
        for r in (recommended or []):
            try:
                nm = (r.get('name') or '').strip().lower()
                aka = [s.strip().lower() for s in (r.get('aka') or []) if s]
                tgs = [s.strip().lower() for s in (r.get('tags') or []) if s]
                rmin = int(r.get('min_cards') or 0) or None
                rmax = int(r.get('max_cards') or 0) or None
                why = (r.get('why') or '').strip()
                conf = float(r.get('confidence') or 0.0)
                recs.append({'name': nm, 'aka': aka, 'tags': tgs, 'min': rmin, 'max': rmax, 'why': why, 'conf': conf})
            except Exception:
                continue

        # 3) 评分
        w = dict(topic=0.30, depth=0.20, diff=0.15, rule=0.20, name=0.15, pop=0.00, repeat=0.00)
        scored = []

        def _depth_bucket(n):
            return 1 if n <= 3 else 2 if n <= 6 else 3

        depth_target = _depth_bucket(max_cards)

        for s in cands:
            s_name = (s['name'] or '')
            s_name_l = s_name.lower()
            s_desc = (s.get('description') or '')
            s_cat  = (s.get('category') or '')
            s_cnt  = int(s.get('card_count') or 0)
            s_diff = (s.get('difficulty') or '')

            # 主题匹配
            topic_fit = 1.0 if (topic and s_cat == topic) else (0.6 if s_cat == '通用' else (0.2 if topic else 0.8))

            # 深度匹配
            depth_fit = 1.0 if _depth_bucket(s_cnt) == depth_target else 0.6 if abs(_depth_bucket(s_cnt) - depth_target) == 1 else 0.2

            # 难度匹配
            diff_fit = 1.0
            user_rank = _difficulty_rank(difficulty or '简单')
            s_rank    = _difficulty_rank(s_diff)
            if s_rank - user_rank == 1:
                diff_fit = 0.5
            elif s_rank - user_rank >= 2:
                diff_fit = 0.0

            # 名称/标签命中（只在 LLM 提供的推荐里找，不编造）
            name_hit = 0.0
            if recs:
                for r in recs:
                    if r['name'] and r['name'] in s_name_l:
                        name_hit = max(name_hit, 1.0 * (0.7 + 0.3 * r['conf']))
                    for alias in r['aka']:
                        if alias and alias in s_name_l:
                            name_hit = max(name_hit, 0.8 * (0.7 + 0.3 * r['conf']))
                    # 张数范围软匹配（允许±1）
                    if r['min'] and s_cnt < r['min'] - 1:
                        name_hit *= 0.8
                    if r['max'] and s_cnt > r['max'] + 1:
                        name_hit *= 0.8

            # 特殊规则：根据 question 内容加权（不越界）
            rule = _special_rule_boost(s_name, s_desc, question)

            score = w['topic']*topic_fit + w['depth']*depth_fit + w['diff']*diff_fit + \
                    w['rule']*rule + w['name']*name_hit

            scored.append((score, s, name_hit))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_items = []
        for score, s, name_hit in scored[:max(topn, 2)]:
            # 生成 why：优先用 LLM 的 why（若命中），否则根据匹配维度拼接
            why = ""
            if recs:
                for r in recs:
                    if r['name'] and r['name'] in (s['name'] or '').lower() and r['why']:
                        why = r['why']; break
            if not why:
                parts = []
                if topic and s.get('category') == topic:
                    parts.append("主题契合")
                if abs(_depth_bucket(int(s.get('card_count') or 0)) - depth_target) == 0:
                    parts.append("张数匹配")
                if name_hit >= 0.8:
                    parts.append("与推断名称/别名相符")
                if _special_rule_boost(s['name'], s.get('description',''), question) >= 0.8:
                    parts.append("针对你的问题类型更合适")
                why = "、".join(parts) or "综合匹配较好"

            top_items.append({
                "spread_id": s['id'],
                "spread_name": s['name'],
                "card_count": int(s.get('card_count') or 0),
                "tags": [s.get('category') or '', s.get('difficulty') or ''],
                "why": why,
                "score": round(float(score), 3)
            })

        token = _sign_candidate_ids([it['spread_id'] for it in top_items], user_ref)
        return {"candidate_set_id": token, "items": top_items}

    @staticmethod
    def verify_candidate_membership(candidate_set_id: str, spread_id: str, user_ref: str, max_age: int = 1800):
        data = _verify_candidate_ids(candidate_set_id or '', max_age=max_age)
        if not data:
            return False, 'candidate_set_invalid_or_expired'
        if data.get('user') != user_ref:
            return False, 'candidate_set_user_mismatch'
        ids = set(data.get('ids') or [])
        if spread_id not in ids:
            return False, 'spread_not_in_candidate_set'
        return True, None