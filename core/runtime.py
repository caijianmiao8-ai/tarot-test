# core/runtime.py
from datetime import datetime
from zoneinfo import ZoneInfo
from config import Config
from core.dao import GameSessionDAO, GameActionDAO, GameUsageDAO

TZ = ZoneInfo("Asia/Singapore")

class GameRuntime:
    @staticmethod
    def today():
        return datetime.now(TZ).date()

    @staticmethod
    def can_play(game_key, user_id, session_id, is_guest:bool):
        lim = (Config.GAME_FEATURES.get(game_key, {})
               .get('daily_limit_guest' if is_guest else 'daily_limit_user', 100))
        used = GameUsageDAO.get_today(game_key, user_id, session_id, GameRuntime.today())
        return used < lim, max(lim - used, 0)

    @staticmethod
    def session(game_key, user_id, session_id, *, daily=False, ai_personality='warm'):
        day_key = GameRuntime.today() if daily else None
        s = GameSessionDAO.get_by_key(game_key, user_id, session_id, day_key)
        # 改这里：用 create_or_get
        return s or GameSessionDAO.create_or_get(game_key, user_id, session_id, day_key, ai_personality)

    @staticmethod
    def patch_state(session_id, patch:dict):
        GameSessionDAO.patch_state(session_id, patch)

    @staticmethod
    def log(game_key, session_id, user_id, action, payload=None, result=None, *, bump=True):
        GameActionDAO.add(session_id, game_key, user_id, action, payload, result)
        if bump:
            GameUsageDAO.bump(game_key, user_id, session_id, GameRuntime.today(), actions=1)