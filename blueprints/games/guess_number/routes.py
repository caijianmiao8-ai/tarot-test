from flask import Blueprint, render_template, request, jsonify

bp = Blueprint("guess_number", __name__, template_folder="templates")

@bp.get("/")
def page():
    return render_template("games/guess_number/index.html")

# 极简无DB示例：纯内存，不上生产，只为跑通结构
secret = 42

@bp.post("/api/guess")
def api_guess():
    try:
        n = int((request.json or {}).get("n", 0))
    except Exception:
        return jsonify({"ok": False, "error": "bad_input"}), 400
    if n == secret:
        return jsonify({"ok": True, "result": "equal"})
    return jsonify({"ok": True, "result": "low" if n < secret else "high"})
