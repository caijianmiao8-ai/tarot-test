"""
塔罗每日指引 - 主应用
重构版本，支持 Vercel 部署和未来迁移
"""
import os
import json
import random
import traceback
import uuid
from datetime import datetime
from functools import wraps
import time
import logging
from contextlib import contextmanager
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify, make_response

from config import Config
from database import DatabaseManager, ChatDAO, SpreadDAO  # 这里如果用到 UserDAO 也只在函数内部 import 了，OK
from services import (
    DateTimeService,
    UserService,
    TarotService,
    DifyService,
    SessionService,
    FortuneService,
    ChatService,
    SpreadService, 
    PersonaService  # ★ 必须补上
)


# 初始化 Flask 应用
app = Flask(__name__)
app.config.from_object(Config)

# 验证配置
try:
    Config.validate()
except ValueError as e:
    print(f"Configuration error: {e}")
    if Config.IS_PRODUCTION:
        raise

# 统一日志格式（生产上可以写到 JSON）
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def _rid():
    """生成本次请求内的短 request id，便于串联日志"""
    return uuid.uuid4().hex[:6]

@contextmanager
def time_block(label, rid=None):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        t1 = time.perf_counter()
        app.logger.info(f"[{rid}] {label} took {(t1 - t0)*1000:.1f} ms")

@app.before_request
def before_request():
    """请求前处理"""
    # 确保会话 ID
    if 'session_id' not in session:
        session['session_id'] = uuid.uuid4().hex[:8]  # 生成短ID，更可读
        session.permanent = False  # 非持久化 session

    # 加载用户
    user = get_current_user()
    if not user:
        # 如果没有登录用户，生成访客信息
        user = {
            "id": None, 
            "username": None, 
            "is_guest": True,
            "session_id": session['session_id']
        }
    g.user = user



def get_current_user():
    """获取当前用户"""
    user_id = session.get('user_id')
    if not user_id:
        return None
    
    from database import UserDAO
    return UserDAO.get_by_id(user_id)


def login_required(f):
    """需要登录的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash("请先登录", "info")
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def get_user_ref():
    """
    返回可用于 Dify 的用户标识：
    - 已登录用户返回 user_id
    - 访客返回合法 UUID
    """
    user = g.get("user", None)

    if user and not user.get("is_guest", True):
        # 已登录用户
        return str(user["id"])

    # 访客
    if "session_id" not in session:
        session["session_id"] = uuid.uuid4().hex[:8]

    # 生成合法 UUID
    return str(uuid.uuid5(uuid.NAMESPACE_URL, session['session_id']))

# app.py（顶部或实用函数区）
def _resolve_ai_personality(data: dict) -> str:
    # 支持两种字段：优先 ai_personality，其次 persona_id
    return PersonaService.resolve_ai(
        (data.get("ai_personality") or data.get("persona_id"))
    )

@app.route("/spread/chat2")
def spread_chat2():
    """
    引导牌阵占卜：先进入聊天页，由 Dify 引导收集诉求、推荐牌阵和问题，
    确认后再创建 reading 并逐张翻牌。
    """
    user = g.user
    can_chat, remaining = SpreadService.can_chat_today(
        user.get('id'),
        session.get('session_id'),
        user.get('is_guest', True)
    )
    # 渲染新模板（下一步你会添加 spread_chat2.html）
    return render_template(
        "spread_chat2.html",
        user=user,
        can_chat=can_chat,
        remaining_chats=remaining
    )

@app.route("/api/guided/chat/send", methods=["POST"])
def api_guided_chat_send():
    """
    引导阶段与 Dify 对话（未绑定 reading）：
    - 前端传 ai_personality（人格）、message、可选 conversation_id
    - 返回 answer 与新的 conversation_id
    """
    user = g.user
    data = request.json or {}
    message = (data.get('message') or '').strip()
    ai_personality = _resolve_ai_personality(data)
    conversation_id = data.get('conversation_id')

    if not message or len(message) > Config.CHAT_FEATURES['max_message_length']:
        return jsonify({'error': '消息长度不合法'}), 400

    # 这里不计入 spread_messages，不占旧对话额度；额度控制沿用全局 can_chat_today 即可
    can_chat, remaining = SpreadService.can_chat_today(
        user.get('id'), session.get('session_id'), user.get('is_guest', True)
    )
    if not can_chat:
        limit_msg = random.choice(ChatService.LIMIT_MESSAGES)
        return jsonify({'reply': limit_msg, 'limit_reached': True, 'remaining': 0})

    user_ref = get_user_ref()
    resp = DifyService.guided_chat(
        user_message=message,
        user_ref=user_ref,
        conversation_id=conversation_id,
        ai_personality=ai_personality,
        phase='guide'
    )
    return jsonify({
        'reply': resp.get('answer', ''),
        'conversation_id': resp.get('conversation_id'),
        'remaining': max(remaining - 1, 0)
    })

# app.py — 新增：引导落地创建 reading
@app.route("/api/guided/create_reading", methods=["POST"])
def api_guided_create_reading():
    """
    在引导阶段确定了 spread_id + question + ai_personality 后调用：
    - 抽牌并入库（status=init），不触发 LLM
    - 返回 reading_id、positions（用于前端渲染占位）与 card_count
    """
    rid = getattr(g, "rid", _rid())
    user = g.user
    data = request.json or {}
    spread_id = data.get('spread_id')
    question = (data.get('question') or '').strip()
    ai_personality = _resolve_ai_personality(data)

    if not spread_id:
        return jsonify({'error': '缺少牌阵 ID'}), 400
    if question and len(question) > 200:
        return jsonify({'error': '问题请限制在200字以内'}), 400

    # 次数校验（与 /api/spread/draw 一致）
    can_divine, _ = SpreadService.can_divine_today(
        user.get('id'), session.get('session_id'), user.get('is_guest', True)
    )
    if not can_divine:
        return jsonify({'error': '今日占卜次数已用完'}), 429

    try:
        user_ref = get_user_ref()
        reading = SpreadService.create_guided_reading(
            user_ref=user_ref,
            session_id=session.get('session_id'),
            spread_id=spread_id,
            question=question,
            ai_personality=ai_personality
        )
        # 取 positions 给前端渲染
        spread = SpreadDAO.get_spread_by_id(spread_id)
        positions = (spread or {}).get('positions') or []
        return jsonify({
            'success': True,
            'reading_id': reading['id'],
            'positions': positions,
            'card_count': int(spread.get('card_count', 0)) if spread else 0
        })
    except Exception as e:
        print(f"[guided] create_reading error: {e}")
        return jsonify({'error': '创建占卜失败，请稍后重试'}), 500

# app.py — 新增：逐张揭示卡牌
@app.route("/api/guided/reveal_card", methods=["POST"])
def api_guided_reveal_card():
    """
    参数：reading_id, index
    行为：从既有 reading.cards 中取第 index 张，返回卡名/方位/图/位置信息，并记录一条 system 日志
    """
    user = g.user
    data = request.json or {}
    reading_id = data.get('reading_id')
    index = data.get('index')

    if reading_id is None or index is None:
        return jsonify({'error': 'missing reading_id or index'}), 400

    reading = SpreadService.get_reading(reading_id)
    if not reading:
        return jsonify({'error': '占卜记录不存在'}), 404
    if reading['user_id'] != user.get('id') and reading['session_id'] != session.get('session_id'):
        return jsonify({'error': '无权访问'}), 403

    try:
        index = int(index)
        card = SpreadService.reveal_card(reading_id, index)
        return jsonify({'success': True, 'card': card})
    except IndexError:
        return jsonify({'error': '索引越界'}), 400
    except Exception as e:
        print(f"[guided] reveal_card error: {e}")
        return jsonify({'error': '揭示失败，请稍后重试'}), 500

# app.py — 新增：引导模式完成后触发首解读
@app.route("/api/guided/finalize", methods=["POST"])
def api_guided_finalize():
    """
    所有卡牌已揭示后调用：触发一次首解读生成（与 /api/spread/generate_initial 同步逻辑保持一致）。
    """
    data = request.json or {}
    reading_id = data.get("reading_id")
    if not reading_id:
        return jsonify({'error': 'missing reading_id'}), 400

    reading = SpreadDAO.get_by_id(reading_id)
    if not reading:
        return jsonify({'error': 'not found'}), 404

    status_row = SpreadDAO.get_status(reading_id) or {}
    status = status_row.get('status', 'init')
    has_initial = bool(status_row.get('has_initial'))

    if has_initial or status == 'ready':
        # 已生成则直接返回，保持幂等
        return jsonify({'ok': True, 'status': 'ready', 'message': 'already generated'})

    if status == 'generating':
        return jsonify({'ok': True, 'status': 'generating'})

    try:
        SpreadDAO.update_status(reading_id, 'generating')
        resp = SpreadService.generate_initial_interpretation(
            reading_id=reading_id,
            ai_personality=reading.get('ai_personality', 'warm')
        )
        SpreadDAO.update_status(reading_id, 'ready')
        return jsonify({'ok': True, 'status': 'ready', 'conversation_id': resp.get('conversation_id')})
    except Exception as e:
        SpreadDAO.update_status(reading_id, 'error')
        print(f"[guided] finalize error: {e}")
        return jsonify({'ok': False, 'status': 'error', 'error': '生成失败，请稍后重试'}), 500

# app.py 添加一个管理员路由
@app.route("/admin/init-spreads/<secret_key>")
def init_spreads_route(secret_key):
    """初始化牌阵数据的路由"""
    # 使用环境变量中的密钥验证
    if secret_key != os.getenv('ADMIN_SECRET_KEY', 'your-secret-key'):
        return "Unauthorized", 403
    
    try:
        spreads = [
            {
                'id': 'three_cards',
                'name': '时间三牌阵',
                'description': '探索过去、现在和未来的经典牌阵',
                'card_count': 3,
                'category': '通用',
                'difficulty': '简单',
                'positions': json.dumps([
                    {"index": 0, "name": "过去", "meaning": "影响现状的过去因素"},
                    {"index": 1, "name": "现在", "meaning": "当前的状况和挑战"},
                    {"index": 2, "name": "未来", "meaning": "可能的发展方向"}
                ])
            },
            {
                'id': 'yes_no',
                'name': '是否牌阵',
                'description': '快速获得是或否的答案',
                'card_count': 1,
                'category': '决策',
                'difficulty': '简单',
                'positions': json.dumps([
                    {"index": 0, "name": "答案", "meaning": "对你问题的直接回应"}
                ])
            },
            {
                'id': 'relationship',
                'name': '关系牌阵',
                'description': '深入了解两人之间的关系动态',
                'card_count': 5,
                'category': '爱情',
                'difficulty': '中等',
                'positions': json.dumps([
                    {"index": 0, "name": "你的感受", "meaning": "你对关系的看法"},
                    {"index": 1, "name": "对方感受", "meaning": "对方的想法"},
                    {"index": 2, "name": "关系现状", "meaning": "目前的关系状态"},
                    {"index": 3, "name": "挑战", "meaning": "需要面对的问题"},
                    {"index": 4, "name": "建议", "meaning": "改善关系的方向"}
                ])
            }
        ]
        
        count = 0
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cursor:
                for spread in spreads:
                    cursor.execute("""
                        INSERT INTO spreads 
                        (id, name, description, card_count, positions, category, difficulty)
                        VALUES (%(id)s, %(name)s, %(description)s, %(card_count)s, 
                                %(positions)s, %(category)s, %(difficulty)s)
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            description = EXCLUDED.description,
                            positions = EXCLUDED.positions
                    """, spread)
                    count += 1
                conn.commit()
        
        return f"成功初始化 {count} 个牌阵配置", 200
        
    except Exception as e:
        return f"初始化失败: {str(e)}", 500

@app.route('/favicon.ico')
def favicon():
    """处理 favicon 请求"""
    return '', 204  # 返回无内容响应

# ===== 模板上下文 =====

@app.context_processor
def inject_user():
    """注入用户信息到模板"""
    return {"user": g.user}


@app.template_filter("avatar_letter")
def avatar_letter(user):
    """获取用户头像字母"""
    if user and user.get("username"):
        return user["username"][0].upper()
    return "访"

@app.errorhandler(404)
def not_found(e):
    """404 错误处理"""
    # 如果是 API 请求，返回 JSON
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found'}), 404
    
    # 尝试渲染模板，如果失败则返回简单响应
    try:
        return render_template('404.html'), 404
    except:
        return '<h1>404 - Page Not Found</h1><a href="/">Go Home</a>', 404

@app.errorhandler(500)
def server_error(e):
    """500 错误处理"""
    # 记录错误
    app.logger.error(f'Server Error: {e}')
    
    # 如果是 API 请求，返回 JSON
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    
    # 尝试渲染模板，如果失败则返回简单响应
    try:
        return render_template('500.html'), 500
    except:
        return '<h1>500 - Server Error</h1><a href="/">Go Home</a>', 500

# 1. 牌阵选择页面
@app.route("/spread", endpoint="spread")
def spread_page():
    """牌阵占卜选择页面"""
    user = g.user
    today = DateTimeService.get_beijing_date()
    
    spreads = SpreadDAO.get_all_spreads()

    # 检查占卜次数限制
    can_divine, remaining = SpreadService.can_divine_today(
        user.get('id'),
        session.get('session_id'),
        user.get('is_guest', True)
    )
    
    return render_template(
        "spread.html",
        user=user,
        spreads=spreads,  # 需要在 Config 中定义牌阵配置
        can_divine=can_divine,
        remaining_divinations=remaining
    )

# 2. 牌阵对话页面（类似原有的 chat_page）
@app.route("/spread/chat/<reading_id>")
def spread_chat(reading_id):
    """牌阵占卜对话页面"""
    user = g.user
    
    # 获取占卜记录
    reading = SpreadService.get_reading(reading_id)
    if not reading:
        flash("占卜记录不存在", "error")
        return redirect(url_for('spread'))
    
    # 验证权限
    if reading['user_id'] != user.get('id') and reading['session_id'] != session.get('session_id'):
        flash("无权访问此占卜记录", "error")
        return redirect(url_for('spread'))
    
    # 检查对话限制
    can_chat, remaining_chats = SpreadService.can_chat_today(
        user.get('id'),
        session.get('session_id'),
        user.get('is_guest', True)
    )
    
    # 获取历史消息
    messages = SpreadService.get_chat_messages(reading_id)
    
    # 从数据库获取牌阵配置
    spread_config = SpreadDAO.get_spread_by_id(reading['spread_id'])
    
    return render_template(
        "spread_chat.html",
        user=user,
        reading=reading,
        spread_config=spread_config,
        messages=messages,
        can_chat=can_chat,
        remaining_chats=remaining_chats,
        has_history=len(messages) > 0,
        ai_personality=reading.get('ai_personality', 'warm')
    )

@app.route("/api/spread/draw", methods=["POST"])
def api_draw_spread():
    """抽取牌阵并开始占卜（加测速 & 快速返回模式）"""
    rid = getattr(g, "rid", _rid())
    user = g.user
    data = request.json or {}

    # 开关：快速返回模式（先建记录再跳转，AI 初始化延后）
    # export FAST_DRAW=1 开启；不设置或为 0 则按原来“同步生成”的逻辑走
    FAST_DRAW = os.getenv("FAST_DRAW", "0") == "1"

    with time_block("parse_request", rid):
        spread_id = data.get('spread_id')
        question = (data.get('question') or '').strip()
        ai_personality = data.get('ai_personality', 'warm')

    with time_block("load_spread", rid):
        spread = SpreadDAO.get_spread_by_id(spread_id)

    if not spread:
        return jsonify({'error': '请选择有效的牌阵'}), 400

    if question and len(question) > 200:
        return jsonify({'error': '问题请限制在200字以内'}), 400

    with time_block("check_quota", rid):
        can_divine, remaining = SpreadService.can_divine_today(
            user.get('id'),
            session.get('session_id'),
            user.get('is_guest', True)
        )

    if not can_divine:
        return jsonify({'error': '今日占卜次数已用完', 'remaining': 0}), 429

    try:
        user_ref = get_user_ref()

        # ★ 仅建单，立刻返回
        reading = SpreadService.create_reading_fast(
            user_ref=user_ref,
            session_id=session.get('session_id'),
            spread_id=spread_id,
            question=question,
            ai_personality=ai_personality
        )

        return jsonify({
            'success': True,
            'reading_id': reading['id'],
            'redirect': url_for('spread_chat', reading_id=reading['id'])
        })

    except Exception as e:
        print(f"Draw spread error: {e}")
        return jsonify({'error': '占卜失败，请稍后重试'}), 500


# 4. API: 发送牌阵对话消息
@app.route("/api/spread/chat/send", methods=["POST"])
def api_spread_chat_send():
    """发送牌阵对话消息"""
    user = g.user
    data = request.json
    
    reading_id = data.get('reading_id')
    message = data.get('message', '').strip()
    
    if not message or len(message) > Config.CHAT_FEATURES['max_message_length']:
        return jsonify({'error': '消息长度不合法'}), 400
    
    # 获取占卜记录验证权限
    reading = SpreadService.get_reading(reading_id)
    if not reading:
        return jsonify({'error': '占卜记录不存在'}), 404
    
    if reading['user_id'] != user.get('id') and reading['session_id'] != session.get('session_id'):
        return jsonify({'error': '无权访问'}), 403
    
    # 检查对话限制
    can_chat, remaining = SpreadService.can_chat_today(
        user.get('id'),
        session.get('session_id'),
        user.get('is_guest', True)
    )
    
    if not can_chat:
        # 使用与普通聊天相同的限制消息
        limit_msg = random.choice(ChatService.LIMIT_MESSAGES)
        return jsonify({
            'reply': limit_msg,
            'limit_reached': True,
            'remaining': 0
        })
    
    try:
        user_ref = get_user_ref()
        
        # 处理消息
        ai_response = SpreadService.process_chat_message(
            reading_id,
            message,
            user_ref=user_ref
        )
        
        return jsonify({
            'reply': ai_response['answer'],
            'conversation_id': ai_response.get('conversation_id'),
            'remaining': remaining - 1
        })
        
    except Exception as e:
        print(f"Spread chat error: {e}")
        return jsonify({'error': '消息处理失败，请稍后重试'}), 500

@app.route("/api/spread/generate_initial", methods=["POST"])
def api_spread_generate_initial():
    """
    幂等：如果首条解读已有 => 秒回
    如果 status=init|error => 置 generating 并执行一次生成；成功置 ready；失败置 error
    （注意：Vercel Serverless 内不要线程，这里就同步跑一次 Dify）
    """
    data = request.json or {}
    reading_id = data.get("reading_id")
    if not reading_id:
        return jsonify({'error': 'missing reading_id'}), 400

    reading = SpreadDAO.get_by_id(reading_id)
    if not reading:
        return jsonify({'error': 'not found'}), 404

    status_row = SpreadDAO.get_status(reading_id) or {}
    status = status_row.get('status', 'init')
    has_initial = bool(status_row.get('has_initial'))

    if has_initial or status == 'ready':
        return jsonify({'ok': True, 'status': 'ready', 'message': 'already generated'})

    if status == 'generating':
        # 前端可继续轮询
        return jsonify({'ok': True, 'status': 'generating'})

    # init/error -> 开始生成
    try:
        SpreadDAO.update_status(reading_id, 'generating')
        # 直接调用你已有的生成逻辑（同步）
        resp = SpreadService.generate_initial_interpretation(
            reading_id=reading_id,
            ai_personality=reading.get('ai_personality', 'warm')
        )
        SpreadDAO.update_status(reading_id, 'ready')
        return jsonify({'ok': True, 'status': 'ready', 'conversation_id': resp.get('conversation_id')})
    except Exception as e:
        SpreadDAO.update_status(reading_id, 'error')
        print(f"generate_initial failed: {e}")
        return jsonify({'ok': False, 'status': 'error'}), 500
        
# app.py
@app.route("/guide/spread")
def guide_spread():
    """引导式牌阵选择页面"""
    user = g.user
    
    # 检查占卜次数限制
    can_divine, remaining = SpreadService.can_divine_today(
        user.get('id'),
        session.get('session_id'),
        user.get('is_guest', True)
    )
    
    if not can_divine:
        flash("今日占卜次数已用完", "info")
        return redirect(url_for('spread'))
    
    return render_template(
        "guide_spread.html",
        user=user,
        remaining_divinations=remaining
    )

@app.route("/api/spread/status/<reading_id>")
def api_spread_status(reading_id):
    row = SpreadDAO.get_status(reading_id)
    if not row:
        return jsonify({'error': 'not found'}), 404

    msgs = SpreadDAO.get_all_messages(reading_id) or []

    return jsonify({
        'status': row.get('status', 'init'),
        'has_initial': bool(row.get('has_initial')),
        'message_count': len(msgs),
        'initial_text': row.get('initial_interpretation')  # 新增
    })



# 5. 可选：获取今日占卜记录
@app.route("/api/spread/today")
def api_spread_today():
    """获取今日占卜记录"""
    user = g.user
    today = DateTimeService.get_beijing_date()
    
    if not user["is_guest"]:
        readings = SpreadDAO.get_user_readings_by_date(user["id"], today)
    else:
        readings = SpreadDAO.get_session_readings_by_date(session.get('session_id'), today)
    
    return jsonify({
        'readings': readings,
        'count': len(readings)
    })

# ===== 路由 =====
@app.route("/")
def index():
    user = g.user
    today = DateTimeService.get_beijing_date()
    has_drawn = False
    fortune_data = {}
    today_card = None
    
    if not user["is_guest"]:
        has_drawn = TarotService.has_drawn_today(user['id'], today)
        if has_drawn:
            # 获取完整的今日读取记录
            reading = TarotService.get_today_reading(user['id'], today)
            if reading:
                today_card = {
                    'name': reading['name'],
                    'image': reading.get('image', ''),
                    'direction': reading['direction']
                }
                
                # 获取运势数据
                fortune_data = FortuneService.get_fortune(user['id'], today)
                if not fortune_data:
                    fortune_data = FortuneService.calculate_fortune(
                        reading['card_id'], reading['name'], reading['direction'], today, user['id']
                    )
                    fortune_data = FortuneService.generate_fortune_text(fortune_data)
                    FortuneService.save_fortune(user['id'], today, fortune_data)
    else:
        guest_reading = SessionService.get_guest_reading(session, today)
        has_drawn = guest_reading is not None
        if has_drawn:
            today_card = {
                'name': guest_reading['name'],
                'image': guest_reading.get('image', ''),
                'direction': guest_reading['direction']
            }
            
            fortune_data = session.get('fortune_data', {}).get('data', {})
            if not fortune_data and guest_reading:
                fortune_data = FortuneService.calculate_fortune(
                    guest_reading['card_id'], guest_reading['name'], guest_reading['direction'], today
                )
                fortune_data = FortuneService.generate_fortune_text(fortune_data)
                session['fortune_data'] = {'date': str(today), 'data': fortune_data}
                session.modified = True
    
    return render_template(
        "index.html",
        has_drawn=has_drawn,
        fortune_data=fortune_data,
        user=user,
        today=today.strftime("%Y-%m-%d"),
        today_card=today_card
    )

@app.route("/chat")
def chat_page():
    """聊天页面"""
    user = g.user
    today = DateTimeService.get_beijing_date()
    
    # 检查是否已抽牌
    if not user["is_guest"]:
        reading = TarotService.get_today_reading(user["id"], today)
    else:
        reading = SessionService.get_guest_reading(session, today)
    
    if not reading:
        flash("请先抽取今日塔罗牌", "info")
        return redirect(url_for("index"))
    
    # 检查对话限制
    can_chat, remaining_chats = ChatService.can_start_chat(
        user.get('id'), 
        session.get('session_id'),
        user.get('is_guest', True)
    )
    
    # 获取或创建会话并加载历史消息
    chat_session = None
    messages = []
    ai_personality = None  # 新增
    
    try:
        chat_session = ChatService.create_or_get_session(
            user.get('id'),
            session.get('session_id'),
            reading,
            today
        )
        if chat_session:
            messages = ChatDAO.get_session_messages(chat_session['id'])
            # 获取已保存的人格
            ai_personality = chat_session.get('ai_personality')
            # 转换为前端需要的格式
            messages = [
                {'role': msg['role'], 'content': msg['content']} 
                for msg in reversed(messages)
            ] if messages else []
    except Exception as e:
        print(f"Load chat history error: {e}")
        print("=== Chat Page Debug ===")

    print(f"can_chat: {can_chat}")
    print(f"remaining_chats: {remaining_chats}")
    print(f"session_id: {chat_session['id'] if chat_session else None}")
    print(f"messages count: {len(messages)}")
    print(f"ai_personality: {ai_personality}")

    return render_template(
        "chat.html",
        user=user,
        card_info=reading,
        can_chat=can_chat,
        remaining_chats=remaining_chats,
        session_id=str(chat_session['id']) if chat_session else None,
        messages=messages,
        has_history=len(messages) > 0,
        ai_personality=ai_personality  # 新增
    )


@app.route("/api/chat/init", methods=["POST"])
def init_chat():
    """初始化聊天会话"""
    user = g.user
    today = DateTimeService.get_beijing_date()
    data = request.json
    ai_personality = data.get('ai_personality')  # 新增
    
    # 获取今日卡片信息
    if not user["is_guest"]:
        reading = TarotService.get_today_reading(user["id"], today)
    else:
        reading = SessionService.get_guest_reading(session, today)
    
    if not reading:
        return jsonify({'error': '未找到今日塔罗记录'}), 404
    
    # 创建或获取会话
    try:
        chat_session = ChatService.create_or_get_session(
            user.get('id'),
            session.get('session_id'),
            reading,
            today,
            ai_personality=ai_personality  # 新增参数
        )
        
        if not chat_session:
            return jsonify({'error': '无法创建会话'}), 500
        
        # 获取历史消息
        messages = ChatDAO.get_session_messages(chat_session['id'])
        
        return jsonify({
            'session_id': str(chat_session['id']),
            'messages': [
                {'role': msg['role'], 'content': msg['content']} 
                for msg in reversed(messages) if messages
            ] if messages else []
        })
    except Exception as e:
        print(f"Init chat error: {e}")
        return jsonify({'error': '初始化失败'}), 500

@app.route("/api/chat/send", methods=["POST"])
def send_chat_message():
    user = g.user
    data = request.json
    message = data.get('message', '').strip()
    session_id = data.get('session_id')
    ai_personality = data.get('ai_personality')  # 新增
    
    if not message or len(message) > Config.CHAT_FEATURES['max_message_length']:
        return jsonify({'error': '消息长度不合法'}), 400

    can_chat, remaining = ChatService.can_start_chat(
        user.get('id'),
        session.get('session_id'),
        user.get('is_guest', True)
    )

    if not can_chat:
        limit_msg = random.choice(ChatService.LIMIT_MESSAGES)
        return jsonify({'reply': limit_msg, 'limit_reached': True, 'remaining': 0})

    try:
        user_ref = get_user_ref()
        ai_response = ChatService.process_message(
            session_id, 
            message, 
            user_ref=user_ref,
            ai_personality=ai_personality  # 新增参数
        )

        # 确保 ai_response 是 dict
        answer_text = ai_response.get('answer') if isinstance(ai_response, dict) else str(ai_response)
        conversation_id = ai_response.get('conversation_id') if isinstance(ai_response, dict) else None

        return jsonify({
            'reply': answer_text,
            'conversation_id': conversation_id,
            'remaining': remaining - 1
        })
        
    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({'error': '处理消息时出错'}), 500


@app.route("/login", methods=["GET", "POST"])
def login():
    """登录"""
    if request.method == "POST":
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash("请填写用户名和密码", "error")
            return render_template("login.html")
        
        user = UserService.authenticate(username, password)
        if user:
            session['user_id'] = user['id']
            session.permanent = True
            flash(f"欢迎回来，{username}！", "success")
            next_page = request.args.get('next') or url_for('index')
            return redirect(next_page)
        else:
            flash("用户名或密码错误", "error")
    
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """注册"""
    if request.method == "POST":
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # 验证输入
        if not username or not password:
            flash("请填写用户名和密码", "error")
        elif len(username) < 3:
            flash("用户名至少需要3个字符", "error")
        elif len(password) < 6:
            flash("密码至少需要6个字符", "error")
        elif password != confirm_password:
            flash("两次输入的密码不一致", "error")
        else:
            # 生成设备指纹
            device_id = UserService.generate_device_fingerprint(
                request.headers.get('User-Agent', ''),
                request.headers.get('Accept-Language', '')
            )
            
            # 注册用户
            user, error = UserService.register(username, password, device_id)
            if user:
                session['user_id'] = user['id']
                session.permanent = True
                flash(f"注册成功！欢迎你，{username}！", "success")
                return redirect(url_for('index'))
            else:
                flash(error, "error")
    
    return render_template("register.html")


@app.route("/logout")
def logout():
    """退出登录"""
    username = g.user.get('username', '访客')
    session.clear()
    flash(f"再见，{username}！期待您下次光临", "info")
    return redirect(url_for('index'))


@app.route("/draw", methods=["POST"])
def draw_card():
    """抽牌"""
    user = g.user
    today = DateTimeService.get_beijing_date()
    
    # 检查是否已经抽过牌
    if not user["is_guest"]:
        if TarotService.has_drawn_today(user["id"], today):
            return redirect(url_for("result"))
    else:
        if SessionService.get_guest_reading(session, today):
            return redirect(url_for("result"))
    
    # 抽牌
    card, direction = TarotService.draw_card()
    if not card:
        flash("数据库中没有塔罗牌数据", "error")
        return redirect(url_for("index"))
    
    # 保存记录
    if not user["is_guest"]:
        TarotService.save_reading(user["id"], today, card["id"], direction)
    else:
        SessionService.save_guest_reading(session, card, direction, today)
    
    flash(f"您抽到了{card['name']}（{direction}）", "success")
    return redirect(url_for("result"))


@app.route("/result")
def result():
    """查看结果"""
    user = g.user
    today = DateTimeService.get_beijing_date()
    
    # 获取抽牌记录
    if not user["is_guest"]:
        reading = TarotService.get_today_reading(user["id"], today)
        if not reading:
            flash("请先抽取今日塔罗牌", "info")
            return redirect(url_for("index"))
        
        card_data = {
            "id": reading["card_id"],
            "name": reading["name"],
            "image": reading["image"],
            "meaning_up": reading["meaning_up"],
            "meaning_rev": reading["meaning_rev"]
        }
        direction = reading["direction"]
        today_insight = reading.get("today_insight")
        guidance = reading.get("guidance")
        
    else:
        reading = SessionService.get_guest_reading(session, today)
        if not reading:
            flash("请先抽取塔罗牌", "info")
            return redirect(url_for("index"))
        
        card_data = {
            "id": reading.get("card_id"),
            "name": reading["name"],
            "image": reading.get("image"),
            "meaning_up": reading.get("meaning_up"),
            "meaning_rev": reading.get("meaning_rev")
        }
        direction = reading["direction"]
        today_insight = reading.get('today_insight')
        guidance = reading.get('guidance')
    
    # 生成解读（如果还没有）- 这里是关键修复
    need_generate = (today_insight is None or today_insight == "" or 
                    guidance is None or guidance == "")
    
    if need_generate:
        # 获取牌面含义
        card_meaning = card_data.get(f"meaning_{'up' if direction == '正位' else 'rev'}", "")
        
        # 调用 AI 生成 - 确保这里会被执行
        try:
            user_ref = get_user_ref()
            result = DifyService.generate_reading(card_data["name"], direction, card_meaning, user_ref=user_ref)
            
            today_insight = result.get("today_insight", f"今日你抽到了{card_data['name']}（{direction}）")
            guidance = result.get("guidance", "请静心感受这张牌的能量")
            
            # 保存解读
            if not user["is_guest"]:
                from database import ReadingDAO
                ReadingDAO.update_insight(user["id"], today, today_insight, guidance)
            else:
                SessionService.update_guest_insight(session, today_insight, guidance)
        
        except Exception as e:
            print(f"Generate reading error: {e}")
            # 使用默认解读
            today_insight = f"今日你抽到了{card_data['name']}（{direction}）"
            guidance = "请静心感受这张牌的能量"
    
    return render_template(
        "result.html",
        today_date=today.strftime("%Y-%m-%d"),
        card=card_data,
        direction=direction,
        today_insight=today_insight,
        guidance=guidance,
        is_guest=user["is_guest"],
        can_export=True,
        user=user
    )


@app.route("/stats")
@login_required
def stats():
    """统计页面"""
    user = g.user
    stats = TarotService.get_user_stats(user['id'])
    
    return render_template(
        "stats.html",
        user=user,
        total_readings=stats['total_readings'],
        recent_readings=stats['recent_readings']
    )


@app.route("/export_reading")
def export_reading():
    """导出解读（访客功能）"""
    user = g.user
    today = DateTimeService.get_beijing_date()
    
    if not user["is_guest"]:
        return redirect(url_for("stats"))
    
    reading = SessionService.get_guest_reading(session, today)
    if not reading:
        flash("没有找到今日的解读记录", "error")
        return redirect(url_for("index"))
    
    # 生成导出内容
    export_content = f"""塔罗每日指引
生成日期：{today.strftime('%Y年%m月%d日')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

抽到的塔罗牌：{reading.get('name')}
牌面方向：{reading.get('direction')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【今日洞察】
{reading.get('today_insight', '暂无解读内容')}

【指引建议】
{reading.get('guidance', '暂无指引内容')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 温馨提示：
• 这是您的专属解读，请用心体会其中的启示
• 塔罗牌是内心智慧的镜子，最终的选择权在您手中
• 如需保存更多历史记录，欢迎注册账号

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

此内容由塔罗每日指引生成
愿宇宙的智慧照亮您的道路 ✨
"""
    
    response = make_response(export_content)
    response.headers["Content-Disposition"] = f"attachment; filename=tarot_reading_{today.strftime('%Y%m%d')}.txt"
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    
    return response


@app.route("/clear")
@login_required
def clear_cache():
    """清除今日记录"""
    user_id = session.get('user_id')
    today = DateTimeService.get_beijing_date()
    
    from database import ReadingDAO
    ReadingDAO.delete_today(user_id, today)
    
    flash("已清除今日抽牌记录", "success")
    return redirect(url_for("index"))


@app.route("/api/regenerate", methods=["POST"])
def regenerate():
    """重新生成解读"""
    user = g.user
    today = DateTimeService.get_beijing_date()
    
    try:
        # 获取今日记录
        if not user["is_guest"]:
            reading = TarotService.get_today_reading(user["id"], today)
            if not reading:
                return jsonify({"success": False, "error": "未找到今日抽牌记录"}), 404
            
            card_name = reading["name"]
            direction = reading["direction"]
            card_meaning = reading[f"meaning_{'up' if direction == '正位' else 'rev'}"]
        else:
            reading = SessionService.get_guest_reading(session, today)
            if not reading:
                return jsonify({"success": False, "error": "未找到今日抽牌记录"}), 404
            
            card_name = reading["name"]
            direction = reading["direction"]
            card_meaning = reading.get(f"meaning_{'up' if direction == '正位' else 'rev'}", "")
        
        # 重新生成
        user_ref = get_user_ref()
        result = DifyService.generate_reading(card_name, direction, card_meaning, user_ref=user_ref)
        
        # 保存新的解读
        if not user["is_guest"]:
            from database import ReadingDAO
            ReadingDAO.update_insight(
                user["id"], 
                today, 
                result["today_insight"], 
                result["guidance"]
            )
        else:
            SessionService.update_guest_insight(
                session, 
                result["today_insight"], 
                result["guidance"]
            )
        
        return jsonify({
            "success": True,
            "today_insight": result["today_insight"],
            "guidance": result["guidance"]
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/fortune/<date>", endpoint="api_fortune")
def get_fortune(date):
    """获取运势数据 API"""
    if not Config.FEATURES.get("fortune_index"):
        return jsonify({"error": "Fortune feature is disabled"}), 404
    
    user = g.user
    
    try:
        # 验证日期格式
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
        today = DateTimeService.get_beijing_date()
        
        # 只能查看今天的运势
        if target_date != today:
            return jsonify({"error": "只能查看今日运势"}), 400
        
        # 获取今日抽牌记录
        if not user["is_guest"]:
            reading = TarotService.get_today_reading(user["id"], today)
            if not reading:
                return jsonify({"error": "请先抽取今日塔罗牌"}), 404
            card_id = reading["card_id"]
            card_name = reading["name"]
            direction = reading["direction"]
        else:
            reading = SessionService.get_guest_reading(session, today)
            if not reading:
                return jsonify({"error": "请先抽取今日塔罗牌"}), 404
            card_id = reading.get("card_id")
            card_name = reading["name"]
            direction = reading["direction"]
        
        # 检查缓存的运势数据
        if user["is_guest"]:
            # 访客缓存
            if 'fortune_data' in session:
                cached = session.get('fortune_data')
                if cached and cached.get('date') == date:
                    return jsonify(cached['data'])
        else:
            # 登录用户检查数据库缓存
            existing_fortune = FortuneService.get_fortune(user["id"], target_date)
            if existing_fortune:
                return jsonify(existing_fortune)
        
        # 计算运势
        fortune_data = FortuneService.calculate_fortune(
            card_id,
            card_name,
            direction,
            target_date,
            user.get("id")
        )
        
        # 生成运势文案
        fortune_data = FortuneService.generate_fortune_text(fortune_data)
        
        # 保存运势数据
        if not user["is_guest"]:
            FortuneService.save_fortune(user["id"], target_date, fortune_data)
        else:
            # 访客缓存
            session['fortune_data'] = {
                'date': date,
                'data': fortune_data
            }
            session.modified = True
        
        return jsonify(fortune_data)
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"Fortune API error: {e}")
        traceback.print_exc()
        return jsonify({"error": "计算运势时出错"}), 500

    if fortune_data and 'dimension_advice' in fortune_data and 'dimensions' not in fortune_data:
        fortune_data = convert_fortune_format(fortune_data)
    
    return jsonify(fortune_data)        

@app.route("/api/fortune_preview")
def fortune_preview():
    """运势预览API - 返回简化的运势数据用于首页显示"""
    user = g.user
    today = DateTimeService.get_beijing_date()
    
    # 检查是否已抽牌
    if not user["is_guest"]:
        reading = TarotService.get_today_reading(user["id"], today)
        if not reading:
            return jsonify({"error": "请先抽取今日塔罗牌"}), 404
    else:
        reading = SessionService.get_guest_reading(session, today)
        if not reading:
            return jsonify({"error": "请先抽取今日塔罗牌"}), 404
    
    # 获取完整运势数据（复用现有逻辑）
    try:
        date_str = today.strftime("%Y-%m-%d")
        # 这里可以调用现有的 get_fortune 路由逻辑
        # 但只返回首页需要的关键信息
        
        return jsonify({
            "overall_score": 85,  # 示例数据
            "top_dimension": {"name": "爱情运", "stars": 4.5},
            "lucky_color": "红色",
            "summary": "今日运势极佳，万事皆宜！"
        })
        
    except Exception as e:
        return jsonify({"error": "获取运势预览失败"}), 500



# ===== 主程序入口 =====

if __name__ == "__main__":
    # 仅在非 Vercel 环境下运行
    if not Config.IS_VERCEL:
        app.run(
            debug=not Config.IS_PRODUCTION,
            host="0.0.0.0",
            port=5000
        )