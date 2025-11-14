# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, make_response

SLUG = "remotedesk"

def get_meta():
    """
    返回游戏元信息，用于主页展示和注册
    """
    return {
        "slug": SLUG,
        "title": "RemoteDesk",
        "subtitle": "远程桌面解决方案 · 高效协作",
        "path": f"/g/{SLUG}/",
        "tags": ["RemoteDesk", "远程协作", "官网"]
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
