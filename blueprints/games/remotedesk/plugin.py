# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, make_response

SLUG = "remotedesk"

def get_meta():
    """
    返回游戏元信息，用于主页展示和注册
    """
    return {
        "slug": SLUG,
        "title": "Glintdesk",
        "subtitle": "手机远程控制电脑 · 永久免费",
        "path": f"/g/{SLUG}/",
        "tags": ["Glintdesk", "远程控制", "官网"]
    }

bp = Blueprint(
    SLUG,
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",
)

@bp.get("/")
@bp.get("")
def page():
    """
    RemoteDesk 官网设计展示页面
    """
    resp = make_response(render_template(f"games/{SLUG}/index.html"))
    return resp

def get_blueprint():
    """
    返回 Blueprint 实例，供 plugins.py 注册
    """
    return bp
