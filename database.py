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
import datetime
import json
from datetime import date, datetime
from decimal import Decimal
import os
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor
import threading 

POOL = None                  # ★ 一定要在模块顶层先定义
POOL_LOCK = threading.Lock()

def _mk_pool():
    global POOL
    if POOL is not None:
        return POOL
    dsn = os.getenv("DATABASE_URL")  # ← 换成 Supabase Pooler DSN
    # 加速 & 稳定性参数
    POOL = SimpleConnectionPool(
        minconn=1, maxconn=8, dsn=dsn,
        connect_timeout=3,
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
        sslmode="require",
        cursor_factory=RealDictCursor
    )
    return POOL

def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()  # 'YYYY-MM-DD' 或 'YYYY-MM-DDTHH:MM:SS'
    if isinstance(o, Decimal):
        return float(o)
    # 其他自定义对象都转成字符串，避免再抛错
    return str(o)

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

# ==== 使用既有表：share_cards ====
# 表结构：
# share_cards(id serial, share_id varchar(20) unique, user_id varchar(50),
#             share_data jsonb, created_at timestamp, view_count int, expires_at timestamp)

class ShareDAO:
    @staticmethod
    def _get_conn():
        if hasattr(DatabaseManager, "get_conn"):
            return DatabaseManager.get_conn()
        if hasattr(DatabaseManager, "get_connection"):
            return DatabaseManager.get_connection()
        raise RuntimeError("DatabaseManager 未提供 get_conn/get_connection 方法")

    @staticmethod
    def save_share(share_id: str, user_id, user_name: str,
                   reading: dict, fortune: dict,
                   created_at: datetime, expires_at: datetime):
        # 将所有内容塞进 share_data(JSONB)
        share_data = {
            "user_name": user_name or "神秘访客",
            "reading": reading or {},
            "fortune": fortune or {},
        }
        sql = """
        INSERT INTO share_cards (share_id, user_id, share_data, created_at, expires_at)
        VALUES (%s, %s, %s::jsonb, %s, %s)
        ON CONFLICT (share_id) DO UPDATE
        SET user_id    = EXCLUDED.user_id,
            share_data = EXCLUDED.share_data,
            created_at = EXCLUDED.created_at,
            expires_at = EXCLUDED.expires_at
        """
        with ShareDAO._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [
                    share_id,
                    (str(user_id) if user_id is not None else None),
                    json.dumps(share_data, ensure_ascii=False, default=_json_default),
                    created_at,
                    expires_at
                ])

    @staticmethod
    def get_share(share_id: str):
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT share_id, user_id, share_data, created_at, view_count, expires_at
                    FROM share_cards
                    WHERE share_id = %s
                """, (share_id,))
                row = cur.fetchone()
                if not row:
                    return None

                # 既支持 dict-like 也支持 tuple-like
                def get(rowobj, name, idx):
                    try:
                        return rowobj[name]     # 字典/RealDictRow
                    except Exception:
                        try:
                            return rowobj[idx]  # 元组/NamedTuple
                        except Exception:
                            return None

                share_data = get(row, 'share_data', 2) or {}
                if isinstance(share_data, str):
                    try:
                        share_data = json.loads(share_data)
                    except Exception:
                        share_data = {}

                result = {
                    "share_id":   get(row, 'share_id',   0),
                    "user_id":    get(row, 'user_id',    1),
                    "created_at": get(row, 'created_at', 3),
                    "view_count": get(row, 'view_count', 4) or 0,
                    "expires_at": get(row, 'expires_at', 5),
                }

                # 合并业务数据（reading/fortune 等）到结果字典
                if isinstance(share_data, dict):
                    result = {**share_data, **result}

                return result

    @staticmethod
    def increment_view(share_id: str):
        sql = "UPDATE share_cards SET view_count = view_count + 1 WHERE share_id = %s"
        with ShareDAO._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, [share_id])

class DifyConversationDAO:
    @staticmethod
    def get_conversation_id(user_ref: str, day_key: str,
                            scope: str = "guided",
                            ai_personality: str = "warm"):
        sql = """
        select conversation_id
        from dify_conversations
        where user_ref=%s and scope=%s and ai_personality=%s and day_key=%s::date
        limit 1
        """
        with DatabaseManager.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_ref, scope, ai_personality, day_key))
                row = cur.fetchone()
                return row[0] if row else None

    @staticmethod
    def upsert_conversation_id(user_ref: str, day_key: str, conversation_id: str,
                               scope: str = "guided",
                               ai_personality: str = "warm"):
        sql = """
        insert into dify_conversations(user_ref, scope, ai_personality, day_key, conversation_id)
        values (%s, %s, %s, %s::date, %s)
        on conflict (user_ref, scope, ai_personality, day_key)
        do update set conversation_id=excluded.conversation_id
        returning id
        """
        with DatabaseManager.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user_ref, scope, ai_personality, day_key, conversation_id))
                _ = cur.fetchone()
                conn.commit()
                return True

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
        # 过期检查：你的列是 timestamp(无时区)，比较时用 naive 的 utcnow 即可
        exp = data.get("expires_at")
        if isinstance(exp, datetime):
            now = datetime.utcnow() if exp.tzinfo is None else datetime.now(timezone.utc)
            if exp < now:
                return None
        return data

    @staticmethod
    def increment_view_count(share_id: str):
        ShareDAO.increment_view(share_id)


class DatabaseManager:
    """数据库管理器"""

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
        return _mk_pool().getconn()

    @classmethod
    def return_connection(cls, conn):
        try:
            _mk_pool().putconn(conn)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    @classmethod
    @contextmanager
    def get_db(cls):
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
    def suggest_candidates(topic=None, min_cards=None, max_cards=None, max_difficulty=None):
        """
        基于用户偏好做初筛：主题/张数范围/难度不超出。
        返回：[{id,name,description,card_count,category,difficulty}, ...]
        """
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                sql = """
                    SELECT id, name, description, card_count, category, difficulty
                    FROM spreads
                    WHERE 1=1
                """
                params = {}
                if topic:
                    sql += " AND (category = %(topic)s OR category = '通用')"
                    params['topic'] = topic
                if min_cards is not None:
                    sql += " AND card_count >= %(minc)s"
                    params['minc'] = int(min_cards)
                if max_cards is not None:
                    sql += " AND card_count <= %(maxc)s"
                    params['maxc'] = int(max_cards)
                if max_difficulty:
                    # 难度不超出一个级别（简单<=普通<=进阶），用 CASE 做个序映射
                    sql += """
                    AND (CASE difficulty
                            WHEN '简单' THEN 1
                            WHEN '普通' THEN 2
                            WHEN '进阶' THEN 3
                            ELSE 2
                         END)
                        <=
                        (CASE %(maxd)s
                            WHEN '简单' THEN 1
                            WHEN '普通' THEN 2
                            WHEN '进阶' THEN 3
                            ELSE 3
                         END)
                    """
                    params['maxd'] = max_difficulty

                sql += " ORDER BY card_count ASC, name ASC"
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                return rows

    @staticmethod
    def get_popularity(spread_ids, days=30):
        if not spread_ids:
            return {}
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT spread_id, COUNT(*) AS cnt
                    FROM spread_readings
                    WHERE spread_id = ANY(%s) 
                      AND date >= (CURRENT_DATE - INTERVAL '%s day')
                    GROUP BY spread_id
                """, (spread_ids, days))
                rows = cur.fetchall()
                return {r['spread_id']: r['cnt'] for r in rows}

    @staticmethod
    def used_recently(user_id, spread_ids, days=14):
        if not user_id or not spread_ids:
            return set()
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT spread_id
                    FROM spread_readings
                    WHERE user_id = %s
                      AND spread_id = ANY(%s)
                      AND date >= (CURRENT_DATE - INTERVAL '%s day')
                """, (user_id, spread_ids, days))
                rows = cur.fetchall()
                return {r['spread_id'] for r in rows}

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
                    SELECT id,
                           status,
                           initial_interpretation,
                           (initial_interpretation IS NOT NULL) as has_initial
                    FROM spread_readings
                    WHERE id = %s
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
