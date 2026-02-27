"""
influx.py — InfluxDB write/query/parse helpers for the k6 dashboard.

Public API:
  influx_write(lines)           — POST line-protocol to InfluxDB
  influx_query(flux) → list     — POST Flux query, return list of row dicts
  init_influx() → bool          — Wait for InfluxDB to become healthy
  lp_tag(v) → str               — Escape tag value for line protocol
  lp_str(v) → str               — Quote string field for line protocol
  now_ns() → int                — Current time in nanoseconds
  now() → str                   — Current time as ISO-8601 string
"""

import csv
import json
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime

# ── InfluxDB connection settings (overridden by main() from env) ───────────────

INFLUX_URL = "http://localhost:8086"
INFLUX_ORG = "matrix"
INFLUX_BUCKET = "k6"
INFLUX_TOKEN = "matrix-k6-token"


# ── Line-protocol helpers ──────────────────────────────────────────────────────


def lp_tag(v: str) -> str:
    """Escape a tag key or tag value for InfluxDB line protocol."""
    return v.replace(",", r"\,").replace("=", r"\=").replace(" ", r"\ ")


def lp_str(v: str) -> str:
    """Quote a string field value for InfluxDB line protocol."""
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def now_ns() -> int:
    """Current wall-clock time as nanoseconds since epoch."""
    return int(time.time() * 1e9)


def now() -> str:
    """Current UTC time as ISO-8601 string (second precision)."""
    return datetime.now(UTC).isoformat(timespec="seconds")


# ── InfluxDB write ─────────────────────────────────────────────────────────────


def influx_write(lines) -> None:
    """POST one or more line-protocol lines to InfluxDB."""
    body = ("\n".join(lines) if isinstance(lines, list) else lines).encode()
    url = f"{INFLUX_URL}/api/v2/write?org={INFLUX_ORG}&bucket={INFLUX_BUCKET}&precision=ns"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Token {INFLUX_TOKEN}",
            "Content-Type": "text/plain; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            r.read()
    except urllib.error.HTTPError as e:
        print(f"[influx] write error {e.code}: {e.read().decode()}", flush=True)
    except Exception as e:
        print(f"[influx] write error: {e}", flush=True)


# ── InfluxDB query ─────────────────────────────────────────────────────────────


def influx_query(flux: str) -> list[dict]:
    """POST a Flux query and return parsed rows as a list of dicts."""
    url = f"{INFLUX_URL}/api/v2/query?org={INFLUX_ORG}"
    body = json.dumps({"query": flux, "type": "flux"}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Token {INFLUX_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/csv",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return parse_influx_csv(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"[influx] query error {e.code}: {e.read().decode()}", flush=True)
        return []
    except Exception as e:
        print(f"[influx] query error: {e}", flush=True)
        return []


def parse_influx_csv(text: str) -> list[dict]:
    """Parse annotated CSV returned by the InfluxDB /api/v2/query endpoint."""
    SKIP = {"", "result", "table", "_start", "_stop", "_measurement"}
    rows, header = [], None
    for line in text.splitlines():
        if not line.strip():
            header = None
            continue
        if line.startswith("#"):
            continue
        parts = next(csv.reader([line]))
        if header is None:
            header = parts
            continue
        if len(parts) != len(header):
            continue
        rows.append({k: v for k, v in zip(header, parts) if k not in SKIP})
    return rows


# ── InfluxDB init ──────────────────────────────────────────────────────────────


def init_influx() -> bool:
    """Poll InfluxDB /health for up to 30 seconds; return True if reachable."""
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                urllib.request.Request(
                    f"{INFLUX_URL}/health",
                    headers={"Authorization": f"Token {INFLUX_TOKEN}"},
                ),
                timeout=3,
            ) as r:
                if r.status == 200:
                    print("[influx] InfluxDB ready", flush=True)
                    return True
        except Exception:
            pass
        time.sleep(1)
    print("[influx] WARNING: InfluxDB not reachable after 30 s", flush=True)
    return False
