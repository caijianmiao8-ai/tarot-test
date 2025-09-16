"""
配置管理模块
支持 Vercel 和传统部署环境
"""
import os
from datetime import timedelta

class Config:
    """应用配置类"""
    
    # ===== Dify & Cron/Webhook 配置 =====
    DIFY_API_BASE = os.getenv("DIFY_API_BASE", "http://ai-bot-new.dalongyun.com/v1")

    # INTERNAL_API_SECRET：供 Workflow 拉你内部接口用；若未单独设置，则回退到 WEBHOOK_SECRET
    INTERNAL_API_SECRET = os.getenv("INTERNAL_API_SECRET") or os.getenv("WEBHOOK_SECRET", "")


    # 触发“会话摘要 Workflow”的 API Key（在该 Workflow 的 Access API 页面获得）
    DIFY_SUM_WORKFLOW_API_KEY = os.getenv("DIFY_SUM_WORKFLOW_API_KEY", "")
    DIFY_PROFILE_WORKFLOW_API_KEY = os.getenv("DIFY_PROFILE_WORKFLOW_API_KEY")

     # 超时（秒）
    DIFY_CONNECT_TIMEOUT = int(os.getenv("DIFY_CONNECT_TIMEOUT", "5"))
    DIFY_WORKFLOW_TIMEOUT = int(os.getenv("DIFY_WORKFLOW_TIMEOUT", "90"))

    # === 画像历史开关 ===
    WRITE_PROFILE_HISTORY = os.getenv("WRITE_PROFILE_HISTORY", "1")

    # 时区与切日（你现在按 01:00 切日）
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Tokyo")
    DAILY_CONV_CUTOFF_HOUR = int(os.getenv("DAILY_CONV_CUTOFF_HOUR", "1"))
    DAILY_CONV_CUTOFF_MINUTE = int(os.getenv("DAILY_CONV_CUTOFF_MINUTE", "0"))
    
    # 调度接口的简易鉴权（Vercel Cron 调用时在 Header 里带 X-CRON-SECRET）
    CRON_SECRET = os.getenv("CRON_SECRET", "change-me")

    # Webhook 验证（Workflow 的最后一个 HTTP 节点以 Header 带上 X-WEBHOOK-SECRET）
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change-me-too")

    # ===== Conversation 日界线配置 =====
    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Asia/Shanghai")  # 也可用 "Asia/Tokyo"
    DAILY_CONV_CUTOFF_HOUR = int(os.environ.get("DAILY_CONV_CUTOFF_HOUR", "1"))  # 01:00 切日

    # Flask 配置
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-in-production")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # 数据库配置
    DATABASE_URL = os.environ.get("DATABASE_URL")
    DB_POOL_SIZE = 1 if os.environ.get("VERCEL") else 5
    
    # Dify API 配置（基础运势解读）
    DIFY_API_KEY = os.environ.get("DIFY_API_KEY")
    DIFY_API_URL = os.environ.get("DIFY_API_URL", "https://ai-bot-new.dalongyun.com/v1/workflows/run")
    DIFY_TIMEOUT = 25  # 秒
    DIFY_SPREAD_API_KEY = os.getenv("DIFY_SPREAD_API_KEY")
    DIFY_SPREAD_API_URL = os.getenv("DIFY_SPREAD_API_URL")
    DIFY_GUIDED_API_URL = os.getenv("DIFY_GUIDED_API_URL", "").strip()
    DIFY_GUIDED_API_KEY = os.getenv("DIFY_GUIDED_API_KEY", "").strip()
    ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "default-secret-key")
    INTERNAL_TOKENS = set(
        t.strip() for t in (os.getenv("INTERNAL_TOKENS") or "").split(",") if t.strip()
    )
    # 运势专用 API 配置（独立 key，可选独立 URL）
    DIFY_FORTUNE_API_KEY = os.environ.get("DIFY_FORTUNE_API_KEY")
    DIFY_FORTUNE_API_URL = os.environ.get("DIFY_FORTUNE_API_URL", DIFY_API_URL)
    
    # 时区配置
    TIMEZONE_OFFSET = 8  # UTC+8 北京时间
    
    # 环境检测
    IS_VERCEL = bool(os.environ.get("VERCEL"))
    IS_PRODUCTION = os.environ.get("VERCEL_ENV") == "production" if IS_VERCEL else os.environ.get("FLASK_ENV") == "production"
    
    # 功能开关（便于测试新功能）
    FEATURES = {
        "fortune_index": os.environ.get("ENABLE_FORTUNE_INDEX", "true").lower() == "true",  # 默认开启
        "export_pdf": os.environ.get("ENABLE_EXPORT_PDF", "false").lower() == "true",
    }
    
    CHAT_FEATURES = {
        'enabled': True,
        'daily_limit_guest': 10,
        'daily_limit_user': 50,
        'max_message_length': 500,
        'session_timeout_minutes': 30,
        'max_history_messages': 10  # 传给AI的历史消息数
    }
    
    # Dify 聊天专用 API（可选）
    DIFY_CHAT_API_KEY = os.environ.get('DIFY_CHAT_API_KEY', DIFY_API_KEY)
    DIFY_CHAT_API_URL = os.environ.get('DIFY_CHAT_API_URL', "http://ai-bot-new.dalongyun.com/v1/chat-messages")

    @classmethod
    def validate(cls):
        """验证必要配置"""
        errors = []
        
        # 必需的配置项
        required = ["DATABASE_URL", "DIFY_API_KEY"]
        
        # 如果启用了运势功能，只要求专用 API Key
        if cls.FEATURES.get("fortune_index"):
            required.append("DIFY_FORTUNE_API_KEY")
        
        for key in required:
            if not getattr(cls, key):
                errors.append(f"Missing required config: {key}")
        
        # 生产环境额外检查
        if cls.IS_PRODUCTION:
            if cls.SECRET_KEY == "dev-secret-key-change-in-production":
                errors.append("Must set FLASK_SECRET_KEY in production")
        
        if errors:
            raise ValueError("\n".join(errors))
        
        return True
    
    @classmethod
    def get_db_config(cls):
        """获取数据库配置（便于未来支持连接池）"""
        return {
            "dsn": cls.DATABASE_URL,
            "pool_size": cls.DB_POOL_SIZE,
            "sslmode": "require"
        }
