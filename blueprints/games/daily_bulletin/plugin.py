# -*- coding: utf-8 -*-
"""
每日板报 Blueprint
基于用户位置显示：日期、天气、全球新闻
新增个性化功能：记事本、待办事项
"""
from flask import Blueprint, render_template, request, jsonify, make_response, session, g
import os
import json
import secrets
import requests
from datetime import datetime
from config import Config
from database import DailyBulletinNoteDAO, DailyBulletinTodoDAO

SLUG = "daily_bulletin"

def get_meta():
    return {
        "slug": SLUG,
        "title": "每日板报",
        "subtitle": "位置 · 天气 · 新闻 · 一目了然",
        "path": f"/g/{SLUG}/",
        "tags": ["Daily", "Weather", "News", "Location"]
    }

bp = Blueprint(
    SLUG,
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",
)

# ============ Cookie 辅助 ============
def _ensure_sid(resp):
    if request.cookies.get("sid"):
        return resp
    sid = secrets.token_hex(16)
    resp.set_cookie(
        "sid",
        sid,
        max_age=60 * 60 * 24 * 730,
        httponly=True,
        samesite="Lax",
        secure=False,
    )
    return resp

# ============ API 调用函数 ============

def get_location_from_ip(ip_address=None):
    """
    通过 IP 获取地理位置信息
    优先使用 ipapi.co，失败时使用 ip-api.com 作为备份
    """
    try:
        # 获取 IP 地址
        if not ip_address or ip_address == "127.0.0.1":
            print(f"[daily_bulletin] Local IP detected, fetching public IP...")
            try:
                ip_address = requests.get("https://api.ipify.org", timeout=5).text.strip()
                print(f"[daily_bulletin] Public IP: {ip_address}")
            except Exception as e:
                print(f"[daily_bulletin] Failed to get public IP: {e}")
                # 使用备用 IP 服务
                ip_address = requests.get("https://api.ip.sb/ip", timeout=5).text.strip()
                print(f"[daily_bulletin] Public IP (fallback): {ip_address}")

        # 方法1: 尝试 ipapi.co
        try:
            url = f"{Config.IPAPI_URL}/{ip_address}/json/"
            print(f"[daily_bulletin] Requesting location from ipapi.co: {url}")

            response = requests.get(url, timeout=10)
            print(f"[daily_bulletin] ipapi.co response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"[daily_bulletin] ipapi.co response: {data}")

                # 检查是否有错误信息（ipapi.co 在达到限制时返回 error: true）
                if not data.get("error"):
                    location = {
                        "city": data.get("city") or "Unknown",
                        "region": data.get("region") or "",
                        "country": data.get("country_name") or "World",
                        "lat": data.get("latitude"),
                        "lon": data.get("longitude"),
                        "timezone": data.get("timezone") or "UTC"
                    }
                    print(f"[daily_bulletin] Location from ipapi.co: {location}")
                    return location
                else:
                    print(f"[daily_bulletin] ipapi.co returned error: {data.get('reason')}")
        except Exception as e:
            print(f"[daily_bulletin] ipapi.co failed: {e}")

        # 方法2: 备用 - 使用 ip-api.com（无需 API key，免费）
        try:
            url = f"http://ip-api.com/json/{ip_address}?fields=status,message,country,countryCode,region,regionName,city,lat,lon,timezone"
            print(f"[daily_bulletin] Trying fallback: ip-api.com")

            response = requests.get(url, timeout=10)
            print(f"[daily_bulletin] ip-api.com response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"[daily_bulletin] ip-api.com response: {data}")

                if data.get("status") == "success":
                    location = {
                        "city": data.get("city") or "Unknown",
                        "region": data.get("regionName") or "",
                        "country": data.get("country") or "World",
                        "lat": data.get("lat"),
                        "lon": data.get("lon"),
                        "timezone": data.get("timezone") or "UTC"
                    }
                    print(f"[daily_bulletin] Location from ip-api.com: {location}")
                    return location
                else:
                    print(f"[daily_bulletin] ip-api.com error: {data.get('message')}")
        except Exception as e:
            print(f"[daily_bulletin] ip-api.com failed: {e}")

    except Exception as e:
        print(f"[daily_bulletin] Location error: {e}")
        import traceback
        traceback.print_exc()

    # 默认返回（所有方法都失败时）
    print("[daily_bulletin] All location APIs failed, using fallback")
    return {
        "city": "Unknown",
        "region": "",
        "country": "World",
        "lat": None,
        "lon": None,
        "timezone": "UTC"
    }

def get_weather(lat, lon):
    """
    获取天气信息
    使用 OpenWeatherMap API
    """
    print(f"[daily_bulletin] Getting weather for lat={lat}, lon={lon}")

    if not Config.OPENWEATHER_API_KEY:
        print("[daily_bulletin] Weather API Key not configured")
        return {
            "temp": "N/A",
            "description": "天气 API Key 未配置",
            "humidity": "N/A",
            "wind_speed": "N/A",
            "icon": "01d"
        }

    if not lat or not lon:
        print(f"[daily_bulletin] Invalid coordinates: lat={lat}, lon={lon}")
        return {
            "temp": "N/A",
            "description": "位置信息不可用（无法获取天气）",
            "humidity": "N/A",
            "wind_speed": "N/A",
            "icon": "01d"
        }

    try:
        url = Config.OPENWEATHER_API_URL
        params = {
            "lat": lat,
            "lon": lon,
            "appid": Config.OPENWEATHER_API_KEY,
            "units": "metric",  # 摄氏度
            "lang": "zh_cn"  # 中文描述
        }

        print(f"[daily_bulletin] Requesting weather from: {url}")
        response = requests.get(url, params=params, timeout=10)
        print(f"[daily_bulletin] Weather API response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"[daily_bulletin] Weather data: {data}")

            main = data.get("main", {})
            weather = data.get("weather", [{}])[0]
            wind = data.get("wind", {})

            weather_info = {
                "temp": f"{main.get('temp', 'N/A')}°C",
                "description": weather.get("description", "未知"),
                "humidity": f"{main.get('humidity', 'N/A')}%",
                "wind_speed": f"{wind.get('speed', 'N/A')} m/s",
                "icon": weather.get("icon", "01d")
            }
            print(f"[daily_bulletin] Parsed weather: {weather_info}")
            return weather_info
        else:
            print(f"[daily_bulletin] Weather API error: {response.status_code}")
            print(f"[daily_bulletin] Response: {response.text}")

    except Exception as e:
        print(f"[daily_bulletin] Weather exception: {e}")
        import traceback
        traceback.print_exc()

    return {
        "temp": "N/A",
        "description": "天气服务暂不可用",
        "humidity": "N/A",
        "wind_speed": "N/A",
        "icon": "01d"
    }

def get_news(country_code="us", language="zh"):
    """
    获取新闻头条
    使用 NewsAPI
    """
    if not Config.NEWS_API_KEY:
        return {
            "articles": [],
            "error": "新闻 API Key 未配置"
        }

    try:
        url = Config.NEWS_API_URL

        # NewsAPI 免费版不支持中国 (cn)，改用全球热门新闻
        if country_code.lower() == "cn":
            # 使用 everything 端点获取中文新闻
            url = Config.NEWS_API_URL.replace('top-headlines', 'everything')
            params = {
                "apiKey": Config.NEWS_API_KEY,
                "q": "中国 OR 科技 OR 财经",  # 搜索关键词
                "language": "zh",
                "sortBy": "publishedAt",
                "pageSize": 10,
            }
        else:
            params = {
                "apiKey": Config.NEWS_API_KEY,
                "country": country_code.lower() if len(country_code) == 2 else "us",
                "pageSize": 10,
            }

        response = requests.get(url, params=params, timeout=10)

        print(f"[daily_bulletin] News API response status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            # 检查 API 返回状态
            if data.get("status") != "ok":
                error_msg = data.get("message", "API 返回错误")
                print(f"[daily_bulletin] News API error: {error_msg}")
                return {
                    "articles": [],
                    "error": f"新闻服务错误: {error_msg}"
                }

            articles = data.get("articles", [])
            print(f"[daily_bulletin] Got {len(articles)} articles")

            # 格式化新闻
            formatted_articles = []
            for article in articles[:5]:  # 只取前5条
                formatted_articles.append({
                    "title": article.get("title", "无标题"),
                    "source": article.get("source", {}).get("name", "未知来源"),
                    "url": article.get("url", "#"),
                    "publishedAt": article.get("publishedAt", ""),
                    "description": article.get("description", "")
                })

            return {
                "articles": formatted_articles,
                "error": None
            }
        else:
            error_msg = f"HTTP {response.status_code}"
            print(f"[daily_bulletin] News API HTTP error: {error_msg}")
            return {
                "articles": [],
                "error": f"新闻服务暂不可用: {error_msg}"
            }
    except Exception as e:
        print(f"[daily_bulletin] News exception: {e}")
        import traceback
        traceback.print_exc()
        return {
            "articles": [],
            "error": f"新闻服务异常: {str(e)}"
        }

# ============ 路由 ============

@bp.get("/")
def page():
    """主页面"""
    resp = make_response(render_template(f"games/{SLUG}/index.html"))
    return _ensure_sid(resp)

@bp.post("/api/fetch")
def fetch_bulletin_data():
    """
    API 端点：获取板报数据
    前端调用此接口获取位置、天气、新闻
    """
    try:
        # 获取用户 IP
        user_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if user_ip:
            user_ip = user_ip.split(",")[0].strip()

        # 1. 获取位置
        location = get_location_from_ip(user_ip)

        # 2. 获取天气
        weather = get_weather(location.get("lat"), location.get("lon"))

        # 3. 获取新闻
        # 根据国家代码调整新闻源
        country_map = {
            "China": "cn",
            "United States": "us",
            "United Kingdom": "gb",
            "Japan": "jp",
            "Korea": "kr"
        }
        country_code = country_map.get(location.get("country"), "us")
        news = get_news(country_code)

        # 4. 当前日期时间（使用 UTC，前端会转换为用户本地时间）
        now = datetime.utcnow()
        date_info = {
            "date": now.strftime("%Y年%m月%d日"),
            "weekday": ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][now.weekday()],
            "time": now.strftime("%H:%M:%S"),
            "timestamp": int(now.timestamp() * 1000) if hasattr(now, 'timestamp') else None,  # 毫秒时间戳
            "timezone": location.get("timezone", "UTC")  # 返回用户时区
        }

        return jsonify({
            "ok": True,
            "location": location,
            "weather": weather,
            "news": news,
            "date": date_info
        })

    except Exception as e:
        print(f"[daily_bulletin] Fetch error: {e}")
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


# ============ 个性化功能 API ============

def _safe_get(row, key, index):
    """
    安全地从 RealDictRow 或 tuple 中获取值
    先尝试字典方式，失败则使用索引
    """
    if row is None:
        return None
    try:
        # 尝试字典访问
        return row[key]
    except (KeyError, TypeError):
        try:
            # 尝试索引访问
            return row[index] if len(row) > index else None
        except (IndexError, TypeError):
            return None

def _get_user_ref():
    """
    获取用户标识（复用主应用的用户系统）
    - 已登录用户返回 user_id
    - 访客返回基于 session_id 的 UUID
    """
    user = g.get("user", None)

    if user and not user.get("is_guest", True):
        # 已登录用户
        return str(user["id"])

    # 访客 - 生成稳定的 UUID
    if "session_id" not in session:
        import uuid
        session["session_id"] = uuid.uuid4().hex[:8]

    # 使用 session_id 生成合法 UUID
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_URL, session['session_id']))


@bp.get("/api/user/status")
def get_user_status():
    """获取用户状态（是否登录）"""
    try:
        user = g.get("user", None)
        is_logged_in = user and not user.get("is_guest", True)

        return jsonify({
            "ok": True,
            "logged_in": is_logged_in,
            "username": user.get("username") if is_logged_in else None,
            "user_id": user.get("id") if is_logged_in else None
        })
    except Exception as e:
        print(f"[daily_bulletin] Get user status error: {e}")
        return jsonify({
            "ok": False,
            "logged_in": False,
            "error": str(e)
        }), 500


# ============ Notes API ============

@bp.get("/api/notes")
def get_notes():
    """获取用户的记事本列表"""
    try:
        user_ref = _get_user_ref()
        notes = DailyBulletinNoteDAO.get_user_notes(user_ref, limit=20)

        # 转换为 JSON 友好格式
        notes_list = []
        for note in notes:
            created_at = _safe_get(note, "created_at", 3)
            updated_at = _safe_get(note, "updated_at", 4)
            notes_list.append({
                "id": _safe_get(note, "id", 0),
                "content": _safe_get(note, "content", 2),
                "created_at": created_at.isoformat() if created_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None
            })

        return jsonify({
            "ok": True,
            "notes": notes_list
        })
    except Exception as e:
        print(f"[daily_bulletin] Get notes error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@bp.post("/api/notes")
def create_note():
    """创建新笔记"""
    try:
        data = request.get_json() or {}
        content = data.get("content", "").strip()

        if not content:
            return jsonify({
                "ok": False,
                "error": "笔记内容不能为空"
            }), 400

        user_ref = _get_user_ref()
        note = DailyBulletinNoteDAO.create_note(user_ref, content)

        created_at = _safe_get(note, "created_at", 3)
        updated_at = _safe_get(note, "updated_at", 4)

        return jsonify({
            "ok": True,
            "note": {
                "id": _safe_get(note, "id", 0),
                "content": _safe_get(note, "content", 2),
                "created_at": created_at.isoformat() if created_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None
            }
        })
    except Exception as e:
        print(f"[daily_bulletin] Create note error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@bp.put("/api/notes/<int:note_id>")
def update_note(note_id):
    """更新笔记"""
    try:
        data = request.get_json() or {}
        content = data.get("content", "").strip()

        if not content:
            return jsonify({
                "ok": False,
                "error": "笔记内容不能为空"
            }), 400

        user_ref = _get_user_ref()
        note = DailyBulletinNoteDAO.update_note(note_id, user_ref, content)

        if not note:
            return jsonify({
                "ok": False,
                "error": "笔记不存在或无权限"
            }), 404

        created_at = _safe_get(note, "created_at", 3)
        updated_at = _safe_get(note, "updated_at", 4)

        return jsonify({
            "ok": True,
            "note": {
                "id": _safe_get(note, "id", 0),
                "content": _safe_get(note, "content", 2),
                "created_at": created_at.isoformat() if created_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None
            }
        })
    except Exception as e:
        print(f"[daily_bulletin] Update note error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@bp.delete("/api/notes/<int:note_id>")
def delete_note(note_id):
    """删除笔记"""
    try:
        user_ref = _get_user_ref()
        success = DailyBulletinNoteDAO.delete_note(note_id, user_ref)

        if not success:
            return jsonify({
                "ok": False,
                "error": "笔记不存在或无权限"
            }), 404

        return jsonify({
            "ok": True,
            "message": "笔记已删除"
        })
    except Exception as e:
        print(f"[daily_bulletin] Delete note error: {e}")
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


# ============ Todos API ============

@bp.get("/api/todos")
def get_todos():
    """获取用户的待办事项列表"""
    try:
        user_ref = _get_user_ref()
        include_completed = request.args.get("include_completed", "false").lower() == "true"

        todos = DailyBulletinTodoDAO.get_user_todos(user_ref, include_completed)

        # 转换为 JSON 友好格式
        todos_list = []
        for todo in todos:
            created_at = _safe_get(todo, "created_at", 5)
            updated_at = _safe_get(todo, "updated_at", 6)
            completed_at = _safe_get(todo, "completed_at", 7)

            todos_list.append({
                "id": _safe_get(todo, "id", 0),
                "content": _safe_get(todo, "content", 2),
                "completed": _safe_get(todo, "completed", 3),
                "priority": _safe_get(todo, "priority", 4),
                "created_at": created_at.isoformat() if created_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None,
                "completed_at": completed_at.isoformat() if completed_at else None
            })

        return jsonify({
            "ok": True,
            "todos": todos_list
        })
    except Exception as e:
        print(f"[daily_bulletin] Get todos error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@bp.post("/api/todos")
def create_todo():
    """创建新待办事项"""
    try:
        data = request.get_json() or {}
        content = data.get("content", "").strip()
        priority = data.get("priority", 2)  # 默认中优先级

        if not content:
            return jsonify({
                "ok": False,
                "error": "待办内容不能为空"
            }), 400

        # 验证优先级
        if priority not in [1, 2, 3]:
            priority = 2

        user_ref = _get_user_ref()
        todo = DailyBulletinTodoDAO.create_todo(user_ref, content, priority)

        created_at = _safe_get(todo, "created_at", 5)
        updated_at = _safe_get(todo, "updated_at", 6)

        return jsonify({
            "ok": True,
            "todo": {
                "id": _safe_get(todo, "id", 0),
                "content": _safe_get(todo, "content", 2),
                "completed": _safe_get(todo, "completed", 3),
                "priority": _safe_get(todo, "priority", 4),
                "created_at": created_at.isoformat() if created_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None
            }
        })
    except Exception as e:
        print(f"[daily_bulletin] Create todo error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@bp.put("/api/todos/<int:todo_id>")
def update_todo(todo_id):
    """更新待办事项"""
    try:
        data = request.get_json() or {}
        content = data.get("content")
        completed = data.get("completed")
        priority = data.get("priority")

        # 至少需要更新一个字段
        if content is None and completed is None and priority is None:
            return jsonify({
                "ok": False,
                "error": "没有要更新的字段"
            }), 400

        # 验证优先级
        if priority is not None and priority not in [1, 2, 3]:
            return jsonify({
                "ok": False,
                "error": "优先级必须是 1（高）、2（中）或 3（低）"
            }), 400

        user_ref = _get_user_ref()
        todo = DailyBulletinTodoDAO.update_todo(
            todo_id,
            user_ref,
            content=content.strip() if content else None,
            completed=completed,
            priority=priority
        )

        if not todo:
            return jsonify({
                "ok": False,
                "error": "待办事项不存在或无权限"
            }), 404

        created_at = _safe_get(todo, "created_at", 5)
        updated_at = _safe_get(todo, "updated_at", 6)
        completed_at = _safe_get(todo, "completed_at", 7)

        return jsonify({
            "ok": True,
            "todo": {
                "id": _safe_get(todo, "id", 0),
                "content": _safe_get(todo, "content", 2),
                "completed": _safe_get(todo, "completed", 3),
                "priority": _safe_get(todo, "priority", 4),
                "created_at": created_at.isoformat() if created_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None,
                "completed_at": completed_at.isoformat() if completed_at else None
            }
        })
    except Exception as e:
        print(f"[daily_bulletin] Update todo error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@bp.delete("/api/todos/<int:todo_id>")
def delete_todo(todo_id):
    """删除待办事项"""
    try:
        user_ref = _get_user_ref()
        success = DailyBulletinTodoDAO.delete_todo(todo_id, user_ref)

        if not success:
            return jsonify({
                "ok": False,
                "error": "待办事项不存在或无权限"
            }), 404

        return jsonify({
            "ok": True,
            "message": "待办事项已删除"
        })
    except Exception as e:
        print(f"[daily_bulletin] Delete todo error: {e}")
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


def get_blueprint():
    return bp
