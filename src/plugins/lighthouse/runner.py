"""
lighthouse_runner.py — Run Google Lighthouse audits and parse results.
"""

import json
import subprocess
import threading
import uuid
from datetime import datetime

from core.storage import REPO_ROOT

LIGHTHOUSE_BIN = "/opt/homebrew/bin/lighthouse"
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
LH_DATA_DIR = REPO_ROOT / "data" / "lighthouse"

# State dict: run_id -> {"status": "running|done|error", "error": None, "result": None}
_runs: dict = {}
_runs_lock = threading.Lock()


def _score_color(score: int | None) -> str:
    """Return Lighthouse color category string for a 0-100 score."""
    if score is None:
        return "average"
    if score >= 90:
        return "good"
    if score >= 50:
        return "average"
    return "poor"


def _flatten_item(item: dict, headings: list) -> dict:
    """Flatten one audit details item into a display-friendly dict."""
    cols = [(h.get("key"), h.get("valueType", ""), h.get("label", "")) for h in headings if h.get("key")]
    row: dict = {}
    for key, vtype, label in cols:
        val = item.get(key)
        if val is None:
            continue
        # Unwrap nested Lighthouse value objects (source-location, url, code, etc.)
        if isinstance(val, dict):
            val = val.get("url") or val.get("value") or val.get("text") or val.get("type") or str(val)
        if isinstance(val, (str, int, float)):
            row[key] = {"v": val, "t": vtype, "l": label}
    return row


def _extract_items(details: dict, max_items: int = 8) -> list:
    """Extract display rows from audit details.items, resolving heading metadata."""
    items = details.get("items", [])
    if not isinstance(items, list):
        return []
    headings = details.get("headings", [])
    if not isinstance(headings, list):
        headings = []
    result = []
    for item in items[:max_items]:
        row = _flatten_item(item, headings)
        if row:
            result.append(row)
    return result


def _extract_result(lh_json: dict) -> dict:
    """Extract key fields from full Lighthouse JSON into a rich result dict."""
    cats = lh_json.get("categories", {})
    audits = lh_json.get("audits", {})

    def cat_score(key: str) -> int | None:
        s = cats.get(key, {}).get("score")
        return round(s * 100) if s is not None else None

    def audit_val(key: str) -> dict:
        a = audits.get(key, {})
        return {
            "display": a.get("displayValue", ""),
            "value": a.get("numericValue"),
            "score": a.get("score"),
        }

    # Build audit-id → category mapping from auditRefs
    audit_category: dict[str, str] = {}
    for cat_key, cat_data in cats.items():
        for ref in cat_data.get("auditRefs") or []:
            audit_category[ref["id"]] = cat_key

    # Collect opportunities (type=opportunity, any failing score)
    opportunities = []
    for aid, a in audits.items():
        details = a.get("details", {})
        sc = a.get("score")
        if details.get("type") == "opportunity" and sc is not None and sc < 1:
            savings = details.get("overallSavingsMs", 0) or 0
            opportunities.append(
                {
                    "id": aid,
                    "title": a.get("title", aid),
                    "description": a.get("description", ""),
                    "display": a.get("displayValue", ""),
                    "savings_ms": round(savings),
                    "score": sc,
                    "items": _extract_items(details),
                }
            )
    opportunities.sort(key=lambda x: x["savings_ms"], reverse=True)

    # Collect diagnostics (type=diagnostic, score < 1)
    diagnostics = []
    for aid, a in audits.items():
        details = a.get("details", {})
        sc = a.get("score")
        if details.get("type") == "diagnostic" and sc is not None and sc < 1:
            diagnostics.append(
                {
                    "id": aid,
                    "title": a.get("title", aid),
                    "description": a.get("description", ""),
                    "display": a.get("displayValue", ""),
                    "score": sc,
                    "items": _extract_items(details),
                }
            )
    diagnostics.sort(key=lambda x: x["score"] if x["score"] is not None else 1)

    # Group all audits by category into failed / passed lists
    audits_by_category: dict[str, dict] = {}
    for aid, a in audits.items():
        mode = a.get("scoreDisplayMode", "")
        if mode in ("notApplicable", "manual", "error"):
            continue
        sc = a.get("score")
        if sc is None:
            continue
        cat = audit_category.get(aid, "other")
        bucket = audits_by_category.setdefault(cat, {"failed": [], "passed": []})
        entry = {
            "id": aid,
            "title": a.get("title", aid),
            "description": a.get("description", ""),
            "display": a.get("displayValue", ""),
            "score": sc,
        }
        if sc < 0.9:
            details = a.get("details", {})
            if details.get("items"):
                entry["items"] = _extract_items(details)
            bucket["failed"].append(entry)
        else:
            bucket["passed"].append(entry)

    # Sort failed audits within each category by score ascending
    for bucket in audits_by_category.values():
        bucket["failed"].sort(key=lambda x: x["score"] if x["score"] is not None else 1)

    return {
        "url": lh_json.get("finalDisplayedUrl") or lh_json.get("requestedUrl", ""),
        "ran_at": lh_json.get("fetchTime", datetime.now().isoformat()),
        "categories": {
            "performance": cat_score("performance"),
            "accessibility": cat_score("accessibility"),
            "best_practices": cat_score("best-practices"),
            "seo": cat_score("seo"),
        },
        "metrics": {
            "fcp": audit_val("first-contentful-paint"),
            "lcp": audit_val("largest-contentful-paint"),
            "tbt": audit_val("total-blocking-time"),
            "cls": audit_val("cumulative-layout-shift"),
            "tti": audit_val("interactive"),
            "si": audit_val("speed-index"),
        },
        "opportunities": opportunities,
        "diagnostics": diagnostics,
        "audits_by_category": audits_by_category,
    }


def run_lighthouse(
    url: str,
    device: str = "desktop",
    categories: list | None = None,
    extra_headers: dict | None = None,
) -> str:
    """Start a Lighthouse run in a background thread. Returns run_id."""
    run_id = str(uuid.uuid4())
    with _runs_lock:
        _runs[run_id] = {"status": "running", "error": None, "result": None}
    threading.Thread(
        target=_run_worker,
        args=(run_id, url, device, categories or [], extra_headers or {}),
        daemon=True,
    ).start()
    return run_id


def _run_worker(run_id: str, url: str, device: str, categories: list, extra_headers: dict) -> None:
    import json as _json

    LH_DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = LH_DATA_DIR / f"{run_id}.json"

    cat_flag = ",".join(categories) if categories else "performance,accessibility,best-practices,seo"

    cmd = [
        LIGHTHOUSE_BIN,
        url,
        "--output",
        "json",
        "--output-path",
        str(out_path),
        "--chrome-path",
        CHROME_PATH,
        "--chrome-flags=--headless --no-sandbox --disable-gpu --disable-dev-shm-usage",
        *(["--preset=desktop"] if device == "desktop" else []),
        f"--only-categories={cat_flag}",
        "--quiet",
        "--no-enable-error-reporting",
        *(["--extra-headers", _json.dumps(extra_headers)] if extra_headers else []),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=180)
        if out_path.exists():
            raw = json.loads(out_path.read_text(encoding="utf-8"))
            result = _extract_result(raw)
            # Save compact result too
            compact_path = LH_DATA_DIR / f"{run_id}_compact.json"
            compact_path.write_text(json.dumps(result, indent=2))
            with _runs_lock:
                _runs[run_id] = {"status": "done", "error": None, "result": result}
        else:
            err = proc.stderr.decode(errors="replace")[-500:]
            with _runs_lock:
                _runs[run_id] = {"status": "error", "error": err or "No output produced", "result": None}
    except subprocess.TimeoutExpired:
        with _runs_lock:
            _runs[run_id] = {"status": "error", "error": "Lighthouse timed out after 180s", "result": None}
    except Exception as e:
        with _runs_lock:
            _runs[run_id] = {"status": "error", "error": str(e), "result": None}


def get_status(run_id: str) -> dict:
    with _runs_lock:
        s = _runs.get(run_id)
    if not s:
        return {"status": "not_found"}
    return {"status": s["status"], "run_id": run_id, "error": s.get("error")}


def get_result(run_id: str) -> dict | None:
    with _runs_lock:
        s = _runs.get(run_id)
    if s and s.get("result"):
        return s["result"]
    # Fallback: try reading compact file from disk (survives restarts)
    path = LH_DATA_DIR / f"{run_id}_compact.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return None
    return None


def list_history(max_items: int = 20) -> list:
    """Scan LH_DATA_DIR for compact results and return metadata list newest-first."""
    if not LH_DATA_DIR.exists():
        return []
    results = []
    for p in sorted(LH_DATA_DIR.glob("*_compact.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:max_items]:
        try:
            data = json.loads(p.read_text())
            run_id = p.name.replace("_compact.json", "")
            results.append(
                {
                    "run_id": run_id,
                    "url": data.get("url", ""),
                    "ran_at": data.get("ran_at", ""),
                    "scores": data.get("categories", {}),
                }
            )
        except Exception:
            pass
    return results
