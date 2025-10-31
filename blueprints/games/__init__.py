# 自动发现并注册 /blueprints/games/*/routes.py 中的 bp
import importlib, pkgutil

def register_all_games(app):
    import blueprints.games as pkg
    for m in pkgutil.iter_modules(pkg.__path__):
        # 约定每个游戏的蓝图定义在 <game>/routes.py 里，变量名叫 bp
        mod = importlib.import_module(f"{pkg.__name__}.{m.name}.routes")
        bp = getattr(mod, "bp", None)
        if bp:
            app.register_blueprint(bp, url_prefix=f"/g/{m.name}")
