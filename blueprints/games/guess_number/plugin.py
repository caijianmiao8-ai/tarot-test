# plugins.py（稳定版）
import importlib, pkgutil
from typing import List, Dict

_PLUGINS: List[Dict] = []

def register_plugins(app, base_pkg: str):
    print(f"[plugins] loading from base_pkg='{base_pkg}'")
    pkg = importlib.import_module(base_pkg)

    found = 0
    for m in pkgutil.iter_modules(pkg.__path__):
        mod_name = f"{base_pkg}.{m.name}.plugin"
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            print(f"[plugins] skip: {mod_name} not found")
            continue

        get_meta = getattr(mod, "get_meta", None)
        get_bp   = getattr(mod, "get_blueprint", None)
        if not callable(get_meta) or not callable(get_bp):
            print(f"[plugins] skip: {mod_name} missing get_meta/get_blueprint")
            continue

        meta = get_meta()
        bp   = get_bp()
        slug = meta.get("slug", m.name)

        app.register_blueprint(bp, url_prefix=f"/g/{slug}")
        _PLUGINS.append(meta)
        found += 1
        print(f"[plugins] Registered '{slug}' at /g/{slug}/")

    if found == 0:
        print(f"[plugins] WARNING: no plugins found under {base_pkg}")

def plugin_metas() -> List[Dict]:
    return list(_PLUGINS)
