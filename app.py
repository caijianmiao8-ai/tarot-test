import os
import random
import datetime
import uuid
import hashlib
import requests
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session, g
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import json

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

def generate_device_fingerprint(request):
    """生成访客设备指纹"""
    ua = request.headers.get('User-Agent', '')
    lang = request.headers.get('Accept-Language', '')
    return hashlib.md5(f"{ua}_{lang}".encode()).hexdigest()

@app.route("/draw_card", methods=["POST"])
def draw_card():
    user = get_current_user()  # 获取当前用户
    today = datetime.date.today()
    guest_id = generate_device_fingerprint(request) if user["is_guest"] else None

    card_data = {}
    direction = ""
    today_insight = ""
    guidance = ""

    # ---------------- 查询今日抽牌记录 ----------------
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            if user["is_guest"]:
                cursor.execute("""
                    SELECT card, direction, today_insight, guidance
                    FROM readings
                    WHERE guest_id=%s AND date=%s
                """, (guest_id, today))
            else:
                cursor.execute("""
                    SELECT card, direction, today_insight, guidance
                    FROM readings
                    WHERE user_id=%s AND date=%s
                """, (user["id"], today))
            record = cursor.fetchone()
    finally:
        conn.close()

    if record:
        # 已有记录
        card_data = record[0] or {}
        direction = record[1] or ""
        today_insight = record[2] or ""
        guidance = record[3] or ""
    else:
        # ---------------- 生成新牌 ----------------
        card_data, direction = draw_random_card()  # 你现有的抽牌逻辑
        # ---------------- 调用 Dify API ----------------
        try:
            response = requests.post(
                "DIFY_API_URL",
                json={"card": card_data},
                timeout=10
            )
            response.raise_for_status()
            json_text = response.text
            json_data = json.loads(json_text)
            today_insight = json_data.get("today_insight", "")
            guidance = json_data.get("guidance", "")
        except Exception as e:
            print("调用 Dify LLM 出错:", e)

        # ---------------- 保存到数据库 ----------------
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO readings (user_id, guest_id, date, card, direction, today_insight, guidance)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    None if user["is_guest"] else user["id"],
                    guest_id,
                    today,
                    card_data,
                    direction,
                    today_insight,
                    guidance
                ))
                conn.commit()
        finally:
            conn.close()

    # ---------------- 缓存到 session ----------------
    if user["is_guest"]:
        session['last_card'] = {
            "card": card_data,
            "direction": direction,
            "today_insight": today_insight,
            "guidance": guidance,
            "date": str(today)
        }

    # ---------------- 渲染模板 ----------------
    return render_template(
        "result.html",
        today_date=today.strftime("%Y-%m-%d"),
        card=card_data,
        direction=direction,
        today_insight=today_insight,
        guidance=guidance
    )




@app.route("/result")
def result():
    user = g.user
    today = datetime.date.today()

    if not user["is_guest"]:
        # ---------------- 登录用户从数据库读取 ----------------
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT r.*, c.name, c.image, c.guidance as db_guidance, c.meaning_up, c.meaning_rev
                    FROM readings r
                    JOIN tarot_cards c ON r.card_id=c.id
                    WHERE r.user_id=%s AND r.date=%s
                """, (user["id"], today))
                reading = cursor.fetchone()
        finally:
            conn.close()

        if not reading:
            return redirect(url_for("index"))

        card_data = {
            "name": reading["name"],
            "image": reading["image"],
            "meaning_up": reading["meaning_up"],
            "meaning_rev": reading["meaning_rev"]
        }
        direction = reading["direction"]
        today_insight = reading.get("today_insight") or "今日运势解读暂未生成"
        guidance = reading.get("guidance") or "运势指引暂未生成"

    else:
        # ---------------- 访客从数据库读取 ----------------
        guest_id = generate_device_fingerprint(request)
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT card, direction, today_insight, guidance
                    FROM readings
                    WHERE guest_id=%s AND date=%s
                """, (guest_id, today))
                record = cursor.fetchone()
        finally:
            conn.close()

        if not record:
            return redirect(url_for("index"))

        card_data = record[0]  # 如果是 JSON 或字典，请按你的存储方式调整
        direction = record[1]
        today_insight = record[2] or "今日运势解读暂未生成"
        guidance = record[3] or "运势指引暂未生成"

    # ---------------- 调用 Dify LLM（仅当缓存不存在时） ----------------
    if not today_insight or today_insight.startswith("今日运势解读暂未生成"):
        try:
            api_url = "https://ai-bot-new.dalongyun.com/v1/workflows/run"
            headers = {
                "Authorization": f"Bearer {DIFY_API_KEY}",
                "Content-Type": "application/json"
            }

            user_id = session.get('user_id') or guest_id
            payload = {
                "inputs": {
                    "card_name": str(card_data.get("name", "")),
                    "direction": str(direction)
                },
                "response_mode": "blocking",
                "user": str(user_id)
            }

            resp = requests.post(api_url, headers=headers, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            output_str = data.get("data", {}).get("outputs", {}).get("text", "")

            import json
            # ---------------- 解析 JSON 输出 ----------------
            try:
                json_start = output_str.find("```json")
                json_end = output_str.find("```", json_start + 1)
                if json_start != -1 and json_end != -1:
                    json_text = output_str[json_start + len("```json"):json_end].strip()
                    json_data = json.loads(json_text)
                    today_insight = json_data.get("today_insight", today_insight)
                    guidance = json_data.get("guidance", guidance)
            except Exception as e:
                print("解析 Dify LLM 输出出错:", e)

            # ---------------- 缓存结果 ----------------
            conn = get_db()
            try:
                with conn.cursor() as cursor:
                    if user["is_guest"]:
                        cursor.execute("""
                            UPDATE readings
                            SET today_insight=%s, guidance=%s
                            WHERE guest_id=%s AND date=%s
                        """, (today_insight, guidance, guest_id, today))
                    else:
                        cursor.execute("""
                            UPDATE readings
                            SET today_insight=%s, guidance=%s
                            WHERE user_id=%s AND date=%s
                        """, (today_insight, guidance, user["id"], today))
                    conn.commit()
            finally:
                conn.close()

        except requests.exceptions.HTTPError as e:
            print("调用 Dify LLM 出错:", e, e.response.text)
        except Exception as e:
            print("调用 Dify LLM 出错:", e)

    # ---------------- 渲染模板 ----------------
    return render_template(
        "result.html",
        today_date=today.strftime("%Y-%m-%d"),
        card=card_data,
        direction=direction,
        today_insight=today_insight,
        guidance=guidance
    )





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
