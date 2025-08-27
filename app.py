from flask import Flask, render_template, request, redirect, url_for, session, g
import pymysql
import random
import datetime
import uuid
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import requests

DIFY_API_KEY = "app-szUNbUL09tXTaWQZvAW0i6wm"
WORKFLOW_ID = "116f057f-53bf-4d32-a6f6-e5482cfb658e"

app = Flask(__name__)
app.secret_key = "sjd82hdn92n3ndks8d1j2k39dk20dk"

# ---------------- 数据库连接 ----------------
def get_db():
    return pymysql.connect(
        host="ruoshui233.mysql.pythonanywhere-services.com",
        user="ruoshui233",
        password="cai-6831",
        database="ruoshui233$tarot",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )

# ---------------- 用户系统 ----------------
def get_current_user():
    """获取当前登录用户，如果没有则返回 None"""
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
    """在每个请求前加载当前用户，保证 g.user 永远存在"""
    user = get_current_user()
    if not user:
        user = {"id": None, "username": None, "is_guest": True}
    g.user = user

@app.context_processor
def inject_user():
    """自动把 user 注入所有模板"""
    return {"user": g.user}

@app.template_filter("avatar_letter")
def avatar_letter(user):
    """获取用户名首字母（大写），匿名则返回“匿”"""
    if user and user.get("username"):
        return user["username"][0].upper()
    return "匿"

def login_required(f):
    """需要登录的装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# ---------------- 路由 ----------------
@app.route("/stats")
@login_required  # 确保只有登录用户可以访问
def stats():
    user = g.user  # 当前登录用户

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 查询总抽牌次数
            cursor.execute(
                "SELECT COUNT(*) AS total FROM readings WHERE user_id=%s",
                (user["id"],)
            )
            total_readings = cursor.fetchone()["total"] or 0

            # 查询最近 10 条抽牌记录
            cursor.execute(
                """
                SELECT r.date, c.name AS card_name, r.direction
                FROM readings r
                JOIN tarot_cards c ON r.card_id = c.id
                WHERE r.user_id = %s
                ORDER BY r.date DESC
                LIMIT 10
                """,
                (user["id"],)
            )
            recent_readings = cursor.fetchall()

            # 用户访问信息（可选：根据你数据库里存储的 first_visit, last_visit）
            first_visit = user.get("first_visit")  # datetime.date 对象
            last_visit = user.get("last_visit")    # datetime.date 对象
            visit_count = user.get("visit_count", 1)

    finally:
        conn.close()

    return render_template(
        "stats.html",
        user={
            "visit_count": visit_count,
            "first_visit": first_visit,
            "last_visit": last_visit
        },
        total_readings=total_readings,
        recent_readings=recent_readings
    )


@app.route("/")
def index():
    today = datetime.date.today()
    user = g.user  # 全局 user
    has_drawn = False

    if not user["is_guest"]:
        # 已登录用户，检查今天是否已经抽过牌
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM readings WHERE user_id=%s AND date=%s",
                    (user['id'], today)
                )
                result = cursor.fetchone()
                has_drawn = result is not None
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
                cursor.execute(
                    "SELECT * FROM users WHERE username = %s",
                    (username,)
                )
                user = cursor.fetchone()

                if user and check_password_hash(user['password_hash'], password):
                    session['user_id'] = user['id']
                    # 更新访问记录
                    cursor.execute(
                        "UPDATE users SET last_visit = NOW(), visit_count = visit_count + 1 WHERE id = %s",
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

        # 验证输入
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
                # 检查用户名是否已存在
                cursor.execute(
                    "SELECT id FROM users WHERE username = %s",
                    (username,)
                )
                if cursor.fetchone():
                    return render_template("register.html", error="用户名已被使用")

                # 创建新用户
                user_id = str(uuid.uuid4())
                password_hash = generate_password_hash(password)
                device_id = generate_device_fingerprint(request)

                cursor.execute("""
                    INSERT INTO users (id, username, password_hash, device_id,
                                     first_visit, last_visit, visit_count, is_guest)
                    VALUES (%s, %s, %s, %s, NOW(), NOW(), 1, FALSE)
                """, (user_id, username, password_hash, device_id))

                conn.commit()

                # 自动登录
                session['user_id'] = user_id

                return redirect(url_for('index'))

        finally:
            conn.close()

    return render_template("register.html")

@app.route("/logout")
def logout():
    """退出登录"""
    session.clear()
    return redirect(url_for('index'))

@app.route("/draw", methods=["POST"])
def draw_card():
    user = g.user
    today = datetime.date.today()
    direction = random.choice(["正位", "逆位"])

    # ------------------ 检查是否已抽过 ------------------
    if not user["is_guest"]:
        # 登录用户，从数据库检查
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM readings WHERE user_id=%s AND date=%s",
                    (user["id"], today)
                )
                if cursor.fetchone():
                    # 已抽过，直接跳转结果页
                    return redirect(url_for("result"))
        finally:
            conn.close()
    else:
        # 访客用户，从 session 检查
        last_card = session.get('last_card')
        if last_card and last_card.get("date") == str(today):
            return redirect(url_for("result"))

    # ------------------ 抽牌逻辑 ------------------
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 从塔罗牌表随机抽一张
            cursor.execute("SELECT * FROM tarot_cards ORDER BY RAND() LIMIT 1")
            card = cursor.fetchone()

            if not card:
                cursor.execute("SELECT * FROM cards ORDER BY RAND() LIMIT 1")
                card = cursor.fetchone()

            if not card:
                return "错误：数据库中没有塔罗牌数据"

            # 登录用户保存到数据库
            if not user["is_guest"]:
                cursor.execute(
                    "INSERT INTO readings (user_id, date, card_id, direction) VALUES (%s, %s, %s, %s)",
                    (user["id"], today, card["id"], direction)
                )
                conn.commit()
    finally:
        conn.close()

    # ------------------ 存 session 临时保存访客抽牌结果 ------------------
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

    # ---------------- 获取抽牌记录 ----------------
    if not user["is_guest"]:
        user_id = user["id"]
        conn = get_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """SELECT r.*, c.name, c.image, c.guidance, c.meaning_up, c.meaning_rev
                       FROM readings r
                       JOIN tarot_cards c ON r.card_id=c.id
                       WHERE r.user_id=%s AND r.date=%s""",
                    (user_id, today)
                )
                reading = cursor.fetchone()

                if not reading:
                    cursor.execute(
                        """SELECT r.*, c.name, c.image, c.guidance, c.meaning_up, c.meaning_rev
                           FROM readings r
                           JOIN cards c ON r.card_id=c.id
                           WHERE r.user_id=%s AND r.date=%s""",
                        (user_id, today)
                    )
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

    else:  # ---------------- 访客 ----------------
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

    # ---------------- 调用 Dify Workflow ----------------
    today_insight = "今日运势解读暂未生成"
    guidance = "运势指引暂未生成"

    try:
        workflow_url = f"https://ai-bot-new.dalongyun.com/v1/workflows/{WORKFLOW_ID}/run"
        headers = {
            "Authorization": f"Bearer {DIFY_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": {
                "card_name": card_data["name"],
                "direction": direction
            }
        }

        resp = requests.post(workflow_url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        output_str = data.get("output", "")

        if output_str:
            # ---------------- 解析 LLM 输出字符串 ----------------
            # 方式：查找 "今日运势解读：" 和 "运势指引：" 标签
            import re
            insight_match = re.search(r"今日运势解读[:：]\s*(.*?)(?:\n|$)", output_str)
            guidance_match = re.search(r"运势指引[:：]\s*(.*?)(?:\n|$)", output_str)

            if insight_match:
                today_insight = insight_match.group(1).strip()
            if guidance_match:
                guidance = guidance_match.group(1).strip()

    except Exception as e:
        print("调用 Dify Workflow 出错:", e)

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
            cursor.execute(
                "DELETE FROM readings WHERE user_id=%s AND date=%s",
                (user_id, today)
            )
            conn.commit()
    finally:
        conn.close()

    return redirect(url_for("index"))

@app.route("/stats")
@login_required
def user_stats():
    """用户统计页面"""
    user_id = session.get('user_id')

    conn = get_db()
    try:
        with conn.cursor() as cursor:
            # 获取用户信息
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()

            # 获取抽牌统计
            cursor.execute(
                "SELECT COUNT(*) as total_readings FROM readings WHERE user_id = %s",
                (user_id,)
            )
            stats = cursor.fetchone()

            # 获取最近记录
            cursor.execute(
                """SELECT r.date, r.direction,
                   COALESCE(tc.name, c.name) as card_name
                   FROM readings r
                   LEFT JOIN tarot_cards tc ON r.card_id = tc.id
                   LEFT JOIN cards c ON r.card_id = c.id
                   WHERE r.user_id = %s
                   ORDER BY r.date DESC LIMIT 7""",
                (user_id,)
            )
            recent_readings = cursor.fetchall()
    finally:
        conn.close()

    return render_template(
        "stats.html",
        user=user,
        total_readings=stats['total_readings'] if stats else 0,
        recent_readings=recent_readings
    )

# ---------------- 工具函数 ----------------
def generate_device_fingerprint(request):
    """生成设备指纹"""
    user_agent = request.headers.get('User-Agent', '')
    accept_language = request.headers.get('Accept-Language', '')
    fingerprint_data = f"{user_agent}_{accept_language}"
    return hashlib.md5(fingerprint_data.encode()).hexdigest()

# ---------------- 数据库迁移 ----------------
def migrate_database():
    """添加必要的数据库字段"""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = 'users'
                AND TABLE_SCHEMA = 'ruoshui233$tarot'
                AND COLUMN_NAME IN ('username', 'password_hash', 'is_guest')
            """)
            existing_columns = [row['COLUMN_NAME'] for row in cursor.fetchall()]

            if 'username' not in existing_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN username VARCHAR(50) UNIQUE")

            if 'password_hash' not in existing_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)")

            if 'is_guest' not in existing_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN is_guest BOOLEAN DEFAULT TRUE")

            conn.commit()
            print("数据库迁移完成")

    except Exception as e:
        print(f"迁移错误: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
    app.run(debug=True)
