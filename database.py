"""
数据库管理模块
支持 Vercel（每次新建连接）和传统部署（连接池）
"""
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from config import Config
import json
import traceback
from psycopg2.extras import Json


def _normalize_json_list(val):
    """把 val 归一化为 list，用于 JSON/JSONB/TEXT 混存的字段"""
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return list(val)
    if isinstance(val, dict):
        return [val]
    if isinstance(val, (bytes, bytearray)):
        try:
            return json.loads(val.decode("utf-8"))
        except Exception:
            return []
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            return _normalize_json_list(parsed)
        except Exception:
            return []
    return []


class DatabaseManager:
    """数据库管理器"""

    _pool = None

    @classmethod
    def init_pool(cls):
        """初始化连接池（仅在非 Vercel 环境使用）"""
        if not Config.IS_VERCEL and not cls._pool:
            from psycopg2 import pool
            db_config = Config.get_db_config()
            cls._pool = pool.SimpleConnectionPool(
                1,
                db_config["pool_size"],
                db_config["dsn"],
                cursor_factory=psycopg2.extras.RealDictCursor
            )

    @classmethod
    def get_connection(cls):
        """获取数据库连接"""
        if Config.IS_VERCEL:
            # Vercel: 每次创建新连接
            return psycopg2.connect(
                Config.DATABASE_URL,
                cursor_factory=psycopg2.extras.RealDictCursor,
                sslmode="require"
            )
        else:
            # 传统部署: 使用连接池
            cls.init_pool()
            return cls._pool.getconn()

    @classmethod
    def return_connection(cls, conn):
        """归还连接到连接池"""
        if not Config.IS_VERCEL and cls._pool:
            cls._pool.putconn(conn)
        else:
            conn.close()

    @classmethod
    @contextmanager
    def get_db(cls):
        """上下文管理器，自动处理连接的获取和释放"""
        conn = cls.get_connection()
        try:
            yield conn
        finally:
            cls.return_connection(conn)


# =========================
#        SpreadDAO
# =========================
class SpreadDAO:
    """牌阵数据访问对象"""

    @staticmethod
    def get_all_spreads():
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, name, description, card_count, positions, category, difficulty
                    FROM spreads 
                    ORDER BY difficulty, card_count
                """)
                spreads = cursor.fetchall()
                for spread in spreads:
                    spread['positions'] = _normalize_json_list(spread.get('positions'))
                return spreads

    @staticmethod
    def get_spread_by_id(spread_id):
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, name, description, card_count, positions, category, difficulty
                    FROM spreads WHERE id = %s
                """, (spread_id,))
                spread = cursor.fetchone()
                if spread:
                    spread['positions'] = _normalize_json_list(spread.get('positions'))
                return spread

    
    @staticmethod
    def create(reading_data):
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO spread_readings 
                    (id, user_id, session_id, spread_id, cards, question, 
                     ai_personality, date, status)
                    VALUES (%(id)s, %(user_id)s, %(session_id)s, %(spread_id)s, 
                            %(cards)s, %(question)s, %(ai_personality)s, %(date)s, %(status)s)
                    RETURNING *
                """, {
                    **reading_data,
                    'cards': Json(reading_data.get('cards')),
                    'status': reading_data.get('status', 'init')
                })
                row = cursor.fetchone()
                conn.commit()
                return row

    @staticmethod
    def update_status(reading_id, status):
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE spread_readings SET status = %s WHERE id = %s
                """, (status, reading_id))
                conn.commit()

    @staticmethod
    def get_status(reading_id):
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT status, initial_interpretation IS NOT NULL AS has_initial
                    FROM spread_readings WHERE id = %s
                """, (reading_id,))
                return cursor.fetchone()

    @staticmethod
    def get_by_id(reading_id):
        """获取占卜记录"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM spread_readings WHERE id = %s
                """, (reading_id,))
                return cursor.fetchone()

    @staticmethod
    def update_initial_interpretation(reading_id, interpretation):
        """更新初始解读"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE spread_readings 
                    SET initial_interpretation = %s
                    WHERE id = %s
                """, (interpretation, reading_id))
                conn.commit()

    @staticmethod
    def update_conversation_id(reading_id, conversation_id):
        """更新会话ID"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE spread_readings 
                    SET conversation_id = %s
                    WHERE id = %s
                """, (conversation_id, reading_id))
                conn.commit()

    @staticmethod
    def save_message(message_data):
        """保存牌阵对话消息（修复：全命名占位，避免 dict is not a sequence）"""
        import uuid
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO spread_messages 
                    (id, reading_id, role, content)
                    VALUES (%(id)s, %(reading_id)s, %(role)s, %(content)s)
                """, {
                    'id': str(uuid.uuid4()),
                    **message_data
                })
                conn.commit()

    @staticmethod
    def get_all_messages(reading_id):
        """获取所有对话消息"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT role, content, created_at 
                    FROM spread_messages 
                    WHERE reading_id = %s 
                    ORDER BY created_at ASC
                """, (reading_id,))
                return cursor.fetchall()

    @staticmethod
    def get_today_spread_count(user_id, session_id, date):
        """获取今日占卜次数"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM spread_readings
                    WHERE (user_id = %s OR session_id = %s) AND date = %s
                """, (user_id, session_id, date))
                result = cursor.fetchone()
                return result['count'] if result else 0

    @staticmethod
    def get_today_chat_count(user_id, session_id, date):
        """获取今日牌阵对话次数"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM spread_messages m
                    JOIN spread_readings r ON m.reading_id = r.id
                    WHERE m.role = 'user' 
                      AND (r.user_id = %s OR r.session_id = %s) 
                      AND DATE(m.created_at) = %s
                """, (user_id, session_id, date))
                result = cursor.fetchone()
                return result['count'] if result else 0

    @staticmethod
    def increment_chat_usage(user_id, session_id, date):
        """增加对话使用次数（可选，如果需要单独统计）"""
        # 由于消息已经保存，这个方法可能不需要
        pass


# =========================
#         ChatDAO
# =========================
class ChatDAO:
    @staticmethod
    def create_session(session_data):
        """创建聊天会话"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO chat_sessions 
                    (user_id, session_id, card_id, card_name, card_direction, date, ai_personality)
                    VALUES (%(user_id)s, %(session_id)s, %(card_id)s, %(card_name)s, 
                            %(card_direction)s, %(date)s, %(ai_personality)s)
                    RETURNING *
                """, {
                    **session_data,
                    'ai_personality': session_data.get('ai_personality', 'warm')
                })
                session = cursor.fetchone()
                conn.commit()
                return session

    @staticmethod
    def get_session_by_date(user_id, session_id, date):
        """获取指定日期的会话"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM chat_sessions 
                    WHERE (user_id = %(user_id)s OR session_id = %(session_id)s)
                      AND date = %(date)s
                    ORDER BY created_at DESC
                    LIMIT 1
                """, {'user_id': user_id, 'session_id': session_id, 'date': date})
                return cursor.fetchone()

    @staticmethod
    def save_message(message_data):
        """保存聊天消息（修复：写入 chat_messages，且全命名占位）"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO chat_messages (session_id, role, content)
                    VALUES (%(session_id)s, %(role)s, %(content)s)
                    RETURNING *
                """, message_data)
                message = cursor.fetchone()
                conn.commit()
                return message

    @staticmethod
    def get_session_messages(session_id, limit=50):
        """获取会话消息历史"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM chat_messages
                    WHERE session_id = %(session_id)s
                    ORDER BY created_at DESC
                    LIMIT %(limit)s
                """, {'session_id': session_id, 'limit': limit})
                return cursor.fetchall()

    @staticmethod
    def get_daily_usage(user_id, session_id, date):
        """获取每日使用次数"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT count FROM chat_usage
                    WHERE (user_id = %(user_id)s OR session_id = %(session_id)s)
                      AND date = %(date)s
                """, {'user_id': user_id, 'session_id': session_id, 'date': date})
                result = cursor.fetchone()
                return result['count'] if result else 0

    @staticmethod
    def increment_usage(user_id, session_id, date):
        """增加使用次数"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO chat_usage (user_id, session_id, date, count)
                    VALUES (%(user_id)s, %(session_id)s, %(date)s, 1)
                    ON CONFLICT (user_id, date) 
                    DO UPDATE SET count = chat_usage.count + 1
                    RETURNING count
                """, {'user_id': user_id, 'session_id': session_id, 'date': date})
                result = cursor.fetchone()
                conn.commit()
                return result['count'] if result else 1

    @staticmethod
    def get_session_by_id(session_id):
        """根据ID获取会话"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM chat_sessions 
                    WHERE id = %s
                """, (session_id,))
                return cursor.fetchone()


# =========================
#         UserDAO
# =========================
class UserDAO:
    """用户数据访问对象"""

    @staticmethod
    def get_by_id(user_id):
        """根据 ID 获取用户"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                return cursor.fetchone()

    @staticmethod
    def get_by_username(username):
        """根据用户名获取用户"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                return cursor.fetchone()

    @staticmethod
    def create(user_data):
        """创建新用户"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO users (id, username, password_hash, device_id,
                                       first_visit, last_visit, visit_count, is_guest)
                    VALUES (%(id)s, %(username)s, %(password_hash)s, %(device_id)s,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, FALSE)
                    RETURNING *
                """, user_data)
                user = cursor.fetchone()
                conn.commit()
                return user

    @staticmethod
    def update_visit(user_id):
        """更新用户访问信息"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE users 
                    SET last_visit = CURRENT_TIMESTAMP, 
                        visit_count = visit_count + 1 
                    WHERE id = %s
                """, (user_id,))
                conn.commit()


# =========================
#        ReadingDAO
# =========================
class ReadingDAO:
    """占卜记录数据访问对象"""

    @staticmethod
    def get_today_reading(user_id, date):
        """获取今日占卜记录"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT r.*, c.name, c.image, c.meaning_up, c.meaning_rev
                    FROM readings r
                    JOIN tarot_cards c ON r.card_id = c.id
                    WHERE r.user_id = %s AND r.date = %s
                """, (user_id, date))
                return cursor.fetchone()

    @staticmethod
    def create(reading_data):
        """创建占卜记录"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO readings 
                        (user_id, date, card_id, direction, today_insight, guidance)
                    VALUES (%(user_id)s, %(date)s, %(card_id)s, %(direction)s, NULL, NULL)
                    RETURNING *
                """, reading_data)
                reading = cursor.fetchone()
                conn.commit()
                return reading

    @staticmethod
    def update_insight(user_id, date, today_insight, guidance):
        """更新今日洞察和指引"""
        try:
            with DatabaseManager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE readings 
                    SET today_insight = %s, guidance = %s 
                    WHERE user_id = %s AND date = %s
                """, (today_insight, guidance, user_id, date))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Update insight error: {e}")
            traceback.print_exc()
            return False

    @staticmethod
    def update_fortune(user_id, date, fortune_data):
        """更新运势数据"""
        try:
            with DatabaseManager.get_connection() as conn:
                cursor = conn.cursor()
                # 强制序列化为 JSON 字符串
                cursor.execute("""
                    UPDATE readings 
                    SET fortune_data = %s,
                        fortune_generated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s AND date = %s
                """, (json.dumps(fortune_data, ensure_ascii=False), user_id, date))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Update fortune error: {e}")
            traceback.print_exc()
            return False

    @staticmethod
    def get_fortune(user_id, date):
        """获取运势数据"""
        try:
            with DatabaseManager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT fortune_data, fortune_generated_at
                    FROM readings
                    WHERE user_id = %s AND date = %s
                      AND fortune_data IS NOT NULL
                """, (user_id, date))
                result = cursor.fetchone()
                if result and result['fortune_data']:
                    # 判断类型，避免二次 json.loads 出错
                    if isinstance(result['fortune_data'], str):
                        fortune_parsed = json.loads(result['fortune_data'])
                    elif isinstance(result['fortune_data'], dict):
                        fortune_parsed = result['fortune_data']
                    else:
                        fortune_parsed = None
                    return {
                        'fortune_data': fortune_parsed,
                        'generated_at': result.get('fortune_generated_at')
                    }
                return None
        except Exception as e:
            print(f"Get fortune error: {e}")
            traceback.print_exc()
            return None

    @staticmethod
    def delete_today(user_id, date):
        """删除今日记录（重新抽牌）"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM readings WHERE user_id = %s AND date = %s",
                    (user_id, date)
                )
                conn.commit()

    @staticmethod
    def get_recent(user_id, limit=10):
        """获取最近的占卜记录"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT r.date, c.name as card_name, r.direction,
                           r.today_insight, r.guidance
                    FROM readings r
                    JOIN tarot_cards c ON r.card_id = c.id
                    WHERE r.user_id = %s
                    ORDER BY r.date DESC
                    LIMIT %s
                """, (user_id, limit))
                return cursor.fetchall()

    @staticmethod
    def count_by_user(user_id):
        """统计用户占卜次数"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) as count FROM readings WHERE user_id = %s",
                    (user_id,)
                )
                return cursor.fetchone()['count']


# =========================
#         CardDAO
# =========================
class CardDAO:
    """塔罗牌数据访问对象"""

    @staticmethod
    def get_all():
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM tarot_cards")
                return cur.fetchall()

    @staticmethod
    def get_random():
        """随机获取一张塔罗牌"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM tarot_cards ORDER BY RANDOM() LIMIT 1")
                return cursor.fetchone()

    @staticmethod
    def get_by_id(card_id):
        """根据 ID 获取塔罗牌"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM tarot_cards WHERE id = %s", (card_id,))
                return cursor.fetchone()

    @staticmethod
    def get_by_id_with_energy(card_id):
        """获取塔罗牌完整信息，包括能量值"""
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT *,
                           energy_career, energy_wealth, energy_love,
                           energy_health, energy_social, element,
                           special_effect
                    FROM tarot_cards 
                    WHERE id = %s
                """, (card_id,))
                return cursor.fetchone()
