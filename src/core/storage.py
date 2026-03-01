"""
core/storage.py — File I/O helpers and type coercions for the k6 dashboard.

Handles reading/writing:
  - Dashboard state  (data/state.json)
  - Run profiles     (data/profiles.json)
  - Webhooks         (data/webhooks.json)
  - Endpoint config  (k6/config/endpoints.json)

All path constants are imported from core.config so this module has no
hard-coded filesystem assumptions.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from core.config import (
    DASHBOARD_STATE,
    DATA_DIR,
    HOOKS_DIR,
    PROFILES_FILE,
    REPO_ROOT,
    SAVED_CONFIGS_DIR,
    WEBHOOKS_FILE,
)
from core.config import (
    ENDPOINTS_JSON as _ENDPOINTS_JSON,
)

# Re-export the path constants that other modules depended on via `from storage import …`
SCRIPT_DIR = Path(__file__).parent.parent / "dashboard"  # src/dashboard/ (index.html lives here)

__all__ = [
    # paths
    "SCRIPT_DIR", "REPO_ROOT", "DATA_DIR", "HOOKS_DIR",
    # functions
    "load_endpoint_config", "save_endpoints_json", "build_op_group",
    "save_named_config", "list_saved_configs", "load_named_config",
    "load_state", "save_state",
    "load_profiles", "save_profiles",
    "load_webhooks", "save_webhooks",
    "coerce_int", "coerce_float",
]


# ── Endpoint config ────────────────────────────────────────────────────────────


def load_endpoint_config() -> dict:
    """Load k6/config/endpoints.json; return empty structure on any failure."""
    try:
        with open(_ENDPOINTS_JSON, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"endpoints": [], "setup": [], "teardown": []}


def save_endpoints_json(config: dict, _globals_ref: dict | None = None) -> None:
    """Write endpoints.json and optionally update caller's global references."""
    with open(_ENDPOINTS_JSON, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    if _globals_ref is not None:
        _globals_ref["_endpoint_config"] = config
        _globals_ref["OP_GROUP"] = build_op_group(config)


def _config_slug(service: str, source: str) -> str:
    svc = re.sub(r"[^a-z0-9]+", "-", (service or "config").lower()).strip("-")[:30]
    src = re.sub(r"[^a-z0-9]+", "-", (source or "manual").lower()).strip("-")[:20]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{svc}_{src}_{ts}"


def save_named_config(config: dict) -> str:
    """Write a uniquely-named copy to SAVED_CONFIGS_DIR; return the filename."""
    SAVED_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    service = config.get("service") or "config"
    source = config.get("_source") or "manual"
    slug = _config_slug(service, source)
    filename = f"{slug}.json"
    to_save = {k: v for k, v in config.items() if not k.startswith("_")}
    to_save["_meta"] = {
        "saved_at": datetime.now().isoformat(),
        "source": source,
        "filename": filename,
        "base_url": config.get("_base_url", ""),
        "auth_token": config.get("_auth_token", ""),
    }
    with open(SAVED_CONFIGS_DIR / filename, "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2)
    return filename


def list_saved_configs() -> list:
    """Return metadata list for all saved configs, newest first."""
    if not SAVED_CONFIGS_DIR.exists():
        return []
    result = []
    for p in sorted(SAVED_CONFIGS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            with open(p, encoding="utf-8") as f:
                cfg = json.load(f)
            meta = cfg.get("_meta", {})
            result.append({
                "filename": p.name,
                "service": cfg.get("service", ""),
                "source": meta.get("source", ""),
                "endpoint_count": len(cfg.get("endpoints", [])),
                "saved_at": meta.get("saved_at", ""),
            })
        except Exception:
            pass
    return result


def load_named_config(name: str) -> dict:
    safe = re.sub(r"[^a-zA-Z0-9_\-.]", "", name)
    if not safe.endswith(".json"):
        return {}
    path = SAVED_CONFIGS_DIR / safe
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def build_op_group(cfg: dict) -> dict:
    """Build {op_name: group} mapping from all sections of endpoint config."""
    mapping = {}
    for section in ("endpoints", "setup", "teardown"):
        for ep in cfg.get(section, []):
            name = ep.get("name")
            grp = ep.get("group", name)
            if name:
                mapping[name] = grp
    return mapping


# ── Dashboard state ────────────────────────────────────────────────────────────


def load_state() -> dict:
    try:
        return json.loads(DASHBOARD_STATE.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_STATE.write_text(json.dumps(state, indent=2))


# ── Profiles ───────────────────────────────────────────────────────────────────


def load_profiles() -> dict:
    try:
        return json.loads(PROFILES_FILE.read_text())
    except Exception:
        return {}


def save_profiles(profiles: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_FILE.write_text(json.dumps(profiles, indent=2))


# ── Webhooks ───────────────────────────────────────────────────────────────────


def load_webhooks() -> list:
    try:
        return json.loads(WEBHOOKS_FILE.read_text())
    except Exception:
        return []


def save_webhooks(hooks: list) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WEBHOOKS_FILE.write_text(json.dumps(hooks, indent=2))


# ── Type coercions ─────────────────────────────────────────────────────────────


def coerce_int(v, default=None):
    if v is None or v == "":
        return default
    try:
        return int(float(v))
    except Exception:
        return default


def coerce_float(v, default=None):
    if v is None or v == "":
        return default
    try:
        return float(v)
    except Exception:
        return default
