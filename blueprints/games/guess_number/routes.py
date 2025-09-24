# blueprints/games/guess_number/routes.py
from flask import Blueprint, render_template, request, jsonify

SLUG = "guess_number"

bp = Blueprint(
    SLUG,
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path=f"/static/games/{SLUG}",  # 例如 /static/games/guess_number/main.css
)

@bp.get("/")
def page():
    return render_template("games/guess_number/index.html")

# 极简逻辑：只是为了演示结构
_SECRET = 42

@bp.post("/api/guess")
def api_guess():
    n = int((request.json or {}).get("n", 0))
    if n == _SECRET:
        return jsonify({"ok": True, "result": "equal"})
    return jsonify({"ok": True, "result": "low" if n < _SECRET else "high"})
