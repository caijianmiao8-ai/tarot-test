"""
塔罗每日指引 - 主应用
重构版本，支持 Vercel 部署和未来迁移
"""
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify, make_response
from functools import wraps

# 导入配置和服务
from config import Config
from database import DatabaseManager
from services import (
    DateTimeService,
    UserService,
    TarotService,
    DifyService,
    SessionService
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


# ===== 中间件和辅助函数 =====

@app.before_request
def before_request():
    """请求前处理"""
    # 确保会话 ID
    if 'session_id' not in session:
        import uuid
        session['session_id'] = str(uuid.uuid4())
        session.permanent = False
    
    # 加载用户
    user = get_current_user()
    if not user:
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


# ===== 路由 =====

@app.route("/")
def index():
    """首页"""
    user = g.user
    today = DateTimeService.get_beijing_date()
    has_drawn = False
    fortune = None
    tarot_card = None

    if not user["is_guest"]:
        has_drawn = TarotService.has_drawn_today(user['id'], today)
        if has_drawn:
            reading = TarotService.get_today_reading(user['id'], today)
            if reading:
                tarot_card = {
                    "id": reading["card_id"],
                    "name": reading["name"],
                    "image": reading["image"],
                    "meaning_up": reading["meaning_up"],
                    "meaning_rev": reading["meaning_rev"],
                    "direction": reading["direction"]
                }
                fortune = TarotService.get_today_fortune(reading)
    else:
        guest_reading = SessionService.get_guest_reading(session, today)
        has_drawn = guest_reading is not None
        if guest_reading:
            tarot_card = {
                "id": guest_reading.get("card_id"),
                "name": guest_reading["name"],
                "image": guest_reading.get("image"),
                "meaning_up": guest_reading.get("meaning_up"),
                "meaning_rev": guest_reading.get("meaning_rev"),
                "direction": guest_reading["direction"]
            }
            fortune = SessionService.get_guest_fortune(session, today)

    return render_template(
        "index.html",
        has_drawn=has_drawn,
        fortune=fortune,
        tarot_card=tarot_card
    )




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
    
    # 生成解读（如果还没有）
    need_generate = (today_insight is None or today_insight == "" or 
                    guidance is None or guidance == "")
    
    if need_generate:
        # 获取牌面含义
        card_meaning = card_data.get(f"meaning_{'up' if direction == '正位' else 'rev'}", "")
        
        # 调用 AI 生成
        result = DifyService.generate_reading(card_data["name"], direction, card_meaning)
        
        today_insight = result.get("today_insight", f"今日你抽到了{card_data['name']}（{direction}）")
        guidance = result.get("guidance", "请静心感受这张牌的能量")
        
        # 保存解读
        if not user["is_guest"]:
            from database import ReadingDAO
            ReadingDAO.update_insight(user["id"], today, today_insight, guidance)
        else:
            SessionService.update_guest_insight(session, today_insight, guidance)
    
    # ===== 新增：生成今日运势 =====
    try:
        from services import FortuneService
        fortune_data = FortuneService.calculate_fortune(
            card_id=card_data["id"],
            card_name=card_data["name"],
            direction=direction,
            date=today,
            user_id=None if user["is_guest"] else user.get("id")
        )
        from config import Config
        fortune_result = FortuneService.generate_fortune_text(
            fortune_data,
            dify_api_key=Config.DIFY_FORTUNE_API_KEY,
            workflow_id=Config.DIFY_FORTUNE_WORKFLOW_ID
        )
        # 保存到数据库或 session
        if not user["is_guest"]:
            FortuneService.save_fortune(user["id"], today, fortune_result)
        else:
            SessionService.update_guest_insight(
                session,
                insight=fortune_result.get("summary", ""),
                guidance=fortune_result.get("dimension_advice", {})
            )
    except Exception as e:
        print(f"Fortune generation error: {e}")
        fortune_result = None
    
    return render_template(
        "result.html",
        today_date=today.strftime("%Y-%m-%d"),
        card=card_data,
        direction=direction,
        today_insight=today_insight,
        guidance=guidance,
        fortune=fortune_result,
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
- 这是您的专属解读，请用心体会其中的启示
- 塔罗牌是内心智慧的镜子，最终的选择权在您手中
- 如需保存更多历史记录，欢迎注册账号

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
       result = DifyService.generate_reading(card_name, direction, card_meaning)
       
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

@app.route("/api/fortune", methods=["GET"])
def api_fortune():
    """
    当日运势解读接口
    - 已抽牌的用户或访客可以直接获取当天运势
    - 返回 JSON 格式的完整运势数据，包括文案
    """
    from services import FortuneService
    today = DateTimeService.get_beijing_date()
    user = g.user

    # 获取今日抽牌记录
    if not user["is_guest"]:
        reading = TarotService.get_today_reading(user['id'], today)
        if not reading:
            return jsonify({"success": False, "error": "今日尚未抽牌"}), 404
        card_id = reading["card_id"]
        card_name = reading["name"]
        direction = reading["direction"]
    else:
        reading = SessionService.get_guest_reading(session, today)
        if not reading:
            return jsonify({"success": False, "error": "今日尚未抽牌"}), 404
        card_id = reading.get("card_id")
        card_name = reading["name"]
        direction = reading["direction"]

    try:
        # 1. 计算运势数据
        fortune_data = FortuneService.calculate_fortune(
            card_id=card_id,
            card_name=card_name,
            direction=direction,
            date=today,
            user_id=None if user["is_guest"] else user.get("id")
        )

        # 2. 调用 Dify 生成运势文案
        from config import Config
        fortune_result = FortuneService.generate_fortune_text(
            fortune_data,
            dify_api_key=Config.DIFY_FORTUNE_API_KEY,
            workflow_id=Config.DIFY_FORTUNE_WORKFLOW_ID
        )

        # 3. 保存到数据库或会话
        if not user["is_guest"]:
            FortuneService.save_fortune(user["id"], today, fortune_result)
        else:
            SessionService.update_guest_insight(
                session,
                insight=fortune_result.get("summary", ""),
                guidance=fortune_result.get("dimension_advice", {})
            )

        # 4. 返回 JSON
        return jsonify({"success": True, "fortune": fortune_result})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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