# blueprints/games/reaction_timer/routes.py
from flask import Blueprint, render_template

SLUG = "reaction_timer"

bp = Blueprint(
    SLUG,
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",  # /static/games/reaction_timer/...
)

@bp.get("/")
def page():
    return render_template("games/reaction_timer/index.html")
