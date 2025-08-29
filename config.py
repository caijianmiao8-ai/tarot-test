"""
配置管理模块
支持 Vercel 和传统部署环境
"""
import os
from datetime import timedelta

class Config:
    """应用配置类"""
    


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
        'daily_limit_guest': 5,
        'daily_limit_user': 10,
        'max_message_length': 500,
        'session_timeout_minutes': 30,
        'max_history_messages': 10  # 传给AI的历史消息数
    }
    
    # Dify 聊天专用 API（可选）
    DIFY_CHAT_API_KEY = os.environ.get('DIFY_CHAT_API_KEY', DIFY_API_KEY)
    DIFY_CHAT_API_URL = os.environ.get('DIFY_CHAT_API_URL', DIFY_API_URL)
        
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
