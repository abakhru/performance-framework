"""
lighthouse_runner.py — Run Google Lighthouse audits and parse results.
"""

import json
import subprocess
import threading
import uuid
from datetime import datetime

from storage import REPO_ROOT

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


def _extract_result(lh_json: dict) -> dict:
    """Extract key fields from full Lighthouse JSON into a compact result dict."""
    cats = lh_json.get("categories", {})
    audits = lh_json.get("audits", {})

    def score(key: str) -> int | None:
        s = cats.get(key, {}).get("score")
        return round(s * 100) if s is not None else None

    def audit_val(key: str) -> dict:
        a = audits.get(key, {})
        return {
            "display": a.get("displayValue", ""),
            "value": a.get("numericValue"),
            "score": a.get("score"),
        }

    # Collect opportunities (type=opportunity with savings)
    opportunities = []
    for aid, a in audits.items():
        if a.get("details", {}).get("type") == "opportunity" and a.get("score") is not None and a.get("score") < 1:
            savings = a.get("details", {}).get("overallSavingsMs", 0) or 0
            if savings > 0 or a.get("score") < 0.9:
                opportunities.append(
                    {
                        "id": aid,
                        "title": a.get("title", aid),
                        "description": a.get("description", ""),
                        "display": a.get("displayValue", ""),
                        "savings_ms": round(savings),
                        "score": a.get("score"),
                    }
                )
    opportunities.sort(key=lambda x: x["savings_ms"], reverse=True)

    # Collect diagnostics (type=diagnostic, score < 1)
    diagnostics = []
    for aid, a in audits.items():
        if a.get("details", {}).get("type") == "diagnostic" and a.get("score") is not None and a.get("score") < 1:
            diagnostics.append(
                {
                    "id": aid,
                    "title": a.get("title", aid),
                    "display": a.get("displayValue", ""),
                    "score": a.get("score"),
                }
            )
    diagnostics.sort(key=lambda x: x["score"] or 1)

    return {
        "url": lh_json.get("finalDisplayedUrl") or lh_json.get("requestedUrl", ""),
        "ran_at": lh_json.get("fetchTime", datetime.now().isoformat()),
        "categories": {
            "performance": score("performance"),
            "accessibility": score("accessibility"),
            "best_practices": score("best-practices"),
            "seo": score("seo"),
        },
        "metrics": {
            "fcp": audit_val("first-contentful-paint"),
            "lcp": audit_val("largest-contentful-paint"),
            "tbt": audit_val("total-blocking-time"),
            "cls": audit_val("cumulative-layout-shift"),
            "tti": audit_val("interactive"),
            "si": audit_val("speed-index"),
        },
        "opportunities": opportunities[:8],
        "diagnostics": diagnostics[:8],
    }


def run_lighthouse(url: str, device: str = "desktop", categories: list | None = None) -> str:
    """Start a Lighthouse run in a background thread. Returns run_id."""
    run_id = str(uuid.uuid4())
    with _runs_lock:
        _runs[run_id] = {"status": "running", "error": None, "result": None}
    threading.Thread(target=_run_worker, args=(run_id, url, device, categories or []), daemon=True).start()
    return run_id


def _run_worker(run_id: str, url: str, device: str, categories: list) -> None:
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
        f"--form-factor={device}",
        f"--only-categories={cat_flag}",
        "--quiet",
        "--no-enable-error-reporting",
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
