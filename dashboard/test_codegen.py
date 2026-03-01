"""
test_codegen.py — Auto-generation and execution of multi-type test suites.

Given a discovered endpoint config (from the Discover wizard) this module:
  1. Generates four artefact types into a unique timestamped directory:
       test_api_smoke.py      — pytest/httpx API smoke tests
       test_ui_playwright.py  — Playwright page-load / smoke UI tests
       endpoints_perf.json    — k6 endpoints config (ready to load via dashboard)
       lighthouse_urls.json   — list of URLs for Lighthouse auditing
       metadata.json          — provenance + result tracking

  2. Executes any combination of the four suites against the generated artefacts
     and appends structured results to  <dir>/results/<suite>.json.

Public API
----------
generate_suite(config, base_url, suites, output_root) → GeneratedSuite
run_suite(dir_name, suites, base_url, token, output_root) → dict[str, SuiteResult]
list_generated(output_root, limit) → list[dict]
get_generated(dir_name, output_root) → dict | None
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from storage import DATA_DIR

log = logging.getLogger(__name__)

GENERATED_DIR = DATA_DIR / "generated-tests"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

REPO_ROOT = Path(__file__).parent.parent

# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class SuiteResult:
    suite: str
    status: str  # "passed" | "failed" | "error" | "skipped" | "not_run"
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    total: int = 0
    duration_ms: float = 0.0
    error_message: str = ""
    output: str = ""


@dataclass
class GeneratedSuite:
    dir_name: str
    base_url: str
    endpoints_count: int
    suites_generated: list[str]
    files: list[str]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    results: dict[str, SuiteResult] = field(default_factory=dict)


# ── Directory helpers ─────────────────────────────────────────────────────────


def _make_dir_name() -> str:
    """Create a unique, sortable directory name: YYYYMMDD-HHMMSS-<8hex>"""
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    uid = uuid.uuid4().hex[:8]
    return f"{ts}-{uid}"


def _suite_dir(dir_name: str, output_root: Path | None = None) -> Path:
    root = output_root or GENERATED_DIR
    return root / dir_name


def _results_dir(dir_name: str, output_root: Path | None = None) -> Path:
    d = _suite_dir(dir_name, output_root) / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_metadata(dir_name: str, output_root: Path | None = None) -> dict | None:
    meta = _suite_dir(dir_name, output_root) / "metadata.json"
    if not meta.exists():
        return None
    try:
        return json.loads(meta.read_text())
    except Exception:
        return None


def _save_metadata(suite: GeneratedSuite, output_root: Path | None = None) -> None:
    d = _suite_dir(suite.dir_name, output_root)
    d.mkdir(parents=True, exist_ok=True)
    data = asdict(suite)
    (d / "metadata.json").write_text(json.dumps(data, indent=2))


# ── Code generators ────────────────────────────────────────────────────────────


def _gen_api_smoke(endpoints: list[dict], base_url: str, dir_name: str) -> str:
    """Generate pytest/httpx API smoke test source."""
    lines = [
        '"""Auto-generated API smoke tests.',
        f"Base URL: {base_url}",
        f"Generated: {datetime.now(UTC).isoformat()} | Suite: {dir_name}",
        'Do not edit by hand — re-generate via the Discover → Test Suite tab.',
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "import os",
        "import sys",
        "from pathlib import Path",
        "",
        "import pytest",
        "",
        "# Allow running standalone without installing the package",
        "sys.path.insert(0, str(Path(__file__).parent.parent.parent))",
        "",
        "try:",
        "    import httpx",
        "except ImportError:",
        '    pytest.skip("httpx not installed", allow_module_level=True)',
        "",
        f'BASE_URL = os.environ.get("BASE_URL", {base_url!r})',
        'AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")',
        "",
        "",
        "# ── Fixtures ──────────────────────────────────────────────────────────",
        "",
        "@pytest.fixture(scope='module')",
        "def client():",
        "    headers = {}",
        "    if AUTH_TOKEN:",
        '        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"',
        "    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=15, follow_redirects=True) as c:",
        "        yield c",
        "",
        "",
        "# ── Tests ─────────────────────────────────────────────────────────────",
        "",
        "class TestApiSmoke:",
        f'    """API smoke tests for {base_url or "configured service"} — {len(endpoints)} endpoints."""',
        "",
    ]

    for ep in endpoints:
        method = (ep.get("method") or "GET").upper()
        path = ep.get("path") or "/"
        name = ep.get("name") or path.strip("/").replace("/", "_") or "root"
        safe = _safe_id(name)
        expected = ep.get("checks", {}).get("status", 200)
        ep_type = ep.get("type", "rest")

        if ep_type == "graphql":
            query = ep.get("query", "{ __typename }")
            lines += [
                f"    def test_{safe}(self, client):",
                f'        """GraphQL {name}"""',
                f"        payload = {{'query': {query!r}}}",
                f"        r = client.post({path!r}, json=payload)",
                f"        assert r.status_code == {expected}, f\"Expected {expected}, got {{r.status_code}}\"",
                "",
            ]
        else:
            body = ep.get("body")
            if method in ("POST", "PUT", "PATCH") and body:
                lines += [
                    f"    def test_{safe}(self, client):",
                    f'        """[{method}] {path} — {name}"""',
                    f"        r = client.{method.lower()}({path!r}, json={body!r})",
                    f"        assert r.status_code == {expected}, f\"Expected {expected}, got {{r.status_code}}\"",
                    "",
                ]
            else:
                lines += [
                    f"    def test_{safe}(self, client):",
                    f'        """[{method}] {path} — {name}"""',
                    f"        r = client.{method.lower()}({path!r})",
                    f"        assert r.status_code == {expected}, f\"Expected {expected}, got {{r.status_code}}\"",
                    "",
                ]

    return "\n".join(lines)


def _gen_ui_playwright(base_url: str, pages: list[str], dir_name: str) -> str:
    """Generate a Playwright UI smoke test file."""
    page_list = pages or ["/"]
    lines = [
        '"""Auto-generated Playwright UI smoke tests.',
        f"Base URL: {base_url}",
        f"Generated: {datetime.now(UTC).isoformat()} | Suite: {dir_name}",
        'Do not edit by hand — re-generate via the Discover → Test Suite tab.',
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "import os",
        "import sys",
        "from pathlib import Path",
        "",
        "import pytest",
        "",
        "sys.path.insert(0, str(Path(__file__).parent.parent.parent))",
        "",
        "try:",
        "    from playwright.sync_api import Page, expect",
        "except ImportError:",
        '    pytest.skip("playwright not installed — run: just ui-install", allow_module_level=True)',
        "",
        f'BASE_URL = os.environ.get("BASE_URL", {base_url!r}).rstrip("/")',
        "",
        "",
        "@pytest.fixture(scope='module')",
        "def browser_context_args(browser_context_args):",
        '    return {**browser_context_args, "viewport": {"width": 1280, "height": 900}}',
        "",
        "",
        "class TestUiSmoke:",
        f'    """UI smoke tests for {base_url or "configured service"}."""',
        "",
        "    def test_homepage_loads(self, page: Page):",
        '        """Homepage returns a non-empty page."""',
        "        page.goto(BASE_URL + '/')",
        "        assert page.title() is not None",
        "        assert page.url.startswith(BASE_URL)",
        "",
        "    def test_homepage_no_console_errors(self, page: Page):",
        '        """Homepage has no uncaught JavaScript errors."""',
        "        errors: list[str] = []",
        "        page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)",
        "        page.on('pageerror', lambda err: errors.append(str(err)))",
        "        page.goto(BASE_URL + '/')",
        "        page.wait_for_load_state('networkidle')",
        "        assert errors == [], f'Console errors: {errors}'",
        "",
    ]

    for page_path in page_list[:10]:  # cap at 10 pages to keep file manageable
        if page_path in ("/",):
            continue  # already covered by homepage tests
        safe = _safe_id(page_path)
        lines += [
            f"    def test_page_{safe}_loads(self, page: Page):",
            f'        """Page {page_path!r} loads successfully."""',
            f"        response = page.goto(BASE_URL + {page_path!r})",
            "        assert response is not None",
            f"        assert response.status < 400, f'Page {page_path} returned {{response.status}}'",
            "",
        ]

    return "\n".join(lines)


def _safe_id(text: str) -> str:
    import re

    s = re.sub(r"[^a-zA-Z0-9]", "_", text)
    s = re.sub(r"_+", "_", s).strip("_").lower()
    return s or "endpoint"


# ── Main generation entry point ────────────────────────────────────────────────


def generate_suite(
    config: dict,
    base_url: str = "",
    suites: list[str] | None = None,
    output_root: Path | None = None,
) -> GeneratedSuite:
    """
    Generate test artefacts from an endpoint discovery config.

    Args:
        config:      Endpoint config dict (from discover_url or endpoints.json).
        base_url:    Override base URL (falls back to config["base_url"] or "").
        suites:      Which artefacts to generate: ["api", "ui", "perf", "lighthouse"].
                     Defaults to all four.
        output_root: Parent dir for generated suites (defaults to data/generated-tests/).

    Returns:
        GeneratedSuite dataclass with dir_name and files list.
    """
    suites = suites or ["api", "ui", "perf", "lighthouse"]
    root = output_root or GENERATED_DIR
    dir_name = _make_dir_name()
    suite_path = root / dir_name
    suite_path.mkdir(parents=True, exist_ok=True)

    effective_url = base_url or config.get("base_url", "") or ""
    endpoints: list[dict] = config.get("endpoints", [])
    files: list[str] = []

    # Collect discovered page paths (from web crawler or endpoints)
    page_paths: list[str] = sorted({
        ep.get("path", "/")
        for ep in endpoints
        if ep.get("method", "GET").upper() == "GET" and ep.get("type", "rest") == "rest"
    })

    # ── API smoke tests ───────────────────────────────────────────────────────
    if "api" in suites and endpoints:
        src = _gen_api_smoke(endpoints, effective_url, dir_name)
        out = suite_path / "test_api_smoke.py"
        out.write_text(src)
        files.append(out.name)

    # ── Playwright UI tests ───────────────────────────────────────────────────
    if "ui" in suites and effective_url:
        src = _gen_ui_playwright(effective_url, page_paths, dir_name)
        out = suite_path / "test_ui_playwright.py"
        out.write_text(src)
        files.append(out.name)

    # ── k6 performance config ─────────────────────────────────────────────────
    if "perf" in suites and endpoints:
        perf_config = {
            "service": config.get("service", _safe_id(effective_url)),
            "base_url": effective_url,
            "endpoints": endpoints,
            "_generated": dir_name,
        }
        out = suite_path / "endpoints_perf.json"
        out.write_text(json.dumps(perf_config, indent=2))
        files.append(out.name)

    # ── Lighthouse URL list ───────────────────────────────────────────────────
    if "lighthouse" in suites and effective_url:
        lh_urls = list({effective_url.rstrip("/") + p for p in (page_paths[:5] or ["/"])})
        lh_config = {
            "base_url": effective_url,
            "urls": lh_urls,
            "_generated": dir_name,
        }
        out = suite_path / "lighthouse_urls.json"
        out.write_text(json.dumps(lh_config, indent=2))
        files.append(out.name)

    # ── metadata.json ─────────────────────────────────────────────────────────
    suite = GeneratedSuite(
        dir_name=dir_name,
        base_url=effective_url,
        endpoints_count=len(endpoints),
        suites_generated=suites,
        files=files,
    )
    _save_metadata(suite, output_root)
    return suite


# ── Execution ─────────────────────────────────────────────────────────────────


def _run_pytest(test_path: str, base_url: str, token: str, result_file: Path, extra_args: list[str] | None = None) -> SuiteResult:
    """Run pytest against test_path, save output JSON, return SuiteResult."""
    import re

    cmd = [
        sys.executable, "-m", "pytest",
        test_path,
        "--tb=short", "-q",
        f"--junit-xml={result_file.with_suffix('.xml')}",
        f"--rootdir={REPO_ROOT}",
    ]
    if extra_args:
        cmd += extra_args

    env = dict(os.environ)
    if base_url:
        env["BASE_URL"] = base_url
    if token:
        env["AUTH_TOKEN"] = token
    # Add dashboard to PYTHONPATH so generated tests can import it
    existing_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{REPO_ROOT / 'dashboard'}{os.pathsep}{REPO_ROOT}{os.pathsep}{existing_path}"

    start = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(REPO_ROOT))
        elapsed_ms = (time.monotonic() - start) * 1000
        output = proc.stdout + proc.stderr

        passed = failed = errors = skipped = 0
        for line in output.splitlines():
            p = re.search(r"(\d+) passed", line)
            f = re.search(r"(\d+) failed", line)
            e = re.search(r"(\d+) error", line)
            s = re.search(r"(\d+) skipped", line)
            if p:
                passed = int(p.group(1))
            if f:
                failed = int(f.group(1))
            if e:
                errors = int(e.group(1))
            if s:
                skipped = int(s.group(1))

        sr = SuiteResult(
            suite="api" if "api" in test_path else "ui",
            status="passed" if failed == 0 and errors == 0 else "failed",
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            total=passed + failed + errors + skipped,
            duration_ms=elapsed_ms,
            output=output[-4000:],  # keep last 4K chars
        )
    except Exception as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        sr = SuiteResult(
            suite="api" if "api" in test_path else "ui",
            status="error",
            error_message=str(exc),
            duration_ms=elapsed_ms,
        )

    result_file.write_text(json.dumps(asdict(sr), indent=2))
    return sr


def _run_lighthouse_for_suite(lh_config: dict, result_file: Path) -> SuiteResult:
    """Run Lighthouse against the first URL from the generated config."""
    try:

        from lighthouse_runner import get_result, get_status, run_lighthouse

        urls = lh_config.get("urls", [lh_config.get("base_url", "")])
        if not urls:
            raise ValueError("No URLs configured for Lighthouse")

        url = urls[0]
        run_id = run_lighthouse(url, device="desktop", categories=["performance", "accessibility", "best-practices", "seo"])

        # Wait for completion (up to 90s)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            status = get_status(run_id)
            if status.get("status") in ("done", "error"):
                break
            time.sleep(2)

        result = get_result(run_id)
        has_result = result is not None
        scores = result.get("scores", {}) if result else {}
        summary = f"Performance: {scores.get('performance', '—')} | Accessibility: {scores.get('accessibility', '—')}"

        sr = SuiteResult(
            suite="lighthouse",
            status="passed" if has_result else "error",
            passed=1 if has_result else 0,
            total=1,
            output=summary,
        )
        if result:
            result_file.write_text(json.dumps(result, indent=2))
        else:
            result_file.write_text(json.dumps(asdict(sr), indent=2))
        return sr

    except Exception as exc:
        log.exception("Lighthouse run failed")
        sr = SuiteResult(suite="lighthouse", status="error", error_message=str(exc))
        result_file.write_text(json.dumps(asdict(sr), indent=2))
        return sr


def _run_k6_for_suite(perf_config: dict, result_file: Path) -> SuiteResult:
    """Run a brief k6 smoke run using the generated endpoints config."""
    try:
        import tempfile

        # Write a temp endpoints.json for k6
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(perf_config, f)
            tmp_config = f.name

        k6_bin = str(REPO_ROOT / "bin" / "k6")
        if not Path(k6_bin).exists():
            k6_bin = "k6"

        script = str(REPO_ROOT / "k6" / "scripts" / "smoke.js")
        if not Path(script).exists():
            # Fall back to any k6 script
            scripts = list((REPO_ROOT / "k6" / "scripts").glob("*.js"))
            if scripts:
                script = str(scripts[0])
            else:
                raise FileNotFoundError("No k6 scripts found")

        base_url = perf_config.get("base_url", "")
        env = dict(os.environ)
        env["BASE_URL"] = base_url
        env["ENDPOINTS_JSON"] = tmp_config
        env["VUS"] = "2"
        env["DURATION"] = "15s"

        start = time.monotonic()
        proc = subprocess.run(
            [k6_bin, "run", "--quiet", script],
            capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
        )
        elapsed_ms = (time.monotonic() - start) * 1000
        output = proc.stdout + proc.stderr

        success = proc.returncode == 0
        sr = SuiteResult(
            suite="perf",
            status="passed" if success else "failed",
            passed=1 if success else 0,
            failed=0 if success else 1,
            total=1,
            duration_ms=elapsed_ms,
            output=output[-3000:],
        )
        result_file.write_text(json.dumps(asdict(sr), indent=2))

        import os as _os
        _os.unlink(tmp_config)
        return sr

    except Exception as exc:
        log.exception("k6 run failed")
        sr = SuiteResult(suite="perf", status="error", error_message=str(exc))
        result_file.write_text(json.dumps(asdict(sr), indent=2))
        return sr


def run_suite(
    dir_name: str,
    suites: list[str],
    base_url: str = "",
    token: str = "",
    output_root: Path | None = None,
) -> dict[str, SuiteResult]:
    """
    Execute one or more test suites for a generated test directory.

    Args:
        dir_name:    The generated directory name (e.g. 20260228-175412-a3f2bc).
        suites:      List of suite names to run: "api", "ui", "perf", "lighthouse".
        base_url:    Override BASE_URL (falls back to metadata base_url).
        token:       Bearer token injected as AUTH_TOKEN.
        output_root: Parent dir (defaults to data/generated-tests/).

    Returns:
        dict mapping suite name → SuiteResult.
    """
    suite_path = _suite_dir(dir_name, output_root)
    results_path = _results_dir(dir_name, output_root)
    meta = _load_metadata(dir_name, output_root) or {}
    effective_url = base_url or meta.get("base_url", "")

    results: dict[str, SuiteResult] = {}

    if "api" in suites:
        test_file = suite_path / "test_api_smoke.py"
        if test_file.exists():
            results["api"] = _run_pytest(
                str(test_file), effective_url, token,
                results_path / "api_results.json",
            )
        else:
            results["api"] = SuiteResult(suite="api", status="not_run", error_message="test_api_smoke.py not generated")

    if "ui" in suites:
        test_file = suite_path / "test_ui_playwright.py"
        if test_file.exists():
            results["ui"] = _run_pytest(
                str(test_file), effective_url, token,
                results_path / "ui_results.json",
                extra_args=["--headed=False"],
            )
        else:
            results["ui"] = SuiteResult(suite="ui", status="not_run", error_message="test_ui_playwright.py not generated")

    if "perf" in suites:
        perf_config_file = suite_path / "endpoints_perf.json"
        if perf_config_file.exists():
            perf_config = json.loads(perf_config_file.read_text())
            if effective_url:
                perf_config["base_url"] = effective_url
            results["perf"] = _run_k6_for_suite(perf_config, results_path / "perf_results.json")
        else:
            results["perf"] = SuiteResult(suite="perf", status="not_run", error_message="endpoints_perf.json not generated")

    if "lighthouse" in suites:
        lh_config_file = suite_path / "lighthouse_urls.json"
        if lh_config_file.exists():
            lh_config = json.loads(lh_config_file.read_text())
            if effective_url:
                lh_config["base_url"] = effective_url
            results["lighthouse"] = _run_lighthouse_for_suite(lh_config, results_path / "lighthouse_results.json")
        else:
            results["lighthouse"] = SuiteResult(suite="lighthouse", status="not_run", error_message="lighthouse_urls.json not generated")

    # Write summary
    summary = {
        "dir_name": dir_name,
        "base_url": effective_url,
        "run_at": datetime.now(UTC).isoformat(),
        "suites": {k: asdict(v) for k, v in results.items()},
        "overall_passed": all(v.status == "passed" for v in results.values()),
    }
    (results_path / "summary.json").write_text(json.dumps(summary, indent=2))

    # Update metadata with latest results
    if meta:
        meta["results"] = {k: asdict(v) for k, v in results.items()}
        (suite_path / "metadata.json").write_text(json.dumps(meta, indent=2))

    return results


# ── Listing ───────────────────────────────────────────────────────────────────


def list_generated(output_root: Path | None = None, limit: int = 20) -> list[dict]:
    """Return metadata for the most recently generated test suites."""
    root = output_root or GENERATED_DIR
    dirs = sorted(
        [d for d in root.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    results = []
    for d in dirs[:limit]:
        meta = _load_metadata(d.name, output_root)
        if meta:
            results.append(meta)
    return results


def get_generated(dir_name: str, output_root: Path | None = None) -> dict | None:
    """Return full metadata + file list for a specific generated suite."""
    meta = _load_metadata(dir_name, output_root)
    if meta is None:
        return None
    suite_path = _suite_dir(dir_name, output_root)
    results_path = suite_path / "results"

    # Attach file contents for display
    file_info = []
    for fname in meta.get("files", []):
        fp = suite_path / fname
        file_info.append({
            "name": fname,
            "size": fp.stat().st_size if fp.exists() else 0,
            "exists": fp.exists(),
        })

    # Attach result files if present
    result_files = []
    if results_path.exists():
        for rf in sorted(results_path.glob("*.json")):
            try:
                result_files.append({
                    "name": rf.name,
                    "data": json.loads(rf.read_text()),
                })
            except Exception:
                pass

    return {**meta, "file_info": file_info, "result_files": result_files}
