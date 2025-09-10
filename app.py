"""
塔罗每日指引 - 主应用
重构版本，支持 Vercel 部署和未来迁移
"""
import os
import json, requests
import random
import traceback
import uuid
import io
import base64
from urllib.parse import urlencode
from datetime import datetime, timedelta
from functools import wraps
import time
import logging
from contextlib import contextmanager
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify, make_response, send_file
import hashlib
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
    PersonaService,
    ShareService # ★ 必须补上
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

# Playwright
try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

# --- Playwright 启动器（全局单例） ---
_browser = None
_context = None

def get_browser():
    global _browser, _context
    if _browser is not None and _context is not None:
        return _browser, _context
    if sync_playwright is None:
        raise RuntimeError("Playwright 未安装，请 pip install playwright 并 playwright install chromium")
    pw = sync_playwright().start()
    _browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
    _context = _browser.new_context(
        device_scale_factor=2,  # 高清出图
        viewport={"width": 420, "height": 760},  # 初始视口，稍后以元素裁剪为准
        java_script_enabled=True,
    )
    return _browser, _context

def screenshot_share_card(url: str, selector: str = "#shareCardRoot") -> bytes:
    """
    打开 share_card 页面，等待稳定后，截图卡片根节点（selector），返回 PNG bytes
    """
    browser, context = get_browser()
    page = context.new_page()
    # 禁止动画可提高稳定性（如需）
    page.add_style_tag(content="""
      * { animation: none !important; transition: none !important; }
    """)
    # 打开页面
    page.goto(url, wait_until="networkidle", timeout=20000)
    # 等待字体与布局稳定
    try:
        page.wait_for_function("document.fonts && document.fonts.ready", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(300)  # 轻等

    # 选择元素并截图（clip 元素）
    el = page.query_selector(selector)
    if not el:
        # 兜底整页截图
        png = page.screenshot(type="png", full_page=True)
    else:
        png = el.screenshot(type="png")
    page.close()
    return png


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


# app.py 顶部合适位置
def flatten_fortune_for_share(f):
    """把 fortune_data 拍平为前端友好的结构，不改变原字段，只是补充"""
    import copy
    f = copy.deepcopy(f or {})

    # 1) 幸运元素拍平
    lucky = (f.get('lucky_elements') or {})
    f.setdefault('lucky_color', lucky.get('color', ''))
    f.setdefault('lucky_number', lucky.get('number', ''))
    f.setdefault('lucky_hour', lucky.get('hour', ''))
    f.setdefault('lucky_direction', lucky.get('direction', ''))

    # 2) 维度转换为 map + 文本（兼容 parseDimensions）
    dims = f.get('dimensions') or []
    if isinstance(dims, list):
        f['dimensions_map'] = {d.get('name'): float(d.get('stars') or d.get('score') or 0) 
                               for d in dims if d.get('name')}
        f['dimensions'] = "\n".join(
            f"{d.get('name')}：{d.get('stars', d.get('score'))}星（{d.get('level','')})"
            for d in dims if d.get('name')
        )

    # 3) 把 fortune_text 的几个关键字段提升一层，方便前端取用
    ft = f.get('fortune_text') or {}
    for k in ('summary', 'dimension_advice', 'do', 'dont'):
        if k in ft and k not in f:
            f[k] = ft[k]

    return f


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

def generate_qr_code(data: str) -> str:
    """
    返回形如 'data:image/png;base64,...' 的 Data URL。
    若本地缺少 qrcode，则优雅降级为 None。
    """
    try:
        import qrcode
        from PIL import Image
        qr = qrcode.QRCode(
            version=1, error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6, border=2
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception as e:
        # 不中断主流程，前端可用 share_url 自行渲染第三方二维码（或展示链接）
        print(f"[generate_qr_code] fallback: {e}")
        return None



# ===== Cron 调度：按日枚举会话并触发摘要 Workflow =====
from flask import request, jsonify
from datetime import datetime, timedelta
# ==== imports（若已存在可忽略） ====
import json
from psycopg2.extras import Json
import requests
from config import Config

def _webhook_authorized():
    """
    允许以下任一方式通过：
      - Header: X-WEBHOOK-SECRET: <Config.WEBHOOK_SECRET>
      - Header: Authorization: Bearer <Config.WEBHOOK_SECRET>
      - Query:  ?token=<Config.WEBHOOK_SECRET>   (便于手工调试)
    """
    try:
        if request.headers.get("X-WEBHOOK-SECRET") == Config.WEBHOOK_SECRET:
            return True
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth.split(" ", 1)[1] == Config.WEBHOOK_SECRET:
            return True
        if request.args.get("token") == Config.WEBHOOK_SECRET:
            return True
    except Exception:
        pass
    return False

# ==== 触发 Dify 摘要 Workflow（轻量触发，不拼消息） ====
def _run_summary_workflow(user_ref: str,
                          conversation_id: str,
                          day_key: str,
                          scope: str,
                          persona: str,
                          extra_inputs: dict | None = None,
                          timeout: int = 20):
    """
    触发 Dify 的“会话摘要 Workflow”。这里只传轻量 inputs，
    真正的“拉历史+总结”在 Dify Workflow 内部完成（HTTP Request 节点访问 /v1/messages）。
    返回: (ok: bool, info: dict)
    """
    api_key = getattr(Config, "DIFY_SUM_WORKFLOW_API_KEY", "")
    if not api_key:
        return False, {"error": "Missing env DIFY_SUM_WORKFLOW_API_KEY"}

    base = getattr(Config, "DIFY_API_BASE", "https://api.dify.ai").rstrip("/")
    url = f"{base}/v1/workflows/run"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {
            "user": user_ref,
            "conversation_id": conversation_id,
            "day_key": str(day_key),
            "scope": scope,
            "persona": persona,
            **(extra_inputs or {})
        },
        # 触发即可；不依赖流式
        "response_mode": "blocking"
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
        ok = 200 <= r.status_code < 300
        try:
            body = r.json()
        except Exception:
            body = {"text": r.text[:2000]}
        if ok:
            return True, body
        else:
            return False, {"status_code": r.status_code, "body": body}
    except requests.RequestException as e:
        return False, {"error": str(e)}

# —— 小工具：鉴权（支持 Vercel Cron 或 token）——
def _cron_authorized():
    """
    通过以下任一方式鉴权：
      1) Vercel Cron 自带请求头：x-vercel-cron: 1
      2) Header: X-CRON-SECRET: <Config.CRON_SECRET>
      3) Query:  ?token=<Config.CRON_SECRET>
      4) Header: Authorization: Bearer <Config.CRON_SECRET>
    """
    try:
        if request.headers.get("x-vercel-cron") == "1":
            return True
        if request.headers.get("X-CRON-SECRET") == Config.CRON_SECRET:
            return True
        if request.args.get("token") == Config.CRON_SECRET:
            return True
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth.split(" ", 1)[1] == Config.CRON_SECRET:
            return True
    except Exception:
        pass
    return False

# —— 小工具：解析查询参数（兼容 GET/POST）——
def _read_params():
    # GET 参数
    scope_filter = request.args.get("scope")  # guided | spread | all/None
    only_missing = request.args.get("only_missing", "1") in ("1", "true", "True")
    limit = int(request.args.get("limit", "300"))  # 默认 300，比 10000 安全很多
    after_id = request.args.get("after_id")  # 分页用：仅取 id > after_id 的会话
    day_key_override = request.args.get("day_key")  # 允许指定某天，格式 YYYY-MM-DD

    # 兼容 POST JSON（手工触发时也可以传）
    j = request.get_json(silent=True) or {}
    scope_filter = j.get("scope", scope_filter)
    if "only_missing" in j:
        only_missing = str(j.get("only_missing")).lower() in ("1", "true")
    limit = int(j.get("limit", limit))
    after_id = j.get("after_id", after_id)
    day_key_override = j.get("day_key", day_key_override)

    return scope_filter, only_missing, limit, after_id, day_key_override

# —— 小工具：本地切日 —— 
def _now_local():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(getattr(Config, "APP_TIMEZONE", "Asia/Tokyo")))
    except Exception:
        return datetime.now()

def _day_key_for_cutoff(dt: datetime | None = None):
    dt = dt or _now_local()
    cutoff = getattr(Config, "DAILY_CONV_CUTOFF_HOUR", 1)
    if dt.hour < cutoff:
        return (dt - timedelta(days=1)).date()
    return dt.date()

@app.route("/webhooks/dify/summary_ingest", methods=["POST"])
def webhooks_dify_summary_ingest():
    """
    接收 Dify Workflow 的摘要结果，写入 daily_summaries 表。
    期望 Body（JSON）包含：
      user, conversation_id, day_key, scope, persona, message_count, summary_json(对象或字符串), [tail_preview], [turns_compact_count]
    """
    # 1) 鉴权
    if not _webhook_authorized():
        return jsonify({"error": "unauthorized"}), 401

    # 2) 解析 Body（兼容对象/字符串）
    body = request.get_json(silent=True) or {}
    user_ref = (body.get("user") or "").strip()
    conversation_id = (body.get("conversation_id") or "").strip()
    scope = (body.get("scope") or "guided").strip()
    persona = (body.get("persona") or "default").strip()
    day_key_raw = (body.get("day_key") or "").strip()
    message_count = int(body.get("message_count") or 0)

    # day_key 转日期
    try:
        day_key = datetime.fromisoformat(day_key_raw).date()
    except Exception:
        return jsonify({"error": "invalid day_key"}), 400

    # summary_json 可能是对象或字符串
    summary_json = body.get("summary_json")
    if isinstance(summary_json, str):
        try:
            summary_json = json.loads(summary_json)
        except Exception:
            summary_json = None

    if not isinstance(summary_json, dict):
        # 最小兜底，确保有结构
        summary_json = {
            "summary": (body.get("summary") or "今天没有对话内容"),
            "topics": [],
            "mood": "neutral",
            "next_openers": []
        }

    # 生成一份 summary_text（可选，便于检索/预览）
    summary_text = (summary_json.get("summary") or "").strip()
    if len(summary_text) > 2000:
        summary_text = summary_text[:2000]

    # 3) 入库（UPSERT）
    # 约定：daily_summaries 上有唯一键 (user_ref, scope, ai_personality, day_key)
    sql = """
        INSERT INTO daily_summaries
          (user_ref, scope, ai_personality, day_key, conversation_id, message_count, summary_json, summary_text, updated_at)
        VALUES
          (%s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (user_ref, scope, ai_personality, day_key) DO UPDATE SET
          conversation_id = EXCLUDED.conversation_id,
          message_count   = EXCLUDED.message_count,
          summary_json    = EXCLUDED.summary_json,
          summary_text    = EXCLUDED.summary_text,
          updated_at      = now()
        RETURNING id
    """
    params = [
        user_ref, scope, persona, day_key, conversation_id,
        message_count, Json(summary_json), summary_text
    ]

    try:
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                conn.commit()
        return jsonify({"ok": True, "id": (row["id"] if isinstance(row, dict) else (row[0] if row else None))})
    except Exception as e:
        # 统一打印/返回，方便排错
        try:
            err = str(e)
        except Exception:
            err = "db error"
        return jsonify({"ok": False, "error": err}), 500


@app.route("/tasks/dispatch_daily_summaries", methods=["GET", "POST"])
def tasks_dispatch_daily_summaries():
    """
    调度接口：枚举当日（或指定 day_key）的 dify_conversations，
    为每条 (user_ref, conversation_id) 触发“会话摘要 Workflow”。
    Workflow 内部自行拉取 /v1/messages 并总结，再 POST 回 /webhooks/dify/summary_ingest。
    """
    # 1) 鉴权：支持 Vercel Cron 或 token 兜底
    if not _cron_authorized():
        return jsonify({"error": "unauthorized"}), 401

    # 2) 读取参数（GET/POST 通用）
    scope_filter, only_missing, limit, after_id, day_key_override = _read_params()
    debug = request.args.get("debug", "0") in ("1", "true", "True")
    dry_run = request.args.get("dry_run", "0") in ("1", "true", "True")

    # 3) day_key：允许外部传入；否则按本地切日计算（01:00）
    if day_key_override:
        try:
            day_key = datetime.fromisoformat(day_key_override).date()
        except Exception:
            return jsonify({"error": "invalid day_key, expect YYYY-MM-DD"}), 400
    else:
        day_key = _day_key_for_cutoff()

    # 4) 组装 SQL：支持 only_missing、scope 过滤、after_id 分页
    left_join = ""
    and_scope = ""
    and_missing = ""
    and_after = ""

    params = [day_key]

    if scope_filter and scope_filter != "all":
        and_scope = "AND c.scope = %s"
        params.append(scope_filter)

    if only_missing:
        left_join = """
            LEFT JOIN daily_summaries s
              ON s.user_ref=c.user_ref
             AND s.scope=c.scope
             AND s.ai_personality=c.ai_personality
             AND s.day_key=c.day_key
        """
        and_missing = "AND s.id IS NULL"

    if after_id:
        and_after = "AND c.id > %s"
        params.append(int(after_id))

    params.append(int(limit))

    sql = f"""
        SELECT c.id, c.user_ref, c.scope, c.ai_personality, c.conversation_id
          FROM dify_conversations c
          {left_join}
         WHERE c.day_key = %s
           {and_scope}
           {and_missing}
           {and_after}
         ORDER BY c.id ASC
         LIMIT %s
    """

    # 5) 查询
    with DatabaseManager.get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() or []

    if not rows:
        return jsonify({
            "day_key": str(day_key),
            "total": 0,
            "dispatched": 0,
            "next_after_id": None,
            "items": [],
            "filters": {
                "scope": scope_filter or "ALL",
                "only_missing": bool(only_missing),
                "after_id": after_id,
                "limit": limit
            }
        })

    # dry_run：只回显将要触发的条目，不实际触发
    if dry_run:
        items = []
        for r in rows:
            row_id   = r["id"] if isinstance(r, dict) else r[0]
            user_ref = r["user_ref"] if isinstance(r, dict) else r[1]
            scope    = r["scope"] if isinstance(r, dict) else r[2]
            persona  = r["ai_personality"] if isinstance(r, dict) else r[3]
            cid      = r["conversation_id"] if isinstance(r, dict) else r[4]
            items.append({
                "id": row_id, "user_ref": user_ref, "scope": scope, "persona": persona, "conversation_id": cid
            })
        return jsonify({
            "day_key": str(day_key),
            "total": len(rows),
            "dispatched": 0,
            "next_after_id": (rows[-1]["id"] if isinstance(rows[0], dict) else rows[-1][0]),
            "items": items,
            "dry_run": True
        })

    # 6) 逐条触发 Workflow（轻量：只传 user/conv/day/scope/persona）
    total = len(rows)
    dispatched = 0
    items = []
    last_id = None

    for r in rows:
        row_id   = r["id"] if isinstance(r, dict) else r[0]
        user_ref = r["user_ref"] if isinstance(r, dict) else r[1]
        scope    = r["scope"] if isinstance(r, dict) else r[2]
        persona  = r["ai_personality"] if isinstance(r, dict) else r[3]
        cid      = r["conversation_id"] if isinstance(r, dict) else r[4]

        ok, info = _run_summary_workflow(
            user_ref=user_ref,
            conversation_id=cid,
            day_key=str(day_key),
            scope=scope,
            persona=persona,
            extra_inputs=None,
            timeout=12  # 短超时即可；真正工作在 Workflow 内完成并回调
        )
        dispatched += 1 if ok else 0
        last_id = row_id
        item = {"id": row_id, "user_ref": user_ref, "scope": scope, "persona": persona, "ok": ok}
        if debug:
            # 回显 Dify 的响应，便于定位 401/403/404 或 Body 错误
            item["resp"] = info
        items.append(item)

    # 7) 返回 next_after_id，便于多次触发分页跑完（如果需要）
    return jsonify({
        "day_key": str(day_key),
        "total": total,
        "dispatched": dispatched,
        "next_after_id": last_id,
        "items": items,
        "debug": bool(debug)
    })



# ====== 日切工具 & DB 读写（仅本文件使用） ======
from datetime import timedelta
from flask import request, jsonify, session, g
from database import DatabaseManager, SpreadDAO  # 已有
from services import DateTimeService, DifyService, SpreadService, ChatService, PersonaService


def _day_key_date(cutoff_hour: int = 1):
    """
    返回“会话日”的 date（01:00 为日界线）：
    - 00:00 ~ 00:59 视为前一天
    - 01:00 及之后视为当天
    """
    now = DateTimeService.get_beijing_datetime()
    if now.hour < cutoff_hour:
        return (now - timedelta(days=1)).date()
    return now.date()

def _dc_select(user_ref: str, scope: str, ai_personality: str, day_key_date):
    """查当日 conversation_id（表：dify_conversations）"""
    try:
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT conversation_id
                    FROM dify_conversations
                    WHERE user_ref=%s AND scope=%s AND ai_personality=%s AND day_key=%s
                    LIMIT 1
                """, (user_ref, scope, ai_personality, day_key_date))
                row = cur.fetchone()
                if not row:
                    return None
                # 兼容 RealDictCursor / tuple
                return row.get("conversation_id") if isinstance(row, dict) else row[0]
    except Exception as e:
        print("[daily-cid] select error:", e)
        return None

def _dc_upsert(user_ref: str, scope: str, ai_personality: str, day_key_date, conversation_id: str):
    """写/改当日 conversation_id（有则覆盖，无则插入）"""
    try:
        with DatabaseManager.get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO dify_conversations(user_ref, scope, ai_personality, day_key, conversation_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_ref, scope, ai_personality, day_key)
                    DO UPDATE SET conversation_id = EXCLUDED.conversation_id
                """, (user_ref, scope, ai_personality, day_key_date, conversation_id))
                conn.commit()
    except Exception as e:
        print("[daily-cid] upsert error:", e)

# ========== 引导聊天（guided）：每日固定会话 ==========
@app.route("/api/guided/chat/send_daily", methods=["POST"])
def api_guided_chat_send_daily():
    """
    与 /api/guided/chat/send 等价，但 conversation_id 按 用户×人格×scope=guided×(01:00切日) 固定
    """
    user = g.get("user") or {}
    data = request.json or {}
    message = (data.get('message') or '').strip()
    ai_personality = _resolve_ai_personality(data)

    if not message or len(message) > Config.CHAT_FEATURES['max_message_length']:
        return jsonify({'error': '消息长度不合法'}), 400

    # 频控（沿用原逻辑）
    can_chat, remaining = SpreadService.can_chat_today(
        user.get('id'), session.get('session_id'), user.get('is_guest', True)
    )
    if not can_chat:
        limit_msg = random.choice(ChatService.LIMIT_MESSAGES)
        return jsonify({'reply': limit_msg, 'limit_reached': True, 'remaining': 0})

    user_ref = get_user_ref()
    scope = "guided"
    day_key = _day_key_date(1)

    # 1) 取当日CID；若无则不传 cid 让 Dify 新建
    cid = _dc_select(user_ref, scope, ai_personality, day_key)

    resp = DifyService.guided_chat(
        user_message=message,
        user_ref=user_ref,
        conversation_id=cid,             # 可能是 None → 让 Dify 新建
        ai_personality=ai_personality,
        phase='guide',
        spread_id=data.get('spread_id'),
        reading_id=data.get('reading_id'),
        question=data.get('question'),
        candidate_set_id=data.get('candidate_set_id'),
    )

    new_cid = resp.get("conversation_id") or cid
    if new_cid:
        _dc_upsert(user_ref, scope, ai_personality, day_key, new_cid)
        session['guided_cid'] = new_cid  # 兼容旧逻辑
        session.modified = True

    return jsonify({
        'reply': resp.get('answer', ''),
        'conversation_id': new_cid,
        'remaining': max(remaining - 1, 0)
    })

# ========== 牌阵聊天（spread）：每日固定会话 ==========
@app.route("/api/spread/chat/send_daily", methods=["POST"])
def api_spread_chat_send_daily():
    """
    与 /api/spread/chat/send 等价，但 conversation_id 按 用户×人格×scope=spread×(01:00切日) 固定；
    同时把当日CID写回该 reading，保证 SpreadService.process_chat_message 继续沿用。
    """
    user = g.get("user") or {}
    data = request.json or {}
    reading_id = data.get('reading_id')
    message = (data.get('message') or '').strip()
    if not reading_id:
        return jsonify({'error': 'missing reading_id'}), 400
    if not message:
        return jsonify({'error': '消息为空'}), 400

    # 鉴权
    reading = SpreadDAO.get_by_id(reading_id)
    if not reading:
        return jsonify({'error': '占卜记录不存在'}), 404
    if reading['user_id'] != user.get('id') and reading['session_id'] != session.get('session_id'):
        return jsonify({'error': '无权访问'}), 403

    # 频控
    can_chat, remaining = SpreadService.can_chat_today(
        user.get('id'), session.get('session_id'), user.get('is_guest', True)
    )
    if not can_chat:
        limit_msg = random.choice(ChatService.LIMIT_MESSAGES)
        return jsonify({'reply': limit_msg, 'limit_reached': True, 'remaining': 0})

    user_ref = get_user_ref()
    ai_personality = (reading.get('ai_personality') or _resolve_ai_personality(data) or 'warm')
    scope = "spread"
    day_key = _day_key_date(1)

    # 1) 取当日CID；如命中且与 reading 不同，则同步回 reading
    cid = _dc_select(user_ref, scope, ai_personality, day_key)
    if cid and cid != reading.get('conversation_id'):
        try:
            SpreadDAO.update_conversation_id(reading_id, cid)
        except Exception as e:
            print("[daily-cid] update reading conversation_id error:", e)

    # 2) 走你现有服务：它会根据 reading.conversation_id 续聊，并在变化时更新 reading
    resp = SpreadService.process_chat_message(
        reading_id=reading_id,
        user_message=message,
        user_ref=user_ref
    )

    new_cid = resp.get("conversation_id") or cid
    if new_cid and new_cid != cid:
        _dc_upsert(user_ref, scope, ai_personality, day_key, new_cid)
        try:
            SpreadDAO.update_conversation_id(reading_id, new_cid)
        except Exception as e:
            print("[daily-cid] update reading conversation_id error:", e)

    return jsonify({
        'reply': resp.get('answer', ''),
        'conversation_id': new_cid,
        'remaining': max(remaining - 1, 0)
    })

# =========================
# 路由：分享卡片生成页面（本人查看/生成）
# =========================
@app.route("/share/card")
@login_required  # 若允许游客也进来，可去掉该装饰器
def share_card():
    """分享卡片生成页面"""
    user = g.user
    today = DateTimeService.get_beijing_date()

    # 读取今日抽牌与运势数据（登录用户 vs 访客）
    if not user.get("is_guest", True):
        reading = TarotService.get_today_reading(user["id"], today)
        fortune_data = FortuneService.get_fortune(user["id"], today)
    else:
        reading = SessionService.get_guest_reading(session, today)
        # 你之前保存到 session 的结构：session['fortune_data']['data']
        fortune_data = (session.get('fortune_data') or {}).get('data') or {}

    if not reading:
        flash("请先抽取今日塔罗牌", "info")
        return redirect(url_for("index"))

    return render_template(
        "share_card.html",
        user=user,
        reading=reading,
        fortune_data=fortune_data,
        today=today.strftime("%Y.%m.%d")
    )


# --- 修改 view_share，使其在 card/embed/export 场景渲染 share_card.html ---
@app.route("/s/<share_id>")
def view_share(share_id):
    share_data = ShareService.get_share_data(share_id)
    if not share_data:
        flash("分享链接已失效", "info")
        return redirect(url_for("index"))

    # 计数
    ShareService.increment_view_count(share_id)

    use_card = request.args.get("card") == "1" or request.args.get("embed") == "1" or request.args.get("export") == "1"
    if use_card:
        # 统一走 share_card.html，传入 share_data，并注入 embed/export 标志
        return render_template(
            "share_card.html",
            share_data=share_data,
            is_viewer=True,
            embed=(request.args.get("embed") == "1"),
            export_mode=(request.args.get("export") == "1"),
        )
    else:
        # 保留原有的查看页
        return render_template("share_view.html", share_data=share_data, is_viewer=True)

# --- 新增：后端导出接口 ---
@app.route("/api/share/export", methods=["POST"])
def api_share_export():
    """
    入参：
      - JSON: { "share_id": "xxxx" }
        或 { "payload": { user_name, reading, fortune, created_at } }
    返回：image/png（二进制）
    """
    try:
        base = request.host_url.rstrip("/")
        data = request.get_json(silent=True) or {}

        # 优先 share_id
        share_id = data.get("share_id")
        if share_id:
            # 用短链渲染 share_card.html（card=1 + export=1）
            url = f"{base}/s/{share_id}?card=1&export=1"
        else:
            # 无 share_id，用 payload 临时渲染（需要你在 share_card.html 能读到 window.name 或 query 注入）
            # 简单做法：把 payload 用 query 传；若过长可改 POST 到一个临时路由
            payload = data.get("payload") or {}
            q = urlencode({"payload": json.dumps(payload, ensure_ascii=False)}, safe=":/?&=")
            url = f"{base}/share/card?embed=1&export=1&{q}"

        png = screenshot_share_card(url)
        return send_file(io.BytesIO(png), mimetype="image/png",
                         as_attachment=True, download_name=f"ruoshui_tarot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    except Exception as e:
        # 可补充 logging
        return jsonify({"success": False, "error": str(e)}), 500


# =========================
# API：创建分享
# =========================
@app.route("/api/share/create", methods=["POST"])
def api_create_share():
    """创建分享链接API"""
    user = g.get("user")  # 允许未登录也可分享时，这里可能为 None
    today = DateTimeService.get_beijing_date()

    # ---- 补齐 reading / fortune_data（与 /share/card 保持一致）----
    if user and not user.get("is_guest", True):
        reading = TarotService.get_today_reading(user["id"], today)
        fortune_data = FortuneService.get_fortune(user["id"], today)
        user_id = user.get("id")
        user_name = user.get("username", "神秘访客")
    else:
        reading = SessionService.get_guest_reading(session, today)
        fortune_data = (session.get('fortune_data') or {}).get('data') or {}
        user_id = None  # 访客不落库用户ID
        user_name = (session.get("guest_name")
                     or (user and user.get("username"))
                     or "神秘访客")

    if not reading:
        return jsonify({"success": False, "error": "尚未抽取今日卡片"}), 400

    # ---- 生成短链ID（低碰撞 + 可复现性）----
    salt = os.urandom(4).hex()
    raw = f"{user_id or 'guest'}_{today.isoformat()}_{datetime.utcnow().isoformat()}_{salt}"
    share_id = hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]

    # ---- 生成短链 URL（按你的域名来）----
    # 若生产环境可用 request.url_root 自动推导域名，也可固定为 ruoshui.fun：
    # base_url = request.url_root.rstrip('/')  # 如 https://www.ruoshui.fun
    base_url = "https://www.ruoshui.fun"  # 你给的域名
    share_url = f"{base_url}/s/{share_id}"

    # ---- 生成二维码（Base64 DataURL；若失败返回 None）----
    qr_code_dataurl = generate_qr_code(share_url)

    # ---- 入库分享数据 ----
    payload = {
        "user_id": user_id,
        "user_name": user_name or "神秘访客",
        "reading": reading,
        "fortune": fortune_data,
        "created_at": datetime.utcnow(),
        "expires_at": datetime.utcnow() + timedelta(days=30),
    }
    ShareService.save_share_data(share_id, payload)

    return jsonify({
        "success": True,
        "share_id": share_id,
        "share_url": share_url,
        "qr_code": qr_code_dataurl  # 前端可 <img src="{{ qr_code }}">
    })
                         
@app.route("/api/guided/get_reading", methods=["POST"])
def api_guided_get_reading():
    """
    输入(JSON):
      - reading_id: str   必填
      - include_messages: bool 可选
      - mask_until: int   可选（非内部调用时可用来遮罩未揭示卡）
    权限：
      - 同一登录用户 或 同一会话(session) 或 携带有效 X-Internal-Token
    返回:
      success, reading_id, question, ai_personality,
      spread: {id, name, description, card_count, positions: [...]},
      cards:  [{ index, position_name, position_meaning, card_id, card_name, direction, image, masked? }, ...],
      cards_layout: "1. ...\n2. ...",
      messages?: [...]
    """
    # --- 统一日志：看 content-type 和原始前200字 ---
    app.logger.info(
        "get_reading HIT ct=%s raw[:200]=%r",
        request.headers.get("Content-Type"),
        (request.data or b"")[:200],
    )

    # --- 先给默认值，避免 NameError ---
    include_messages = False
    mask_until = None
    reading_id = ""

    try:
        # 解析 JSON（容错：失败则给空 dict）
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            data = {}

        # 读取字段（允许前端传 false / 0 / "false" 等）
        reading_id = (data.get("reading_id") or "").strip()

        # include_messages 统一为 bool
        im = data.get("include_messages", False)
        # 接受多种形式：True/False, "true"/"false", 1/0
        if isinstance(im, str):
            include_messages = im.strip().lower() in ("1", "true", "t", "yes", "y")
        else:
            include_messages = bool(im)

        # 遮罩参数
        mask_until = data.get("mask_until", None)
        try:
            if mask_until is not None:
                mask_until = int(mask_until)
        except Exception:
            mask_until = None

        # 容错：若未取到 reading_id，尝试 raw 再 parse 一次
        if not reading_id and request.data:
            try:
                import json as _json
                raw_obj = _json.loads(request.data.decode("utf-8", "ignore"))
                if isinstance(raw_obj, dict):
                    reading_id = (raw_obj.get("reading_id") or "").strip()
                    if "include_messages" in raw_obj:
                        im2 = raw_obj.get("include_messages")
                        if isinstance(im2, str):
                            include_messages = im2.strip().lower() in ("1", "true", "t", "yes", "y")
                        else:
                            include_messages = bool(im2)
            except Exception:
                pass

        if not reading_id:
            app.logger.warning(
                "get_reading 400 missing_reading_id; json=%r form=%r args=%r",
                data, dict(request.form), dict(request.args)
            )
            return jsonify({"success": False, "error": "missing_reading_id"}), 400

        # --- 鉴权：同用户 / 同会话 / 内部令牌 ---
        from services import SpreadService
        from database import SpreadDAO
        from flask import session as flask_session

        def _is_internal_call(req):
            from config import Config
            token = (req.headers.get("X-Internal-Token") or "").strip()
            return bool(token and token in Config.INTERNAL_TOKENS)

        trusted = _is_internal_call(request)
        user = getattr(g, "user", None) or {}
        sess_id = flask_session.get("session_id")

        reading = SpreadService.get_reading(reading_id)
        if not reading:
            return jsonify({"success": False, "error": "not_found"}), 404

        same_user = (reading.get("user_id") and user.get("id") == reading.get("user_id"))
        same_session = (reading.get("session_id") and sess_id == reading.get("session_id"))
        if not (same_user or same_session or trusted):
            return jsonify({"success": False, "error": "forbidden"}), 403

        # --- 取 spread/positions ---
        spread = SpreadDAO.get_spread_by_id(reading["spread_id"]) or {}
        positions = spread.get("positions") or []
        # 兼容字符串/对象
        if isinstance(positions, str):
            try:
                import json as _json
                positions = _json.loads(positions) or []
            except Exception:
                positions = []
        elif isinstance(positions, dict):
            try:
                positions = [positions[str(i)] for i in sorted(map(int, positions.keys()))]
            except Exception:
                positions = []

        # --- 归一化 cards 并拼位置信息 ---
        cards_raw = reading.get("cards") or []
        if isinstance(cards_raw, str):
            try:
                import json as _json
                cards_raw = _json.loads(cards_raw) or []
            except Exception:
                cards_raw = []

        cards = []
        for i, c in enumerate(cards_raw):
            pos = positions[i] if i < len(positions) else {}
            item = {
                "index": i,
                "position_name": pos.get("name", f"位置{i+1}"),
                "position_meaning": pos.get("meaning", ""),
                "card_id": c.get("card_id"),
                "card_name": c.get("card_name", ""),
                "direction": c.get("direction", ""),
                "image": c.get("image", "")
            }
            cards.append(item)

        # --- 非内部调用可按 mask_until 遮住尚未揭示的卡 ---
        if not trusted and isinstance(mask_until, int):
            for it in cards:
                if it["index"] >= mask_until:
                    it.update({
                        "card_name": "",
                        "direction": "",
                        "image": "",
                        "masked": True
                    })

        # --- cards_layout 文本 ---
        lines = []
        for i, c in enumerate(cards, 1):
            pos = c["position_name"]
            mean = c["position_meaning"]
            cn = c["card_name"] or "（未揭示）"
            dr = c["direction"] or ""
            lines.append(f"{i}. {pos}（{mean}）\n   {cn}{f'（{dr}）' if dr else ''}")
        cards_layout = "\n".join(lines)

        resp = {
            "success": True,
            "reading_id": reading_id,
            "question": reading.get("question", ""),
            "ai_personality": reading.get("ai_personality", ""),
            "spread": {
                "id": spread.get("id") or reading.get("spread_id"),
                "name": spread.get("name", ""),
                "description": spread.get("description", ""),
                "card_count": int(spread.get("card_count") or len(cards)),
                "positions": positions
            },
            "cards": cards,
            "cards_layout": cards_layout
        }

        if include_messages:
            msgs = SpreadService.get_chat_messages(reading_id)
            resp["messages"] = msgs

        return jsonify(resp)

    except Exception as e:
        # 这里不要引用 include_messages / mask_until 等局部变量，避免二次 NameError
        app.logger.exception("[get_reading] error: %s", e)
        return jsonify({"success": False, "error": "server_error"}), 500

        
# ========= spreads: 根据 LLM 推断解析数据库候选 =========
@app.route("/api/spreads/resolve_from_llm", methods=["POST"])
def api_spreads_resolve_from_llm():
    """
    输入：
      - normalized: {topic, depth, difficulty}
      - recommended: LLM 推断出的候选数组（名字/别名/标签/张数范围/理由/置信度）
      - question: 原始问题（可选）
    输出：
      - candidate_set_id: 本次候选签名（HMAC）
      - items: [{spread_id, spread_name, card_count, tags, why, score}, ...]（按 score 降序）
    """
    try:
        data = request.json or {}
        normalized = data.get('normalized') or {}
        recommended = data.get('recommended') or []
        question = (data.get('question') or '').strip()

        # 兼容前端把 recommended 作为字符串传来的情况
        if isinstance(recommended, str):
            try:
                import json as _json
                recommended = _json.loads(recommended)
            except Exception:
                recommended = []

        from services import SpreadService
        user_ref = get_user_ref()
        result = SpreadService.resolve_spreads_from_llm(
            user_ref=user_ref,
            normalized=normalized,
            recommended=recommended,
            question=question,
            topn=3  # 返回前3个候选
        )
        return jsonify({'success': True, **result})
    except Exception as e:
        print(f"[resolve_from_llm] error: {e}")
        return jsonify({'success': False, 'error': '解析候选失败'}), 500


@app.route("/api/spreads/suggest", methods=["POST"])
def api_spreads_suggest():
    user_ref = get_user_ref()
    data = request.json or {}
    topic = data.get('topic') or '通用'
    depth = data.get('depth') or 'short'
    difficulty = data.get('difficulty') or '简单'
    question = (data.get('question') or '').strip()

    items = SpreadService.suggest_spreads(
        user_ref=user_ref,
        topic=topic, depth=depth, difficulty=difficulty,
        question=question,
        avoid_recent_user_id=g.user.get('id'),
        topn=3
    )
    return jsonify({'success': True, **items})


@app.route("/spread/chat2")
def spread_chat2():
    """
    引导牌阵占卜：先进入聊天页，由 Dify 引导收集诉求、推荐牌阵和问题，
    确认后再创建 reading 并逐张翻牌。
    """
    user = g.user or {}
    can_chat, remaining = SpreadService.can_chat_today(
        user.get('id'),
        session.get('session_id'),
        user.get('is_guest', True)
    )
    # 可把 URL 参数透传给模板，便于调试（模板里也用到了）
    return render_template(
        "spread_chat2.html",
        user=user,
        can_chat=can_chat,
        remaining_chats=remaining,
        persona_id=request.args.get("persona_id", ""),
        spread_id=request.args.get("spread_id", ""),
        question=request.args.get("question", ""),
        debug=request.args.get("debug", ""),
        itoken=request.args.get("itoken", ""),
    )

# app.py
@app.route("/api/guided/chat/send", methods=["POST"])
def api_guided_chat_send():
    """
    引导阶段与 Dify 对话（未绑定 reading）：
    - 前端传 ai_personality（人格）、message、可选 conversation_id
    - 返回 answer 与新的 conversation_id
    """
    user = g.user or {}
    data = request.json or {}
    message = (data.get('message') or '').strip()
    ai_personality = _resolve_ai_personality(data)

    # ✅ 关键：优先用前端传的，其次用后端 session 缓存的
    conversation_id = data.get('conversation_id') or session.get('guided_cid')

    if not message or len(message) > Config.CHAT_FEATURES['max_message_length']:
        return jsonify({'error': '消息长度不合法'}), 400

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
        conversation_id=conversation_id,   # ✅ 带上（可能为 None）
        ai_personality=ai_personality,
        phase='guide',
        # 这里也可以把 spread_id / reading_id / question / candidate_set_id 透传
        spread_id=data.get('spread_id'),
        reading_id=data.get('reading_id'),
        question=data.get('question'),
        candidate_set_id=data.get('candidate_set_id'),
    )

    # ✅ 拿到新的会话 ID，持久化到后端 session
    new_cid = resp.get('conversation_id') or conversation_id
    if new_cid:
        session['guided_cid'] = new_cid
        session.modified = True

    return jsonify({
        'reply': resp.get('answer', ''),
        'conversation_id': new_cid,
        'remaining': max(remaining - 1, 0)
    })



# app.py — 新增：引导落地创建 reading（带候选集强校验）
@app.route("/api/guided/create_reading", methods=["POST"])
def api_guided_create_reading():
    """
    在引导阶段确定了 spread_id + question + ai_personality 后调用：
    - 可选接收 candidate_set_id，用于强校验“spread_id 属于最近一次候选集合”
    - 抽牌并入库（status=init），不触发 LLM
    - 返回 reading_id、positions（前端占位）与 card_count
    """
    rid = getattr(g, "rid", _rid())
    user = g.user or {}
    data = request.json or {}
    spread_id = (data.get('spread_id') or '').strip()
    question = (data.get('question') or '').strip()
    ai_personality = _resolve_ai_personality(data)
    candidate_set_id = (data.get('candidate_set_id') or '').strip()

    if not spread_id:
        return jsonify({'error': '缺少牌阵 ID'}), 400
    if question and len(question) > 400:
        return jsonify({'error': '问题请限制在200字以内'}), 400

    # 1) 每日次数校验（与 /api/spread/draw 一致）
    can_divine, _ = SpreadService.can_divine_today(
        user.get('id'), session.get('session_id'), user.get('is_guest', True)
    )
    if not can_divine:
        return jsonify({'error': '今日占卜次数已用完'}), 429

    # 2) 基础: 牌阵必须真实存在于数据库
    spread = SpreadDAO.get_spread_by_id(spread_id)
    if not spread:
        return jsonify({'error': '所选牌阵不存在或已下线'}), 404

    # 3) （可选）候选集强校验：如果提供了 candidate_set_id，就必须验证通过
    user_ref = get_user_ref()
    if candidate_set_id:
        ok, reason = SpreadService.verify_candidate_membership(
            candidate_set_id=candidate_set_id,
            spread_id=spread_id,
            user_ref=user_ref
        )
        if not ok:
            # 422：语义正确但不被允许（不在候选集 / 过期 / 用户不匹配）
            return jsonify({
                'error': '所选牌阵不在最近的候选集合内或候选已过期，请重新选择',
                'reason': reason
            }), 422

    try:
        # 4) 入库创建（仅抽牌+保存，不触发 LLM）
        reading = SpreadService.create_guided_reading(
            user_ref=user_ref,
            session_id=session.get('session_id'),
            spread_id=spread_id,
            question=question,
            ai_personality=ai_personality
        )

        positions = (spread or {}).get('positions') or []
        card_count = int(spread.get('card_count', 0)) if spread else 0

        return jsonify({
            'success': True,
            'reading_id': reading['id'],
            'positions': positions,
            'card_count': card_count
        })
    except ValueError as ve:
        # 业务显式抛错（例如库存、计费等）
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        # 记日志后返回 500
        print(f"[guided] create_reading error rid={rid}: {e}")
        return jsonify({'error': '创建占卜失败，请稍后重试'}), 500


_INTERNAL_TOKENS = set(
    t.strip() for t in (os.getenv("INTERNAL_TOKENS") or "").split(",") if t.strip()
)

def _is_internal_call(req: request) -> bool:
    """识别来自 Dify/后端的可信调用"""
    token = req.headers.get("X-Internal-Token", "")
    return bool(token) and (token in _INTERNAL_TOKENS)

def _json_error(status: int, error: str, message: str, **details):
    """统一错误体"""
    payload = {"success": False, "error": error, "message": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status

def _json_ok(**data):
    """统一成功体"""
    payload = {"success": True}
    payload.update(data)
    return jsonify(payload), 200

# ===== 路由：逐张揭示卡牌 =====
@app.route("/api/guided/reveal_card", methods=["POST"])
def api_guided_reveal_card():
    """
    参数(JSON)：reading_id: str, index: int
    行为：
      - 从既有 reading 中揭示第 index 张卡（支持 0/1 基索引输入）
      - 返回卡名/方位/图片/位置等信息
      - 可记录 system 日志（可选）
    权限：
      - 同一用户 或 同一 session 或 携带有效 X-Internal-Token

    返回(JSON)：
      - success: true/false
      - reading_id, index(0-based), index1(1-based)
      - card: {...}
      - 错误时：code/message/可选扩展字段
    """
    data = request.get_json(silent=True) or {}
    reading_id = (data.get("reading_id") or "").strip()
    index_raw = data.get("index")

    # 入口日志（不打印敏感信息）
    app.logger.info("reveal_card HIT json=%s headers[X-Internal-Token]=%s",
                    {"reading_id": reading_id, "index": index_raw},
                    bool(request.headers.get("X-Internal-Token")))

    # 参数校验
    if not reading_id or index_raw is None:
        return _json_error(400, "missing_params", "reading_id 和 index 为必填")

    # index 先转成 int（此处仅校验是整数，基准归一化放到读取 reading 后）
    try:
        idx_in = int(index_raw)
    except (TypeError, ValueError):
        return _json_error(400, "bad_index", "index 必须是整数", got=index_raw)

    # 内部信任头
    trusted = _is_internal_call(request)

    # 会话身份
    user = getattr(g, "user", None) or {}
    sess_id = session.get("session_id")

    # 读取 reading
    try:
        reading = SpreadService.get_reading(reading_id)
    except Exception as e:
        app.logger.exception("reveal_card get_reading failed: %s", e)
        return _json_error(500, "server_error", "读取占卜记录失败")

    if not reading:
        return _json_error(404, "not_found", "占卜记录不存在", reading_id=reading_id)

    # 权限校验：同一用户 / 同一 session / 内部可信调用
    same_user = (reading.get("user_id") and user.get("id") == reading.get("user_id"))
    same_session = (reading.get("session_id") and sess_id == reading.get("session_id"))
    if not (same_user or same_session or trusted):
        app.logger.warning(
            "reveal_card FORBIDDEN reading_uid=%s reading_sid=%s req_uid=%s req_sid=%s trusted=%s",
            reading.get("user_id"), reading.get("session_id"), user.get("id"), sess_id, trusted
        )
        return _json_error(403, "forbidden", "无权访问此占卜记录")

    # ====== 归一化 index：同时支持 0/1 基输入 ======
    # 多源推断 card_count（按你项目的真实结构调整优先级）
    def _int_or_0(v):
        try:
            return int(v or 0)
        except Exception:
            return 0

    card_count = 0
    # 1) reading.card_count
    card_count = _int_or_0(reading.get("card_count"))
    # 2) reading.spread.card_count
    if not card_count and isinstance(reading.get("spread"), dict):
        card_count = _int_or_0(reading["spread"].get("card_count"))
    # 3) reading.positions（如果存了位置数组）
    if not card_count and isinstance(reading.get("positions"), list):
        card_count = len(reading["positions"])
    # 4) reading.cards（仅当它代表牌阵位数）
    if not card_count and isinstance(reading.get("cards"), list):
        card_count = len(reading["cards"])

    # 根据 card_count 认定 0/1 基
    if card_count > 0 and 0 <= idx_in < card_count:
        idx0 = idx_in                      # 0-based
    elif card_count > 0 and 1 <= idx_in <= card_count:
        idx0 = idx_in - 1                  # 1-based -> 0-based
    else:
        # 无法判定或越界
        rng0 = f"[0,{max(0, card_count-1)}]" if card_count else "[0..N-1]"
        rng1 = f"[1,{max(1, card_count)}]" if card_count else "[1..N]"
        return _json_error(400, "out_of_range",
                           f"index={idx_in} 不在允许范围 {rng0} 或 {rng1}",
                           index_in=idx_in, card_count=card_count)

    app.logger.info("reveal_card AUTH same_user=%s same_session=%s trusted=%s idx_in=%s -> idx0=%s cc=%s",
                    same_user, same_session, trusted, idx_in, idx0, card_count)

    # 业务执行
    try:
        card = SpreadService.reveal_card(reading_id, idx0)
        # 可选：记录系统日志
        # SpreadService.log_system(reading_id, f"reveal_card index0={idx0}")

        # 同时返回 0/1 基索引，方便前端/ChatFlow 显示“第几张”
        return _json_ok(reading_id=reading_id, index=idx0, index1=(idx0 + 1), card=card)

    except IndexError:
        # 后端实现可能将“已揭示/越界”都抛 IndexError；这里统一视为 out_of_range
        return _json_error(400, "out_of_range", "索引越界或当前索引不可揭示", index0=idx0, index_in=idx_in)
    except Exception as e:
        app.logger.exception("reveal_card error: %s", e)
        return _json_error(500, "server_error", "揭示失败，请稍后重试")


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
        
        # 生成运势文案之后：
        fortune_text = FortuneService.generate_fortune_text(fortune_data)
        if isinstance(fortune_text, dict):
            # 挂在 fortune_text，同时把常用字段扁平到根上方便前端读取
            fortune_data["fortune_text"] = fortune_text
            for k in ("summary", "dimension_advice", "do", "dont",
                      "lucky_color", "lucky_number", "lucky_hour", "lucky_direction"):
                if k in fortune_text and fortune_text[k]:
                    fortune_data[k] = fortune_text[k]

        # ★ 在保存与返回前拍平结构
        fortune_data = flatten_fortune_for_share(fortune_data)

        # 再保存 / 缓存
        if not user["is_guest"]:
            FortuneService.save_fortune(user["id"], target_date, fortune_data)
        else:
            session['fortune_data'] = {'date': date, 'data': fortune_data}
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