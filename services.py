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
from database import UserDAO, ReadingDAO, CardDAO


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


class DifyService:
    """Dify AI 服务"""
    
    @staticmethod
    def generate_reading(card_name, direction, card_meaning=""):
        """生成塔罗解读"""
        prompt = f"""
        用户抽到了《{card_name}》这张牌，方向是{direction}。
        
        牌面意义：
        - {"正位" if direction == "正位" else "逆位"}含义：{card_meaning}
        
        请根据这张牌和方向，为用户生成今日洞察和具体指引。
        必须返回JSON格式，包含today_insight和guidance两个字段。
        """
        
        payload = {
            "inputs": {"query": prompt},
            "response_mode": "blocking",
            "user": f"tarot_user_{DateTimeService.get_beijing_date()}"
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