# plugins.py
import importlib, pkgutil
from typing import List, Dict

_PLUGINS: List[Dict] = []

def register_plugins(app, base_pkg="games"):
    """
    自动发现 base_pkg.*.plugin，调用 get_meta()/get_blueprint() 注册到 /g/<slug>
    """
    global _PLUGINS
    try:
        pkg = importlib.import_module(base_pkg)
    except ModuleNotFoundError:
        print(f"[plugins] base_pkg '{base_pkg}' not found")
        return

    for m in pkgutil.iter_modules(pkg.__path__):
        mod_name = f"{base_pkg}.{m.name}.plugin"
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            # 子目录没有 plugin.py，跳过
            continue

        get_meta = getattr(mod, "get_meta", None)
        get_bp   = getattr(mod, "get_blueprint", None)
        if not callable(get_meta) or not callable(get_bp):
            print(f"[plugins] {mod_name} missing get_meta/get_blueprint, skipped")
            continue

        meta = get_meta()
        bp   = get_bp()
        slug = meta.get("slug", m.name)

        app.register_blueprint(bp, url_prefix=f"/g/{slug}")
        _PLUGINS.append(meta)
        print(f"[plugins] Registered '{slug}' at /g/{slug}/")

def plugin_metas() -> List[Dict]:
    return list(_PLUGINS)
