# core/dao.py
import json
from database import DatabaseManager
from psycopg2.extras import RealDictCursor

def _identity(user_id, session_id):
    # 你的业务：已登录用 user_id；否则回退到 session_id；都没有就空串
    return user_id or session_id or ""

def _day_norm(day):
    # day 是 date 或 None；None 代表“无按天隔离”，与 SQL 中的 '0001-01-01' 对应
    return day or None  # 查询时我们直接对 day_key_norm 比较参数值（见下）

class GameSessionDAO:
    @staticmethod
    def get_by_key(game_key, user_id, session_id, day_key=None):
        identity = _identity(user_id, session_id)
        # day_key_norm 列 = coalesce(day_key,'0001-01-01')
        # 这里我们传 NULL 代表“无按日”，让 SQL 用 day_key_norm = '0001-01-01' 匹配
        day_val = day_key  # None 表示“无按日”
        with DatabaseManager.get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                select * from game_sessions
                where game_key = %s
                  and identity_key = %s
                  and day_key_norm = coalesce(%s, '0001-01-01'::date)
                limit 1
            """, (game_key, identity, day_val))
            return cur.fetchone()

    @staticmethod
    def create_or_get(game_key, user_id, session_id, day_key=None, ai_personality='warm'):
        """避免并发重复：用唯一约束做 UPSERT，返回最终行"""
        identity = _identity(user_id, session_id)
        with DatabaseManager.get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                insert into game_sessions (game_key, user_id, session_id, day_key, state, ai_personality)
                values (%s, %s, %s, %s, '{}'::jsonb, %s)
                on conflict on constraint uq_game_sessions_identity
                do update set updated_at = now()
                returning *
            """, (game_key, user_id, session_id, day_key, ai_personality))
            row = cur.fetchone()
            conn.commit()
            return row

    @staticmethod
    def patch_state(session_id, patch: dict):
        with DatabaseManager.get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
              update game_sessions
              set state = coalesce(state,'{}'::jsonb) || %s::jsonb,
                  updated_at = now()
              where id=%s
            """, (json.dumps(patch, ensure_ascii=False), session_id))
            conn.commit()

    @staticmethod
    def set_conversation(session_id, cid: str | None):
        with DatabaseManager.get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""update game_sessions set conversation_id=%s, updated_at=now() where id=%s""",
                        (cid, session_id))
            conn.commit()

class GameActionDAO:
    @staticmethod
    def add(session_id, game_key, user_id, action, payload=None, result=None):
        with DatabaseManager.get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
              insert into game_actions (session_id, game_key, user_id, action, payload, result)
              values (%s, %s, %s, %s, %s::jsonb, %s::jsonb)
            """, (session_id, game_key, user_id, action,
                  json.dumps(payload or {}, ensure_ascii=False),
                  json.dumps(result or {}, ensure_ascii=False)))
            conn.commit()

class GameUsageDAO:
    @staticmethod
    def get_today(game_key, user_id, session_id, day):
        identity = _identity(user_id, session_id)
        with DatabaseManager.get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
              select actions from game_usage_daily
              where day = %s and game_key = %s and identity_key = %s
            """, (day, game_key, identity))
            row = cur.fetchone()
            if not row: return 0
            return row["actions"] if isinstance(row, dict) else row[0]

    @staticmethod
    def bump(game_key, user_id, session_id, day, actions=1, tokens_in=0, tokens_out=0):
        with DatabaseManager.get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
              insert into game_usage_daily (day, game_key, user_id, session_id, actions, tokens_in, tokens_out)
              values (%s,%s,%s,%s,%s,%s,%s)
              on conflict (day, game_key, identity_key)
              do update set
                actions    = game_usage_daily.actions    + excluded.actions,
                tokens_in  = game_usage_daily.tokens_in  + excluded.tokens_in,
                tokens_out = game_usage_daily.tokens_out + excluded.tokens_out
            """, (day, game_key, user_id, session_id, actions, tokens_in, tokens_out))
            conn.commit()
