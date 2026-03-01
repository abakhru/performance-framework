"""
plugins/__init__.py — Plugin registry with auto-discovery.

Call :func:`register_all` once at startup (in ``dashboard/server.py``).
Thereafter :func:`get_plugins` returns the ordered list of loaded plugins
whose routers the FastAPI app should mount.

Adding a new plugin
-------------------
1. Create ``src/plugins/<name>/`` directory.
2. Add ``__init__.py`` that sets ``plugin = PluginMeta(...)``.
3. That's it — ``register_all()`` will pick it up automatically.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from plugins.base import PluginMeta

_PLUGINS: list[PluginMeta] = []

# Plugins loaded in this order so their routes appear in the correct OpenAPI section.
# Any plugin NOT listed here is appended afterwards in discovery order.
_PREFERRED_ORDER = [
    "performance",
    "discovery",
    "test_generator",
    "api_tests",
    "ui_tests",
    "lighthouse",
    "visual_qa",
]


def register_all() -> list[PluginMeta]:
    """Auto-discover every sub-package of ``plugins/`` and register it."""
    if _PLUGINS:
        return _PLUGINS  # idempotent

    plugins_dir = Path(__file__).parent
    found: dict[str, PluginMeta] = {}

    for _finder, name, is_pkg in pkgutil.iter_modules([str(plugins_dir)]):
        if not is_pkg or name == "base":
            continue
        try:
            mod = importlib.import_module(f"plugins.{name}")
            if hasattr(mod, "plugin") and isinstance(mod.plugin, PluginMeta):
                found[name] = mod.plugin
        except Exception as exc:
            print(f"[plugins] ⚠ Failed to load plugin {name!r}: {exc}")

    # Emit in preferred order first, then any extras alphabetically
    for name in _PREFERRED_ORDER:
        if name in found:
            _PLUGINS.append(found.pop(name))
    for meta in sorted(found.values(), key=lambda m: m.name):
        _PLUGINS.append(meta)

    return _PLUGINS


def get_plugins() -> list[PluginMeta]:
    """Return the list of registered plugins (call ``register_all`` first)."""
    return list(_PLUGINS)
