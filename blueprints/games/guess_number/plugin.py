# plugins.py（最终稳版）
import importlib
import pkgutil
from typing import List, Dict

_PLUGINS: List[Dict] = []

def _pick_base_pkg(user_pkg: str | None):
    if user_pkg:
        try:
            pkg = importlib.import_module(user_pkg)
            print(f"[plugins] base_pkg set explicitly: {user_pkg}")
            return user_pkg, pkg
        except ModuleNotFoundError:
            print(f"[plugins] ERROR: base_pkg='{user_pkg}' not importable")
            return None, None

    for cand in ("blueprints.games", "games"):
        try:
            pkg = importlib.import_module(cand)
            print(f"[plugins] autodetected base_pkg: {cand}")
            return cand, pkg
        except ModuleNotFoundError:
            continue
    print("[plugins] ERROR: no plugin package found (tried 'blueprints.games', 'games')")
    return None, None

def register_plugins(app, base_pkg: str | None = None):
    global _PLUGINS
    picked, pkg = _pick_base_pkg(base_pkg)
    if not pkg:
        return

    count = 0
    for m in pkgutil.iter_modules(pkg.__path__):
        mod_name = f"{picked}.{m.name}.plugin"
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
        count += 1
        print(f"[plugins] Registered '{slug}' at /g/{slug}/")

    if count == 0:
        print(f"[plugins] WARNING: no plugins found under {picked}")

def plugin_metas() -> List[Dict]:
    return list(_PLUGINS)
