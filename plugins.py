# plugins.py
import importlib, pkgutil
from typing import List, Dict

_PLUGINS: List[Dict] = []

def register_plugins(app, base_pkg="games"):
    global _PLUGINS
    pkg = importlib.import_module(base_pkg)
    for m in pkgutil.iter_modules(pkg.__path__):
        mod = importlib.import_module(f"{base_pkg}.{m.name}.plugin")
        meta = getattr(mod, "get_meta")()
        bp   = getattr(mod, "get_blueprint")()
        slug = meta["slug"]
        app.register_blueprint(bp, url_prefix=f"/g/{slug}")
        _PLUGINS.append(meta)

def plugin_metas() -> List[Dict]:
    return list(_PLUGINS)
