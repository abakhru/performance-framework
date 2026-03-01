"""
core/config.py — Centralised path constants and environment defaults.

All other modules import paths from here rather than computing them from
__file__.  This guarantees consistency regardless of where a module lives
in the source tree.

Usage::

    from core.config import REPO_ROOT, DATA_DIR, K6_DIR
"""

from pathlib import Path

# ── Repository layout ──────────────────────────────────────────────────────────

SRC_DIR: Path = Path(__file__).parent.parent       # …/meg/src/
REPO_ROOT: Path = SRC_DIR.parent                   # …/meg/

# Dashboard static files (index.html lives here)
DASHBOARD_STATIC_DIR: Path = SRC_DIR / "dashboard"

# k6 JavaScript entry-point and config
K6_DIR: Path = REPO_ROOT / "k6"
K6_SCRIPT: Path = K6_DIR / "main.js"
ENDPOINTS_JSON: Path = K6_DIR / "config" / "endpoints.json"
SAVED_CONFIGS_DIR: Path = K6_DIR / "config" / "saved"

# Runtime data produced at run-time (gitignored)
DATA_DIR: Path = REPO_ROOT / "data"
HOOKS_DIR: Path = REPO_ROOT / "hooks"

# Dashboard runtime state files (inside data/ so they're gitignored)
DASHBOARD_STATE: Path = DATA_DIR / "state.json"
PROFILES_FILE: Path = DATA_DIR / "profiles.json"
WEBHOOKS_FILE: Path = DATA_DIR / "webhooks.json"

# Generated test suites directory (created by test_generator plugin)
GENERATED_TESTS_DIR: Path = DATA_DIR / "generated-tests"

# ── Postman collection shipped in the repo ─────────────────────────────────────

POSTMAN_COLLECTION: Path = REPO_ROOT / "Matrix-Strike48_collections.postman_collection.json"

# ── Feature flags / defaults (overridable via env) ────────────────────────────

DASHBOARD_PORT: int = 5656
INFLUXDB_URL_DEFAULT: str = "http://localhost:8086"
INFLUXDB_ORG_DEFAULT: str = "matrix"
INFLUXDB_BUCKET_DEFAULT: str = "k6"
INFLUXDB_TOKEN_DEFAULT: str = "matrix-k6-token"
