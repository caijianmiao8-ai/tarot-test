import os
import random
import datetime
import uuid
import hashlib
import requests
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import json
import time
import traceback
from datetime import datetime, timezone, timedelta

# ---------------- 环境变量 ----------------
DIFY_API_KEY = os.environ.get("DIFY_API_KEY")
WORKFLOW_ID = os.environ.get("WORKFLOW_ID")
DATABASE_URL = os.environ.get("DATABASE_URL")  # Vercel/Supabase 设置

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

# ---------------- Session 配置优化 ----------------
app.config.update(
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",  # 生产环境使用 HTTPS
    SESSION_COOKIE_HTTPONLY=True,  # 防止 JS 访问
    SESSION_COOKIE_SAMESITE='Lax',  # CSRF 保护
    PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=24),  # 会话持续时间
    SESSION_COOKIE_NAME='tarot_session',
)

# ---------------- 数据库连接 ----------------
def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,
        sslmode="require"
    )

# ---------------- 用户系统 ----------------
def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return cursor.fetchone()
    finally:
        conn.close()

def get_local_date():
   """获取北京时间的当前日期"""
   beijing_tz = timezone(timedelta(hours=8))
   return datetime.now(beijing_tz).date()
   
@app.before_request
def before_request():
    """确保会话初始化和用户加载"""
    # 确保每个访客都有唯一标识
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
        session.permanent = False  # 确保是会话 cookie
    
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

@app.context_processor
def inject_user():
    """注入用户信息和辅助函数到模板"""
    return {
        "user": g.user,
        "is_incognito_hint": detect_incognito_mode()
    }

@app.template_filter("avatar_letter")
def avatar_letter(user):
    if user and user.get("username"):
        return user["username"][0].upper()
    return "访"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash("请先登录", "info")
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def detect_incognito_mode():
    """尝试检测是否可能是无痕浏览模式"""
    # 这只是启发式判断，不是100%准确
    user_agent = request.headers.get('User-Agent', '')
    sec_fetch_site = request.headers.get('Sec-Fetch-Site', '')
    
    # 一些可能的无痕模式特征
    hints = [
        sec_fetch_site == 'none',
        'Private' in user_agent,  # 某些浏览器会标记
    ]
    
    return any(hints)

# ---------------- 路由 ----------------
@app.route("/")
def index():
    today = datetime.date.today()
    user = g.user
    has_drawn = False
    can_draw = True
    last_card_date = None

    if not user["is_guest"]:
        # 登录用户检查数据库
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM readings WHERE user_id=%s AND date=%s LIMIT 1",
                    (user['id'], today)
                )
                has_drawn = cursor.fetchone() is not None
        finally:
            conn.close()
    else:
        # 访客检查 session
        last_card = session.get('last_card', {})
        if last_card:
            last_card_date = last_card.get("date")
            has_drawn = last_card_date == str(today)
            # 如果是过期的记录，允许重新抽牌
            if last_card_date and last_card_date != str(today):
                can_draw = True
                flash("昨日的塔罗指引已过期，您可以抽取今日的塔罗牌", "info")

    return render_template(
        "index.html", 
        has_drawn=has_drawn,
        can_draw=can_draw,
        last_card_date=last_card_date,
        is_guest=user["is_guest"],
        show_guest_tip=user["is_guest"] and not has_drawn
    )

@app.route("/stats")
@login_required
def stats():
    user = g.user
    total_readings = 0
    recent_readings = []

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM readings WHERE user_id=%s", (user['id'],))
            total_readings = cursor.fetchone()['count'] or 0

            cursor.execute("""
                SELECT r.date, c.name AS card_name, r.direction, 
                       r.today_insight, r.guidance
                FROM readings r
                JOIN tarot_cards c ON r.card_id = c.id
                WHERE r.user_id = %s
                ORDER BY r.date DESC
                LIMIT 10
            """, (user['id'],))
            recent_readings = cursor.fetchall()
    finally:
        conn.close()

    return render_template(
        "stats.html",
        user=user,
        total_readings=total_readings,
        recent_readings=recent_readings
    )

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash("请填写用户名和密码", "error")
            return render_template("login.html")
        
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                user = cursor.fetchone()
                if user and check_password_hash(user['password_hash'], password):
                    session['user_id'] = user['id']
                    session.permanent = True  # 登录用户使用持久会话
                    
                    cursor.execute(
                        "UPDATE users SET last_visit = CURRENT_TIMESTAMP, visit_count = visit_count + 1 WHERE id = %s",
                        (user['id'],)
                    )
                    conn.commit()
                    
                    flash(f"欢迎回来，{username}！", "success")
                    next_page = request.args.get('next') or url_for('index')
                    return redirect(next_page)
                else:
                    flash("用户名或密码错误", "error")
                    return render_template("login.html")
        finally:
            conn.close()
    
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # 验证输入
        if not username or not password:
            flash("请填写用户名和密码", "error")
            return render_template("register.html")
        if len(username) < 3:
            flash("用户名至少需要3个字符", "error")
            return render_template("register.html")
        if len(password) < 6:
            flash("密码至少需要6个字符", "error")
            return render_template("register.html")
        if password != confirm_password:
            flash("两次输入的密码不一致", "error")
            return render_template("register.html")

        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
                if cursor.fetchone():
                    flash("用户名已被使用", "error")
                    return render_template("register.html")
                
                user_id = str(uuid.uuid4())
                password_hash = generate_password_hash(password)
                device_id = generate_device_fingerprint(request)
                
                cursor.execute("""
                    INSERT INTO users (id, username, password_hash, device_id,
                                       first_visit, last_visit, visit_count, is_guest)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, FALSE)
                """, (user_id, username, password_hash, device_id))
                conn.commit()
                
                session['user_id'] = user_id
                session.permanent = True
                flash(f"注册成功！欢迎你，{username}！", "success")
                return redirect(url_for('index'))
        finally:
            conn.close()
    
    return render_template("register.html")

@app.route("/logout")
def logout():
    username = g.user.get('username', '访客')
    session.clear()
    flash(f"再见，{username}！期待您下次光临", "info")
    return redirect(url_for('index'))

@app.route("/draw", methods=["POST"])
def draw_card():
    user = g.user
    today = datetime.date.today()
    
    # 检查是否已经抽过牌
    if not user["is_guest"]:
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM readings WHERE user_id=%s AND date=%s LIMIT 1",
                    (user["id"], today)
                )
                if cursor.fetchone():
                    return redirect(url_for("result"))
        finally:
            conn.close()
    else:
        # 访客用户检查
        last_card = session.get('last_card', {})
        if last_card.get("date") == str(today):
            return redirect(url_for("result"))
        elif last_card.get("date"):
            # 清除过期的记录
            session.pop('last_card', None)

    # 抽牌
    direction = random.choice(["正位", "逆位"])
    conn = get_db()
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM tarot_cards ORDER BY RANDOM() LIMIT 1")
            card = cursor.fetchone()
            if not card:
                cursor.execute("SELECT * FROM cards ORDER BY RANDOM() LIMIT 1")
                card = cursor.fetchone()
            if not card:
                flash("数据库中没有塔罗牌数据", "error")
                return redirect(url_for("index"))

            # 登录用户保存到数据库
            if not user["is_guest"]:
                cursor.execute(
                    """
                    INSERT INTO readings 
                        (user_id, date, card_id, direction, today_insight, guidance)
                    VALUES (%s, %s, %s, %s, NULL, NULL)
                    """,
                    (user["id"], today, card["id"], direction)
                )
                conn.commit()
                flash(f"您抽到了{card['name']}（{direction}）", "success")
    finally:
        conn.close()

    # 访客用户保存到 session
    if user["is_guest"]:
        session['last_card'] = {
            "card_id": card["id"],
            "name": card["name"],
            "image": card.get("image"),
            "meaning_up": card.get("meaning_up"),
            "meaning_rev": card.get("meaning_rev"),
            "direction": direction,
            "date": str(today),
            "timestamp": datetime.datetime.now().isoformat()
        }
        session.modified = True
        flash(f"您抽到了{card['name']}（{direction}）", "success")

    return redirect(url_for("result"))

@app.route("/result")
def result():
    user = g.user
    today = get_local_date()  # 使用你的时区函数，确保日期本地化
    
    # ---------------- 获取抽牌记录 ----------------
    if not user["is_guest"]:
        # 登录用户从数据库获取
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT r.*, c.name, c.image, c.meaning_up, c.meaning_rev
                    FROM readings r
                    JOIN tarot_cards c ON r.card_id=c.id
                    WHERE r.user_id=%s AND r.date=%s
                """, (user["id"], today))
                reading = cursor.fetchone()

                if not reading:
                    cursor.execute("""
                        SELECT r.*, c.name, c.image, c.meaning_up, c.meaning_rev
                        FROM readings r
                        JOIN cards c ON r.card_id=c.id
                        WHERE r.user_id=%s AND r.date=%s
                    """, (user["id"], today))
                    reading = cursor.fetchone()
        finally:
            conn.close()
        
        if not reading:
            flash("请先抽取今日塔罗牌", "info")
            return redirect(url_for("index"))
        
        card_data = {
            "id": reading["card_id"],
            "name": reading["name"],
            "image": reading["image"],  # 图片路径，例如 /static/images/tarot/00_fool.jpg
            "meaning_up": reading["meaning_up"],
            "meaning_rev": reading["meaning_rev"]
        }
        direction = reading["direction"]
        today_insight = reading.get("today_insight")
        guidance = reading.get("guidance")
        
    else:
        # 访客用户从 session 获取
        last_card = session.get('last_card', {})

        if not last_card:
            flash("请先抽取塔罗牌", "info")
            return redirect(url_for("index"))

        if last_card.get("date") != str(today):
            flash("昨日的塔罗指引已过期，请重新抽牌", "info")
            return redirect(url_for("index"))

        card_data = {
            "id": last_card.get("card_id"),
            "name": last_card["name"],
            "image": last_card.get("image"),
            "meaning_up": last_card.get("meaning_up"),
            "meaning_rev": last_card.get("meaning_rev")
        }
        direction = last_card["direction"]
        today_insight = last_card.get('today_insight')
        guidance = last_card.get('guidance')
    
    # ---------------- 判断是否需要生成内容 ----------------
    need_generate = (not today_insight or today_insight.strip() == "" or
                     not guidance or guidance.strip() == "")

    display_insight = today_insight
    display_guidance = guidance

    if need_generate:
        print(f"Generating content for user {user.get('id', 'guest_' + user.get('session_id', 'unknown'))}")

        # 默认文案
        default_insight = f"今日你抽到了{card_data['name']}（{direction}），这张牌正在向你传递宇宙的信息。"
        default_guidance = f"{'正位' if direction == '正位' else '逆位'}的{card_data['name']}提醒你，要相信内心的声音，保持开放的心态。"

        api_success = False

        try:
            api_url = "https://ai-bot-new.dalongyun.com/v1/workflows/run"
            headers = {
                "Authorization": f"Bearer {DIFY_API_KEY}",
                "Content-Type": "application/json"
            }

            user_identifier = user["id"] if not user["is_guest"] else f'guest_{user.get("session_id", "unknown")}'
            card_meaning = card_data.get(f"meaning_{'up' if direction == '正位' else 'rev'}", "")

            payload = {
                "inputs": {
                    "card_name": str(card_data.get("name", "")),
                    "direction": str(direction),
                    "meaning": str(card_meaning)
                },
                "response_mode": "blocking",
                "user": str(user_identifier)
            }

            print(f"Calling Dify API for card: {card_data['name']}, direction: {direction}")

            response = requests.post(api_url, headers=headers, json=payload, timeout=25)
            response.raise_for_status()

            data = response.json()
            output_str = ""

            if isinstance(data, dict):
                if "data" in data and isinstance(data["data"], dict):
                    outputs = data["data"].get("outputs", {})
                    if isinstance(outputs, dict):
                        output_str = outputs.get("text", "")
                    elif isinstance(outputs, str):
                        output_str = outputs
                elif "answer" in data:
                    output_str = data["answer"]
                elif "text" in data:
                    output_str = data["text"]

            # 尝试解析 JSON
            parsed_data = None
            try:
                parsed_data = json.loads(output_str)
            except:
                try:
                    start = output_str.find("```json")
                    if start != -1:
                        end = output_str.find("```", start + 7)
                        if end != -1:
                            json_str = output_str[start + 7:end].strip()
                            parsed_data = json.loads(json_str)
                except:
                    pass
            if not parsed_data:
                try:
                    start = output_str.find("{")
                    end = output_str.rfind("}")
                    if start != -1 and end != -1:
                        json_str = output_str[start:end + 1]
                        parsed_data = json.loads(json_str)
                except:
                    pass

            if parsed_data and isinstance(parsed_data, dict):
                new_insight = parsed_data.get("today_insight", "").strip()
                new_guidance = parsed_data.get("guidance", "").strip()
                if new_insight and new_guidance:
                    today_insight = new_insight
                    guidance = new_guidance
                    display_insight = today_insight
                    display_guidance = guidance
                    api_success = True
                    print("Successfully generated content")

        except requests.exceptions.Timeout:
            print("Dify API timeout")
        except requests.exceptions.HTTPError as e:
            print(f"Dify API HTTP error: {e}")
        except Exception as e:
            print(f"Unexpected error calling Dify: {type(e).__name__}: {e}")
            traceback.print_exc()

        # 使用默认值或生成的内容
        if not api_success:
            display_insight = default_insight
            display_guidance = default_guidance
        else:
            # 成功生成，更新存储
            if user["is_guest"]:
                session['last_card']['today_insight'] = today_insight
                session['last_card']['guidance'] = guidance
                session.modified = True
            else:
                conn = get_db()
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("""
                            UPDATE readings
                            SET today_insight=%s, guidance=%s
                            WHERE user_id=%s AND date=%s
                        """, (today_insight, guidance, user["id"], today))
                        conn.commit()
                finally:
                    conn.close()

    # ---------------- 确保渲染内容不为空 ----------------
    if not display_insight:
        display_insight = f"今日{card_data['name']}为你带来特别的启示。"
    if not display_guidance:
        display_guidance = "请静心感受这张牌的能量，让它指引你的方向。"

    # ---------------- 渲染模板 ----------------
    return render_template(
        "result.html",
        today_date=today.strftime("%Y-%m-%d"),
        card=card_data,
        direction=direction,
        today_insight=display_insight,
        guidance=display_guidance,
        is_guest=user["is_guest"],
        can_export=True,
        user=user  # 确保模板可以访问 user 对象
    )


@app.route("/export_reading")
def export_reading():
    """导出今日解读（主要为访客设计）"""
    user = g.user
    today = datetime.date.today()
    
    if not user["is_guest"]:
        # 登录用户重定向到统计页面
        return redirect(url_for("stats"))
    
    last_card = session.get('last_card', {})
    if not last_card or last_card.get("date") != str(today):
        flash("没有找到今日的解读记录", "error")
        return redirect(url_for("index"))
    
    # 生成导出内容
    export_content = f"""塔罗每日指引
生成日期：{today.strftime('%Y年%m月%d日')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

抽到的塔罗牌：{last_card.get('name')}
牌面方向：{last_card.get('direction')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【今日洞察】
{last_card.get('today_insight', '暂无解读内容')}

【指引建议】
{last_card.get('guidance', '暂无指引内容')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 温馨提示：
• 这是您的专属解读，请用心体会其中的启示
• 塔罗牌是内心智慧的镜子，最终的选择权在您手中
• 如需保存更多历史记录，欢迎注册账号

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

此内容由塔罗每日指引生成
愿宇宙的智慧照亮您的道路 ✨
"""
    
    # 创建响应
    response = make_response(export_content)
    response.headers["Content-Disposition"] = f"attachment; filename=tarot_reading_{today.strftime('%Y%m%d')}.txt"
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    
    return response

@app.route("/api/regenerate", methods=["POST"])
def regenerate():
    """重新生成解读内容"""
    user = g.user
    today = datetime.date.today()
    
    try:
        # 获取卡牌信息
        if not user["is_guest"]:
            conn = get_db()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT r.*, c.name, c.meaning_up, c.meaning_rev
                        FROM readings r
                        JOIN tarot_cards c ON r.card_id=c.id
                        WHERE r.user_id=%s AND r.date=%s
                    """, (user["id"], today))
                    reading = cursor.fetchone()
            finally:
                conn.close()
            
            if not reading:
                return jsonify({"success": False, "error": "未找到今日抽牌记录"}), 404
            
            card_name = reading["name"]
            direction = reading["direction"]
            card_meaning = reading[f"meaning_{'up' if direction == '正位' else 'rev'}"]
        else:
            last_card = session.get('last_card', {})
            if not last_card or last_card.get("date") != str(today):
                return jsonify({"success": False, "error": "未找到今日抽牌记录"}), 404
            
            card_name = last_card["name"]
            direction = last_card["direction"]
            card_meaning = last_card.get(f"meaning_{'up' if direction == '正位' else 'rev'}", "")
        
        # 调用 Dify API（使用相同的逻辑）
        # ... 省略 API 调用代码 ...
        
        return jsonify({
            "success": True,
            "today_insight": "重新生成的洞察内容",
            "guidance": "重新生成的指引内容"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/clear")
@login_required
def clear_cache():
    """清除今日记录（仅限登录用户）"""
    user_id = session.get('user_id')
    today = datetime.date.today()
    
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM readings WHERE user_id=%s AND date=%s", (user_id, today))
            conn.commit()
            flash("已清除今日抽牌记录", "success")
    finally:
        conn.close()
    
    return redirect(url_for("index"))

@app.route("/guest_hint")
def guest_hint():
    """访客提示页面"""
    return render_template("guest_hint.html", is_incognito=detect_incognito_mode())

def generate_device_fingerprint(request):
    """生成设备指纹"""
    ua = request.headers.get('User-Agent', '')
    lang = request.headers.get('Accept-Language', '')
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    return hashlib.md5(f"{ua}_{lang}_{ip}".encode()).hexdigest()

# ---------------- 错误处理 ----------------
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == "__main__":
    app.run(debug=True)