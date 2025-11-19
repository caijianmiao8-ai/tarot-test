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
from authlib.integrations.flask_client import OAuth

# ---------------- 环境变量 ----------------
DIFY_API_KEY = os.environ.get("DIFY_API_KEY")
WORKFLOW_ID = os.environ.get("WORKFLOW_ID")
DATABASE_URL = os.environ.get("DATABASE_URL")  # Vercel/Supabase 设置

# Google OAuth 配置
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
# 自动检测服务器 URL，支持本地和 Vercel 部署
SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:5000")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

# 初始化 OAuth
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
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
            if not user["is_guest"]:
                cursor.execute(
                    "INSERT INTO readings (user_id, date, card_id, direction) VALUES (%s, %s, %s, %s)",
                    (user["id"], today, card["id"], direction)
                )
                conn.commit()
    finally:
        conn.close()

    session['last_card'] = {
        "name": card["name"],
        "image": card.get("image"),
        "guidance": card.get("guidance"),
        "meaning_up": card.get("meaning_up"),
        "meaning_rev": card.get("meaning_rev"),
        "direction": direction,
        "date": str(today)
    }
    return redirect(url_for("result"))

@app.route("/result")
def result():
    user = g.user
    today = datetime.date.today()
    if not user["is_guest"]:
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT r.*, c.name, c.image, c.guidance, c.meaning_up, c.meaning_rev
                    FROM readings r
                    JOIN tarot_cards c ON r.card_id=c.id
                    WHERE r.user_id=%s AND r.date=%s
                """, (user["id"], today))
                reading = cursor.fetchone()
                if not reading:
                    cursor.execute("""
                        SELECT r.*, c.name, c.image, c.guidance, c.meaning_up, c.meaning_rev
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
            "name": reading["name"],
            "image": reading["image"],
            "guidance": reading["guidance"],
            "meaning_up": reading["meaning_up"],
            "meaning_rev": reading["meaning_rev"]
        }
        direction = reading["direction"]
    else:
        last_card = session.get('last_card')
        if not last_card or last_card.get("date") != str(today):
            return redirect(url_for("index"))
        card_data = {
            "name": last_card["name"],
            "image": last_card.get("image"),
            "guidance": last_card.get("guidance"),
            "meaning_up": last_card.get("meaning_up"),
            "meaning_rev": last_card.get("meaning_rev")
        }
        direction = last_card["direction"]

    today_insight = "今日运势解读暂未生成"
    guidance = "运势指引暂未生成"
    try:
        workflow_url = f"https://ai-bot-new.dalongyun.com/v1/workflows/{WORKFLOW_ID}/run"
        headers = {"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"}
        payload = {"input": {"card_name": card_data["name"], "direction": direction}}
        resp = requests.post(workflow_url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        output_str = data.get("output", "")
        if output_str:
            import re
            insight_match = re.search(r"今日运势解读[:：]\s*(.*?)(?:\n|$)", output_str)
            guidance_match = re.search(r"运势指引[:：]\s*(.*?)(?:\n|$)", output_str)
            if insight_match:
                today_insight = insight_match.group(1).strip()
            if guidance_match:
                guidance = guidance_match.group(1).strip()
    except Exception as e:
        print("调用 Dify Workflow 出错:", e)

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

# ---------------- Google OAuth 路由 ----------------
@app.route("/auth/google")
def google_login():
    """重定向到 Google 登录"""
    # 动态生成回调 URL
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/auth/google/callback")
def google_callback():
    """处理 Google OAuth 回调"""
    try:
        # 获取访问令牌
        token = google.authorize_access_token()
        # 获取用户信息
        user_info = token.get('userinfo')

        if not user_info:
            return render_template("error.html", error="无法获取 Google 用户信息")

        google_id = user_info.get('sub')
        email = user_info.get('email')
        name = user_info.get('name')
        picture = user_info.get('picture')

        if not google_id or not email:
            return render_template("error.html", error="Google 账户信息不完整")

        conn = get_db()
        try:
            with conn.cursor() as cursor:
                # 检查是否已存在 Google OAuth 用户
                cursor.execute(
                    "SELECT * FROM users WHERE oauth_provider = 'google' AND oauth_id = %s",
                    (google_id,)
                )
                user = cursor.fetchone()

                if user:
                    # 已存在，直接登录
                    session['user_id'] = user['id']
                    cursor.execute(
                        "UPDATE users SET last_visit = CURRENT_TIMESTAMP, visit_count = visit_count + 1 WHERE id = %s",
                        (user['id'],)
                    )
                    conn.commit()
                    return redirect(url_for('index'))

                # 检查邮箱是否已被其他账号使用
                cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
                existing_user = cursor.fetchone()

                if existing_user:
                    # 邮箱已存在，让用户选择是否关联
                    session['pending_oauth'] = {
                        'provider': 'google',
                        'oauth_id': google_id,
                        'email': email,
                        'name': name,
                        'picture': picture,
                        'existing_user_id': existing_user['id']
                    }
                    return redirect(url_for('link_account'))

                # 创建新用户
                user_id = str(uuid.uuid4())
                device_id = generate_device_fingerprint(request)
                cursor.execute("""
                    INSERT INTO users (id, username, email, oauth_provider, oauth_id,
                                       avatar_url, device_id, first_visit, last_visit,
                                       visit_count, is_guest)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, FALSE)
                """, (user_id, name, email, 'google', google_id, picture, device_id))
                conn.commit()

                session['user_id'] = user_id
                return redirect(url_for('index'))

        finally:
            conn.close()

    except Exception as e:
        print(f"Google OAuth 错误: {e}")
        return render_template("error.html", error=f"Google 登录失败: {str(e)}")

@app.route("/auth/link-account", methods=["GET", "POST"])
def link_account():
    """账号关联页面"""
    pending_oauth = session.get('pending_oauth')
    if not pending_oauth:
        return redirect(url_for('login'))

    if request.method == "POST":
        action = request.form.get('action')

        conn = get_db()
        try:
            with conn.cursor() as cursor:
                if action == "link":
                    # 关联到现有账号
                    cursor.execute("""
                        UPDATE users
                        SET oauth_provider = %s,
                            oauth_id = %s,
                            email = %s,
                            avatar_url = %s
                        WHERE id = %s
                    """, (
                        pending_oauth['provider'],
                        pending_oauth['oauth_id'],
                        pending_oauth['email'],
                        pending_oauth.get('picture'),
                        pending_oauth['existing_user_id']
                    ))
                    conn.commit()

                    session['user_id'] = pending_oauth['existing_user_id']
                    session.pop('pending_oauth', None)

                    cursor.execute(
                        "UPDATE users SET last_visit = CURRENT_TIMESTAMP, visit_count = visit_count + 1 WHERE id = %s",
                        (pending_oauth['existing_user_id'],)
                    )
                    conn.commit()

                    return redirect(url_for('index'))

                elif action == "create_new":
                    # 创建新账号
                    user_id = str(uuid.uuid4())
                    device_id = generate_device_fingerprint(request)

                    # 为避免邮箱冲突，在新账号的邮箱后添加标识
                    new_email = f"{pending_oauth['oauth_id']}@google-oauth.local"

                    cursor.execute("""
                        INSERT INTO users (id, username, email, oauth_provider, oauth_id,
                                           avatar_url, device_id, first_visit, last_visit,
                                           visit_count, is_guest)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, FALSE)
                    """, (
                        user_id,
                        pending_oauth['name'],
                        new_email,
                        pending_oauth['provider'],
                        pending_oauth['oauth_id'],
                        pending_oauth.get('picture'),
                        device_id
                    ))
                    conn.commit()

                    session['user_id'] = user_id
                    session.pop('pending_oauth', None)
                    return redirect(url_for('index'))

        finally:
            conn.close()

    return render_template("link_account.html", oauth_data=pending_oauth)
