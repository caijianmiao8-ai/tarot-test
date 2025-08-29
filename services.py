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

        # 9. 构建完整的运势数据
        fortune_data = {
            "card_id": card_id,
            "card_name": card_name,
            "direction": direction,
            "dimensions": dimensions,
            "lucky_elements": lucky_elements,
            "overall_score": overall_score,
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
    def _call_dify_fortune_api(prompt, api_key):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": {},
            "response_mode": "blocking",
            "user": f"fortune_user_{DateTimeService.get_beijing_date()}",
        }
        try:
            resp = requests.post(
                Config.DIFY_FORTUNE_API_URL,
                json=payload,
                headers=headers,
                timeout=Config.DIFY_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            text = DifyService._extract_answer(data)
            return DifyService._parse_json_response(text)
        except Exception as e:
            print(f"Dify Fortune API error: {e}")
            return None

    @staticmethod
    def generate_fortune_text(fortune_data, dify_api_key=None, workflow_id=None):
        """
        调用 Dify API 生成运势文案
        参数：
            fortune_data: 运势数据
            dify_api_key: 运势专用 API key（若不传则默认用 Config.DIFY_FORTUNE_API_KEY）
            workflow_id: 可选；你们当前用不到可不传
        """
        # —— 1. 组装 prompt（保留你原有逻辑） ——
        dimensions_text = [
            f"{dim['name']}：{dim['stars']}星（{dim['level']}）"
            for dim in fortune_data['dimensions']
        ]

        special_messages = []
        for event in fortune_data.get('special_events', []):
            if event in FortuneService.SPECIAL_EVENT_MESSAGES:
                special_messages.append(FortuneService.SPECIAL_EVENT_MESSAGES[event])

        prompt = f"""
塔罗牌：{fortune_data['card_name']}（{fortune_data['direction']}）
综合运势评分：{fortune_data['overall_score']}/100

运势指数：
{chr(10).join(dimensions_text)}

幸运元素：
- 幸运色：{fortune_data['lucky_elements']['color']}
- 幸运数字：{fortune_data['lucky_elements']['number']}
- 幸运时辰：{fortune_data['lucky_elements']['hour']}
- 幸运方位：{fortune_data['lucky_elements']['direction']}

{('特殊提示：' + chr(10).join(special_messages)) if special_messages else ''}

请根据以上信息生成：
1. 今日运势总评（50字以内）
2. 各维度的具体建议（每个维度30字以内）
3. 今日宜做的2件事
4. 今日忌做的2件事

要求：
- 结合塔罗牌含义和运势数据
- 语言积极正面，即使运势较低也要给出建设性建议
- 建议要具体可执行

返回JSON格式。
"""

        # —— 2. 选择调用通道（优先运势专用 API Key；workflow_id 可选） ——
        api_key = dify_api_key or Config.DIFY_FORTUNE_API_KEY
        result = None
        if api_key:
            result = FortuneService._call_dify_fortune_api(prompt, api_key)
        else:
            # fallback：走通用塔罗接口；这里不要再 import 自己本模块
            # 注意：generate_reading 的返回结构与期望不同，下面会做兜底转换
            result = DifyService.generate_reading(
                fortune_data['card_name'],
                fortune_data['direction'],
                card_meaning=""  # 不把整段 prompt 塞进 "牌义"
            )

        # —— 3. 结果兜底与结构统一 ——
        def _is_fortune_schema(obj):
            return isinstance(obj, dict) and all(
                k in obj for k in ("summary", "dimension_advice", "do", "dont")
            )

        if _is_fortune_schema(result):
            fortune_data['fortune_text'] = result
        elif isinstance(result, dict) and ("today_insight" in result or "guidance" in result):
            # 将通用解读结构转为运势结构（最小可用）
            fallback = FortuneService._generate_default_text(fortune_data)
            fallback["summary"] = result.get("today_insight", fallback["summary"])
            # 把 guidance 复用为每个维度的统一建议
            guidance = result.get("guidance", "")
            if guidance:
                fallback["dimension_advice"] = {
                    dim['name']: guidance for dim in fortune_data['dimensions']
                }
            fortune_data['fortune_text'] = fallback
        else:
            fortune_data['fortune_text'] = FortuneService._generate_default_text(fortune_data)

        return fortune_data

    @staticmethod
    def _generate_default_text(fortune_data):
        """生成默认的运势文案"""
        overall = fortune_data['overall_score']

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
        for dim in fortune_data['dimensions']:
            if dim['name'] == "事业运":
                if dim['stars'] >= 4:
                    advice = "工作效率高，适合处理重要事务"
                elif dim['stars'] >= 3:
                    advice = "按部就班，保持专注即可"
                else:
                    advice = "避免重大决策，以观察为主"
            elif dim['name'] == "财富运":
                if dim['stars'] >= 4:
                    advice = "财运亨通，投资理财好时机"
                elif dim['stars'] >= 3:
                    advice = "收支平衡，理性消费"
                else:
                    advice = "谨慎理财，避免大额支出"
            elif dim['name'] == "爱情运":
                if dim['stars'] >= 4:
                    advice = "桃花朵朵，感情甜蜜"
                elif dim['stars'] >= 3:
                    advice = "感情稳定，细水长流"
                else:
                    advice = "多些理解，少些要求"
            elif dim['name'] == "健康运":
                if dim['stars'] >= 4:
                    advice = "精力充沛，适合运动"
                elif dim['stars'] >= 3:
                    advice = "身体无恙，保持作息"
                else:
                    advice = "注意休息，避免劳累"
            elif dim['name'] == "贵人运":
                if dim['stars'] >= 4:
                    advice = "贵人相助，把握机会"
                elif dim['stars'] >= 3:
                    advice = "人际和谐，维护关系"
                else:
                    advice = "低调行事，避免纷争"

            dimension_advice[dim['name']] = advice

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
