"""
storage.py — File I/O helpers and type coercions for the k6 dashboard.

Handles reading/writing:
  - Dashboard state (state.json)
  - Run profiles (profiles.json)
  - Webhooks (webhooks.json)
  - Endpoint config (k6/config/endpoints.json)
"""

import json
import re
from datetime import datetime
from pathlib import Path

# ── Path constants ─────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent

_ENDPOINTS_JSON = REPO_ROOT / "k6" / "config" / "endpoints.json"
SAVED_CONFIGS_DIR = REPO_ROOT / "k6" / "config" / "saved"
DASHBOARD_STATE = SCRIPT_DIR / "state.json"
PROFILES_FILE = SCRIPT_DIR / "profiles.json"
WEBHOOKS_FILE = SCRIPT_DIR / "webhooks.json"
DATA_DIR = REPO_ROOT / "data"
HOOKS_DIR = REPO_ROOT / "hooks"


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
    # If the caller passes a mutable dict with '_endpoint_config' and 'OP_GROUP'
    # keys, update them so the in-process state stays consistent.
    if _globals_ref is not None:
        _globals_ref["_endpoint_config"] = config
        _globals_ref["OP_GROUP"] = build_op_group(config)


def _config_slug(service: str, source: str) -> str:
    """Build a filesystem-safe slug for config filenames."""
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
    # Strip private underscore keys from the saved file, but capture useful ones in _meta
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
            result.append(
                {
                    "filename": p.name,
                    "service": cfg.get("service", ""),
                    "source": meta.get("source", ""),
                    "endpoint_count": len(cfg.get("endpoints", [])),
                    "saved_at": meta.get("saved_at", ""),
                }
            )
        except Exception:
            pass
    return result


def load_named_config(name: str) -> dict:
    """Load a named config from SAVED_CONFIGS_DIR; return {} if not found."""
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
    """Load dashboard state dict; returns {} on failure."""
    try:
        return json.loads(DASHBOARD_STATE.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    """Persist dashboard state dict."""
    DASHBOARD_STATE.write_text(json.dumps(state, indent=2))


# ── Profiles ───────────────────────────────────────────────────────────────────


def load_profiles() -> dict:
    """Load profiles dict; returns {} on failure."""
    try:
        return json.loads(PROFILES_FILE.read_text())
    except Exception:
        return {}


def save_profiles(profiles: dict) -> None:
    """Persist profiles dict."""
    PROFILES_FILE.write_text(json.dumps(profiles, indent=2))


# ── Webhooks ───────────────────────────────────────────────────────────────────


def load_webhooks() -> list:
    """Load webhooks list; returns [] on failure."""
    try:
        return json.loads(WEBHOOKS_FILE.read_text())
    except Exception:
        return []


def save_webhooks(hooks: list) -> None:
    """Persist webhooks list."""
    WEBHOOKS_FILE.write_text(json.dumps(hooks, indent=2))


# ── Type coercions ─────────────────────────────────────────────────────────────


def coerce_int(v, default=None):
    """Safely coerce a value to int; returns default on failure."""
    if v is None or v == "":
        return default
    try:
        return int(float(v))
    except Exception:
        return default


def coerce_float(v, default=None):
    """Safely coerce a value to float; returns default on failure."""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except Exception:
        return default
