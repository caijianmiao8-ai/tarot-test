"""
塔罗每日指引 - 主应用
重构版本，支持 Vercel 部署和未来迁移
"""
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify, make_response
from functools import wraps
from datetime import datetime
import traceback
import uuid
from flask import g, session
# 导入配置和服务
from config import Config
from database import DatabaseManager, ChatDAO
from services import (
    DateTimeService,
    UserService,
    TarotService,
    DifyService,
    SessionService,
    FortuneService,
    ChatService
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
    print(f"Has history: {len(messages) > 0}")
    print(f"AI personality: {ai_personality}")
    print(f"Session exists: {chat_session is not None}")
    
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

# ===== 错误处理 =====

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500


# ===== 主程序入口 =====

if __name__ == "__main__":
    # 仅在非 Vercel 环境下运行
    if not Config.IS_VERCEL:
        app.run(
            debug=not Config.IS_PRODUCTION,
            host="0.0.0.0",
            port=5000
        )