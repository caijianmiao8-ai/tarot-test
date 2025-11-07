# -*- coding: utf-8 -*-
"""
每日板报 Blueprint
基于用户位置显示：日期、天气、全球新闻
"""
from flask import Blueprint, render_template, request, jsonify, make_response
import os
import json
import secrets
import requests
from datetime import datetime
from config import Config

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
    使用 ipapi.co 免费服务（无需 API Key）
    """
    try:
        if not ip_address or ip_address == "127.0.0.1":
            # 本地开发时使用公网 IP
            ip_address = requests.get("https://api.ipify.org", timeout=5).text

        url = f"{Config.IPAPI_URL}/{ip_address}/json/"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            return {
                "city": data.get("city", "Unknown"),
                "region": data.get("region", ""),
                "country": data.get("country_name", ""),
                "lat": data.get("latitude"),
                "lon": data.get("longitude"),
                "timezone": data.get("timezone", "UTC")
            }
    except Exception as e:
        print(f"[daily_bulletin] Location error: {e}")

    # 默认返回（如果 API 失败）
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
    if not Config.OPENWEATHER_API_KEY:
        return {
            "temp": "N/A",
            "description": "API Key 未配置",
            "humidity": "N/A",
            "wind_speed": "N/A",
            "icon": "01d"
        }

    if not lat or not lon:
        return {
            "temp": "N/A",
            "description": "位置信息不可用",
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

        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 200:
            data = response.json()
            main = data.get("main", {})
            weather = data.get("weather", [{}])[0]
            wind = data.get("wind", {})

            return {
                "temp": f"{main.get('temp', 'N/A')}°C",
                "description": weather.get("description", "未知"),
                "humidity": f"{main.get('humidity', 'N/A')}%",
                "wind_speed": f"{wind.get('speed', 'N/A')} km/h",
                "icon": weather.get("icon", "01d")
            }
    except Exception as e:
        print(f"[daily_bulletin] Weather error: {e}")

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

def get_blueprint():
    return bp
