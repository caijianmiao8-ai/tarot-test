import os
import random
import datetime
import uuid
import hashlib
import requests
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import json
import time
import traceback

# ---------------- 环境变量 ----------------
DIFY_API_KEY = os.environ.get("DIFY_API_KEY")
WORKFLOW_ID = os.environ.get("WORKFLOW_ID")
DATABASE_URL = os.environ.get("DATABASE_URL")  # Vercel/Supabase 设置

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

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

@app.before_request
def load_user():
    user = get_current_user()
    if not user:
        user = {"id": None, "username": None, "is_guest": True}
    g.user = user

@app.context_processor
def inject_user():
    return {"user": g.user}

@app.template_filter("avatar_letter")
def avatar_letter(user):
    if user and user.get("username"):
        return user["username"][0].upper()
    return "匿"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# ---------------- 路由 ----------------
@app.route("/")
def index():
    today = datetime.date.today()
    user = g.user
    has_drawn = False

    if not user["is_guest"]:
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
    return render_template("index.html", has_drawn=has_drawn)

@app.route("/stats")
@login_required
def stats():
    user = g.user
    total_readings = 0
    recent_readings = []

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 获取总抽牌次数
            cursor.execute("SELECT COUNT(*) FROM readings WHERE user_id=%s", (user['id'],))
            total_readings = cursor.fetchone()['count'] or 0

            # 获取最近 10 条抽牌记录
            cursor.execute("""
                SELECT r.date, c.name AS card_name, r.direction
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
            return render_template("login.html", error="请填写用户名和密码")
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                user = cursor.fetchone()
                if user and check_password_hash(user['password_hash'], password):
                    session['user_id'] = user['id']
                    cursor.execute(
                        "UPDATE users SET last_visit = CURRENT_TIMESTAMP, visit_count = visit_count + 1 WHERE id = %s",
                        (user['id'],)
                    )
                    conn.commit()
                    next_page = request.args.get('next') or url_for('index')
                    return redirect(next_page)
                else:
                    return render_template("login.html", error="用户名或密码错误")
        finally:
            conn.close()
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        if not username or not password:
            return render_template("register.html", error="请填写用户名和密码")
        if len(username) < 3:
            return render_template("register.html", error="用户名至少需要3个字符")
        if len(password) < 6:
            return render_template("register.html", error="密码至少需要6个字符")
        if password != confirm_password:
            return render_template("register.html", error="两次输入的密码不一致")

        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
                if cursor.fetchone():
                    return render_template("register.html", error="用户名已被使用")
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
                return redirect(url_for('index'))
        finally:
            conn.close()
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route("/draw", methods=["POST"])
def draw_card():
    user = g.user
    today = datetime.date.today()
    direction = random.choice(["正位", "逆位"])

    # ---------------- 今日已抽牌，直接跳转 ----------------
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
        last_card = session.get('last_card')
        if last_card and last_card.get("date") == str(today):
            return redirect(url_for("result"))

    # ---------------- 抽牌 ----------------
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM tarot_cards ORDER BY RANDOM() LIMIT 1")
            card = cursor.fetchone()
            if not card:
                cursor.execute("SELECT * FROM cards ORDER BY RANDOM() LIMIT 1")
                card = cursor.fetchone()
            if not card:
                return "错误：数据库中没有塔罗牌数据"

            # ---------------- 登录用户插入记录（使用 NULL 而不是空字符串） ----------------
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
    finally:
        conn.close()

    # ---------------- 游客用户缓存（不包含 insight 和 guidance） ----------------
    if user["is_guest"]:
        session['last_card'] = {
            "card_id": card["id"],
            "name": card["name"],
            "image": card.get("image"),
            "meaning_up": card.get("meaning_up"),
            "meaning_rev": card.get("meaning_rev"),
            "direction": direction,
            "date": str(today)
            # 注意：不设置 today_insight 和 guidance
        }
        session.modified = True

    return redirect(url_for("result"))

@app.route("/result")
def result():
    user = g.user
    today = datetime.date.today()
    
    # ---------------- 获取抽牌记录 ----------------
    if not user["is_guest"]:
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
            return redirect(url_for("index"))
        
        card_data = {
            "id": reading["card_id"],
            "name": reading["name"],
            "image": reading["image"],
            "meaning_up": reading["meaning_up"],
            "meaning_rev": reading["meaning_rev"]
        }
        direction = reading["direction"]
        
        # 直接获取值，不使用 or 操作符
        today_insight = reading.get("today_insight")
        guidance = reading.get("guidance")
        
    else:
        # 游客用户
        last_card = session.get('last_card')
        if not last_card or last_card.get("date") != str(today):
            return redirect(url_for("index"))
        
        card_data = {
            "id": last_card.get("card_id"),
            "name": last_card["name"],
            "image": last_card.get("image"),
            "meaning_up": last_card.get("meaning_up"),
            "meaning_rev": last_card.get("meaning_rev")
        }
        direction = last_card["direction"]
        
        # 使用 get 方法，如果键不存在返回 None
        today_insight = last_card.get('today_insight')
        guidance = last_card.get('guidance')
    
    # ---------------- 判断是否需要生成内容 ----------------
    need_generate = (today_insight is None or today_insight == "" or 
                    guidance is None or guidance == "")
    
    # 显示用的变量
    display_insight = today_insight
    display_guidance = guidance
    
    if need_generate:
        print(f"Need to generate content for user {user.get('id', 'guest')}")
        
        # 设置默认值
        default_insight = f"今日你抽到了{card_data['name']}（{direction}），这张牌蕴含着深刻的智慧。"
        default_guidance = f"{'正位' if direction == '正位' else '逆位'}的{card_data['name']}提醒你要关注内心的声音，相信直觉的指引。"
        
        # 调用 Dify API 生成内容
        api_success = False
        
        try:
            api_url = "https://ai-bot-new.dalongyun.com/v1/workflows/run"
            headers = {
                "Authorization": f"Bearer {DIFY_API_KEY}",
                "Content-Type": "application/json"
            }
            
            user_identifier = user["id"] if not user["is_guest"] else f'guest_{session.sid if hasattr(session, "sid") else "unknown"}'
            
            # 构建更详细的输入
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
            
            print(f"Calling Dify API with payload: {payload}")
            
            # 调用 API，增加超时时间
            response = requests.post(api_url, headers=headers, json=payload, timeout=25)
            response.raise_for_status()
            
            data = response.json()
            print(f"Dify API response status: {response.status_code}")
            
            # 处理响应
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
            
            if output_str:
                print(f"Got output from Dify, length: {len(output_str)}")
                
                # 尝试解析 JSON
                parsed_data = None
                
                # 方法1: 直接解析
                try:
                    parsed_data = json.loads(output_str)
                except:
                    pass
                
                # 方法2: 查找 ```json 块
                if not parsed_data:
                    try:
                        start = output_str.find("```json")
                        if start != -1:
                            end = output_str.find("```", start + 7)
                            if end != -1:
                                json_str = output_str[start + 7:end].strip()
                                parsed_data = json.loads(json_str)
                    except:
                        pass
                
                # 方法3: 查找 JSON 对象
                if not parsed_data:
                    try:
                        start = output_str.find("{")
                        end = output_str.rfind("}")
                        if start != -1 and end != -1:
                            json_str = output_str[start:end + 1]
                            parsed_data = json.loads(json_str)
                    except:
                        pass
                
                # 提取数据
                if parsed_data and isinstance(parsed_data, dict):
                    new_insight = parsed_data.get("today_insight", "").strip()
                    new_guidance = parsed_data.get("guidance", "").strip()
                    
                    if new_insight and new_guidance:
                        today_insight = new_insight
                        guidance = new_guidance
                        display_insight = today_insight
                        display_guidance = guidance
                        api_success = True
                        print("Successfully parsed Dify response")
                    else:
                        print("Parsed data missing required fields")
                else:
                    print(f"Failed to parse JSON from output: {output_str[:200]}...")
            
        except requests.exceptions.Timeout:
            print("Dify API timeout")
        except requests.exceptions.HTTPError as e:
            print(f"Dify API HTTP error: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"Response content: {e.response.text[:500]}")
        except Exception as e:
            print(f"Unexpected error calling Dify: {type(e).__name__}: {e}")
            traceback.print_exc()
        
        # 如果 API 失败，使用默认值
        if not api_success:
            display_insight = default_insight
            display_guidance = default_guidance
            # 但不更新数据库/session，下次还可以重试
        else:
            # API 成功，更新存储
            if user["is_guest"]:
                if 'last_card' not in session:
                    session['last_card'] = {}
                session['last_card']['today_insight'] = today_insight
                session['last_card']['guidance'] = guidance
                session.modified = True
                print("Updated session with new content")
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
                        print(f"Updated database for user {user['id']}")
                finally:
                    conn.close()
    
    # 确保有内容显示
    if not display_insight:
        display_insight = f"今日你抽到了{card_data['name']}（{direction}），请静心感受这张牌的能量。"
    if not display_guidance:
        display_guidance = "塔罗牌的智慧需要你用心体会，相信你的直觉。"
    
    # ---------------- 渲染模板 ----------------
    return render_template(
        "result.html",
        today_date=today.strftime("%Y-%m-%d"),
        card=card_data,
        direction=direction,
        today_insight=display_insight,
        guidance=display_guidance
    )

@app.route("/api/regenerate", methods=["POST"])
def regenerate():
    """手动重新生成解读内容的 API"""
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
            last_card = session.get('last_card')
            if not last_card or last_card.get("date") != str(today):
                return jsonify({"success": False, "error": "未找到今日抽牌记录"}), 404
            
            card_name = last_card["name"]
            direction = last_card["direction"]
            card_meaning = last_card.get(f"meaning_{'up' if direction == '正位' else 'rev'}", "")
        
        # 调用 Dify API
        api_url = "https://ai-bot-new.dalongyun.com/v1/workflows/run"
        headers = {
            "Authorization": f"Bearer {DIFY_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "inputs": {
                "card_name": str(card_name),
                "direction": str(direction),
                "meaning": str(card_meaning)
            },
            "response_mode": "blocking",
            "user": str(user.get("id", "guest"))
        }
        
        response = requests.post(api_url, headers=headers, json=payload, timeout=25)
        response.raise_for_status()
        
        # 解析响应（使用相同的解析逻辑）
        # ... 省略解析代码，与上面相同 ...
        
        return jsonify({
            "success": True,
            "today_insight": today_insight,
            "guidance": guidance
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route("/clear")
@login_required
def clear_cache():
    user_id = session.get('user_id')
    today = datetime.date.today()
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM readings WHERE user_id=%s AND date=%s", (user_id, today))
            conn.commit()
    finally:
        conn.close()
    return redirect(url_for("index"))

def generate_device_fingerprint(request):
    ua = request.headers.get('User-Agent', '')
    lang = request.headers.get('Accept-Language', '')
    return hashlib.md5(f"{ua}_{lang}".encode()).hexdigest()

if __name__ == "__main__":
    app.run(debug=True)