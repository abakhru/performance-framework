"""
lifecycle.py — Run lifecycle, k6 process management, SLO checks, webhooks,
               badge generation, and plugin hooks for the k6 dashboard.

Public API:
  create_run(profile, base_url, run_id=None) → str
  finalize_run(run_id, started_at, exit_code)
  cleanup_orphans()
  build_k6_cmd(profile, cfg) → list[str]
  wait_for_k6_api(timeout) → bool
  run_k6_supervised(profile, cfg, run_id=None)
  poller_loop(run_id, started_at, stop_event)
  compute_slo_checks(slos, fields) → dict
  make_badge_svg(verdict) → str
  fire_webhooks(event, payload)
  load_plugin_hooks()
  call_hook(name, *args)
"""

import hashlib
import hmac
import importlib.util
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

import influx as _influx
from influx import influx_query, influx_write, lp_str, lp_tag, now_ns
from storage import HOOKS_DIR, REPO_ROOT, load_webhooks

# ── Constants ──────────────────────────────────────────────────────────────────

K6_API_PORT = 6565
K6_API_BASE = f"http://127.0.0.1:{K6_API_PORT}"

# ── Global k6 process state ────────────────────────────────────────────────────
# status: 'idle' | 'starting' | 'running' | 'stopping'

_k6_state: dict = {
    "status": "idle",
    "proc": None,
    "run_id": None,
    "profile": None,
    "base_url": None,
    "started_at": None,
    "stop_event": None,
}
_k6_lock = threading.Lock()

# ── Plugin hooks ───────────────────────────────────────────────────────────────

_plugin_hooks: list = []


def load_plugin_hooks() -> None:
    """Scan HOOKS_DIR for *.py files and load them as plugin modules."""
    global _plugin_hooks
    _plugin_hooks = []
    if not HOOKS_DIR.is_dir():
        return
    for path in sorted(HOOKS_DIR.glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(path.stem, path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _plugin_hooks.append(mod)
            print(f"[hooks] loaded {path.name}", flush=True)
        except Exception as e:
            print(f"[hooks] error loading {path.name}: {e}", flush=True)


def call_hook(name: str, *args) -> None:
    """Call a named function in all loaded plugin hook modules."""
    for mod in _plugin_hooks:
        fn = getattr(mod, name, None)
        if callable(fn):
            try:
                fn(*args)
            except Exception as e:
                print(f"[hooks] {name} in {mod.__name__}: {e}", flush=True)


# ── SLO helpers ────────────────────────────────────────────────────────────────


def compute_slo_checks(slos: dict, fields: dict) -> dict:
    """
    Compare fields against SLO thresholds.
    Returns {metric: {"value": ..., "threshold": ..., "pass": bool}}.
    Higher-is-better metrics: checks_rate, apdex_score.
    """
    higher_is_better = {"checks_rate", "apdex_score"}
    checks = {}
    for metric, threshold in slos.items():
        value = fields.get(metric)
        if value is None:
            continue
        if metric in higher_is_better:
            passed = float(value) >= float(threshold)
        else:
            passed = float(value) <= float(threshold)
        checks[metric] = {
            "value": float(value),
            "threshold": float(threshold),
            "pass": passed,
        }
    return checks


# ── Badge SVG ──────────────────────────────────────────────────────────────────


def make_badge_svg(verdict: str) -> str:
    """Generate an SVG pass/fail badge for the given verdict string."""
    color = "#2da44e" if verdict == "pass" else "#cf222e"
    text = "PERF PASS" if verdict == "pass" else "PERF FAIL"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="90" height="20">'
        f'<rect width="90" height="20" rx="3" fill="{color}"/>'
        f'<text x="45" y="14" font-family="DejaVu Sans,sans-serif" font-size="11"'
        f' fill="white" text-anchor="middle">{text}</text>'
        f"</svg>"
    )


# ── Webhooks ───────────────────────────────────────────────────────────────────


def _send_webhook(hook: dict, payload: dict) -> None:
    url = hook.get("url", "")
    if not url:
        return
    body = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Perf-Event": payload.get("event", ""),
    }
    secret = hook.get("secret", "")
    if secret:
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Perf-Signature"] = f"sha256={sig}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
            print(
                f"[webhook] fired {payload.get('event')} to {url[:50]} → {r.status}",
                flush=True,
            )
    except Exception as e:
        print(f"[webhook] error firing to {url[:50]}: {e}", flush=True)


def fire_webhooks(event: str, payload: dict) -> None:
    """Fire all registered webhooks subscribed to the given event."""
    hooks = load_webhooks()
    for hook in hooks:
        if event not in (hook.get("events") or []):
            continue
        threading.Thread(target=_send_webhook, args=(hook, payload), daemon=True).start()


# ── k6 REST API proxy ──────────────────────────────────────────────────────────


def fetch_k6_json(path: str) -> dict:
    """GET a path from the k6 REST API and return parsed JSON."""
    with urllib.request.urlopen(f"{K6_API_BASE}{path}", timeout=5) as r:
        return json.loads(r.read())


def wait_for_k6_api(timeout: int = 30) -> bool:
    """Poll k6 REST API until it responds; return True if successful."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{K6_API_BASE}/v1/status", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


# ── Op summary writer ──────────────────────────────────────────────────────────


def write_op_summaries(run_id: str, m: dict, op_group: dict) -> None:
    """Write per-operation metric summaries to InfluxDB."""
    ts, lines = now_ns(), []
    for op, grp in op_group.items():
        reqs = int(m.get(f"op_{op}_reqs", {}).get("sample", {}).get("count", 0) or 0)
        if reqs == 0:
            continue
        errs = int(m.get(f"op_{op}_errs", {}).get("sample", {}).get("count", 0) or 0)
        dur = m.get(f"op_{op}_ms", {}).get("sample", {})
        f = [
            f"reqs={reqs}i",
            f"errors={errs}i",
            f"avg_ms={float(dur.get('avg', 0) or 0)}",
            f"min_ms={float(dur.get('min', 0) or 0)}",
            f"max_ms={float(dur.get('max', 0) or 0)}",
            f"p90_ms={float(dur.get('p(90)', 0) or 0)}",
            f"p95_ms={float(dur.get('p(95)', 0) or 0)}",
            f"p99_ms={float(dur.get('p(99)', 0) or 0)}",
        ]
        lines.append(f"k6_op,run_id={lp_tag(run_id)},op_name={lp_tag(op)},op_group={lp_tag(grp)} {','.join(f)} {ts}")
    if lines:
        influx_write(lines)


# ── Poller thread ──────────────────────────────────────────────────────────────


def poller_loop(run_id: str, started_at: datetime, stop_event: threading.Event) -> None:
    """Continuously poll k6 REST API and write snapshots to InfluxDB."""
    prev_reqs: int | None = None
    prev_ts: datetime | None = None

    while not stop_event.is_set():
        try:
            status_data = fetch_k6_json("/v1/status")
            metrics_data = fetch_k6_json("/v1/metrics")
            attrs = status_data["data"]["attributes"]
            m = {e["id"]: e["attributes"] for e in metrics_data.get("data", [])}

            vus = attrs.get("vus", 0) or 0
            s_reqs = m.get("http_reqs", {}).get("sample", {})
            s_dur = m.get("http_req_duration", {}).get("sample", {})
            total_reqs = int(s_reqs.get("count", 0) or 0)
            p50_ms = float(s_dur.get("med", 0) or 0)
            p75_ms = float(s_dur.get("p(75)", 0) or 0)
            p95_ms = float(s_dur.get("p(95)", 0) or 0)
            p99_ms = float(s_dur.get("p(99)", 0) or 0)
            avg_ms = float(s_dur.get("avg", 0) or 0)

            cur_now = datetime.now(UTC)
            elapsed_s = int((cur_now - started_at).total_seconds())
            ts_ns = int(cur_now.timestamp() * 1e9)

            rps = 0.0
            if prev_reqs is not None and prev_ts is not None:
                dt = (cur_now - prev_ts).total_seconds()
                rps = max(0.0, (total_reqs - prev_reqs) / dt) if dt >= 0.5 else 0.0
            prev_reqs, prev_ts = total_reqs, cur_now

            influx_write(
                f"k6_snapshot,run_id={lp_tag(run_id)} "
                f"vus={vus}i,rps={rps},"
                f"p50_ms={p50_ms},p75_ms={p75_ms},p95_ms={p95_ms},p99_ms={p99_ms},"
                f"avg_ms={avg_ms},total_reqs={total_reqs}i,elapsed_s={elapsed_s}i "
                f"{ts_ns}"
            )
        except Exception as e:
            print(f"[poller] error: {e}", flush=True)
        stop_event.wait(5.0)


# ── Run lifecycle ──────────────────────────────────────────────────────────────


def create_run(profile: str, base_url: str, run_id: str | None = None) -> str:
    """Write the run_start event to InfluxDB and return the run_id."""
    run_id = run_id or str(uuid.uuid4())
    influx_write(
        f"k6_run_start,run_id={lp_tag(run_id)},profile={lp_tag(profile)} base_url={lp_str(base_url)} {now_ns()}"
    )
    return run_id


def finalize_run(
    run_id: str,
    started_at: datetime,
    exit_code: int,
    endpoint_config: dict,
    op_group: dict,
) -> None:
    """
    Collect final metrics from k6 REST API, write k6_run_final / k6_run_slo
    to InfluxDB, fire webhooks, and call plugin hooks.
    """
    from storage import coerce_int as _int

    status = "finished" if exit_code == 0 else ("interrupted" if exit_code < 0 else "failed")
    fields: dict = {}

    try:
        metrics_data = fetch_k6_json("/v1/metrics")
        status_data = fetch_k6_json("/v1/status")
        m = {e["id"]: e["attributes"] for e in metrics_data.get("data", [])}

        def s(key):
            return m.get(key, {}).get("sample", {})

        dur = s("http_req_duration")
        reqs = s("http_reqs")
        fail = s("http_req_failed")
        wait = s("http_req_waiting")
        chk = s("checks")
        dsent = s("data_sent")
        drecv = s("data_received")
        vus_max = _int(status_data.get("data", {}).get("attributes", {}).get("vus-max")) or 0

        apdex_s = int(s("apdex_satisfied").get("count", 0) or 0)
        apdex_t = int(s("apdex_tolerating").get("count", 0) or 0)
        apdex_f = int(s("apdex_frustrated").get("count", 0) or 0)
        apdex_n = apdex_s + apdex_t + apdex_f
        apdex_score = (apdex_s + apdex_t * 0.5) / apdex_n if apdex_n > 0 else None

        fields = {
            "total_reqs": int(reqs.get("count", 0) or 0),
            "error_rate": float(fail.get("rate", 0) or 0),
            "p50_ms": float(dur.get("med", 0) or 0),
            "p75_ms": float(dur.get("p(75)", 0) or 0),
            "p90_ms": float(dur.get("p(90)", 0) or 0),
            "p95_ms": float(dur.get("p(95)", 0) or 0),
            "p99_ms": float(dur.get("p(99)", 0) or 0),
            "avg_ms": float(dur.get("avg", 0) or 0),
            "min_ms": float(dur.get("min", 0) or 0),
            "med_ms": float(dur.get("med", 0) or 0),
            "ttfb_avg": float(wait.get("avg", 0) or 0),
            "checks_rate": float(chk.get("rate", 0) or 0),
            "data_sent": float(dsent.get("count", 0) or 0),
            "data_received": float(drecv.get("count", 0) or 0),
            "vus_max": vus_max,
            "s2xx": int(s("http_status_2xx").get("count", 0) or 0),
            "s3xx": int(s("http_status_3xx").get("count", 0) or 0),
            "s4xx": int(s("http_status_4xx").get("count", 0) or 0),
            "s5xx": int(s("http_status_5xx").get("count", 0) or 0),
            "apdex_score": apdex_score,
            "conn_reuse_rate": float(s("connection_reused").get("rate", 0) or 0),
            "lat_b50": int(s("lat_bucket_50").get("count", 0) or 0),
            "lat_b200": int(s("lat_bucket_200").get("count", 0) or 0),
            "lat_b500": int(s("lat_bucket_500").get("count", 0) or 0),
            "lat_b1000": int(s("lat_bucket_1000").get("count", 0) or 0),
            "lat_b2000": int(s("lat_bucket_2000").get("count", 0) or 0),
            "lat_b5000": int(s("lat_bucket_5000").get("count", 0) or 0),
            "lat_binf": int(s("lat_bucket_inf").get("count", 0) or 0),
        }
        write_op_summaries(run_id, m, op_group)
    except Exception as e:
        print(f"[dashboard] finalize metrics error: {e}", flush=True)

    cur_now = datetime.now(UTC)
    duration = int((cur_now - started_at).total_seconds())
    parts = [f"status={lp_str(status)}", f"duration_s={duration}i"]
    for k, v in fields.items():
        if v is None:
            continue
        parts.append(f"{k}={v}i" if isinstance(v, int) else f"{k}={v}")

    influx_write(f"k6_run_final,run_id={lp_tag(run_id)} {','.join(parts)} {now_ns()}")

    # Write SLO verdict
    slos = endpoint_config.get("slos", {})
    if slos and fields:
        slo_checks = compute_slo_checks(slos, fields)
        if slo_checks:
            slo_verdict = "pass" if all(c["pass"] for c in slo_checks.values()) else "fail"
            slo_parts = [f"verdict={lp_str(slo_verdict)}"]
            for metric, chk in slo_checks.items():
                slo_parts.append(f"{metric}_pass={1 if chk['pass'] else 0}i")
            influx_write(f"k6_run_slo,run_id={lp_tag(run_id)} {','.join(slo_parts)} {now_ns()}")
            if slo_verdict == "fail":
                fire_webhooks(
                    "slo.breached",
                    {
                        "event": "slo.breached",
                        "run_id": run_id,
                        "verdict": "fail",
                        "checks": {metric_name: c["pass"] for metric_name, c in slo_checks.items()},
                    },
                )

    # Fire run finished/failed webhook
    with _k6_lock:
        profile = _k6_state.get("profile", "")
        base_url = _k6_state.get("base_url", "")

    fire_webhooks(
        "run.finished" if exit_code == 0 else "run.failed",
        {
            "event": "run.finished" if exit_code == 0 else "run.failed",
            "run_id": run_id,
            "profile": profile,
            "status": status,
            "base_url": base_url,
            "duration_s": duration,
            **{
                k: v
                for k, v in fields.items()
                if k in ("total_reqs", "error_rate", "p95_ms", "apdex_score", "checks_rate")
            },
        },
    )

    call_hook("on_run_finish", {"run_id": run_id, "status": status, "duration_s": duration, **fields})
    total = fields.get("total_reqs", "?")
    print(f"[dashboard] run {run_id[:8]}… → {status} ({duration}s, {total} reqs)", flush=True)


def cleanup_orphans() -> None:
    """Mark any started-but-not-finalized runs as 'interrupted' in InfluxDB."""
    start_rows = influx_query(f'''
from(bucket: "{_influx.INFLUX_BUCKET}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "k6_run_start" and r._field == "base_url")
  |> keep(columns: ["run_id", "_value"])
''')
    started_ids = {r.get("run_id", "") for r in start_rows if r.get("run_id")}

    final_rows = influx_query(f'''
from(bucket: "{_influx.INFLUX_BUCKET}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "k6_run_final" and r._field == "status")
  |> keep(columns: ["run_id", "_value"])
''')
    finalized_ids = {r.get("run_id", "") for r in final_rows if r.get("run_id")}

    orphans = started_ids - finalized_ids
    if not orphans:
        return
    print(f"[dashboard] cleaning up {len(orphans)} orphaned run(s)", flush=True)
    ts = now_ns()
    influx_write([f'k6_run_final,run_id={lp_tag(rid)} status="interrupted",duration_s=0i {ts}' for rid in orphans])


# ── k6 command builder ─────────────────────────────────────────────────────────


def build_k6_cmd(profile: str, cfg: dict) -> list[str]:
    """Assemble the k6 CLI command list for the given profile and config."""
    k6_bin = str(REPO_ROOT / "bin" / "k6")
    if not Path(k6_bin).exists():
        k6_bin = "k6"

    def _env(key: str, val: str) -> list[str]:
        return ["--env", f"{key}={val}"] if val else []

    cmd = [
        k6_bin,
        "run",
        "--address",
        f"127.0.0.1:{K6_API_PORT}",
        "--env",
        f"BASE_URL={cfg.get('base_url', '')}",
        "--env",
        f"LOAD_PROFILE={profile}",
        "--env",
        f"VUS={cfg.get('vus', '10')}",
        "--env",
        f"DURATION={cfg.get('duration', '60s')}",
        "--env",
        f"RAMP_DURATION={cfg.get('ramp_duration', '30s')}",
    ]
    cmd += _env("AUTH_TOKEN", cfg.get("auth_token", ""))
    cmd += _env("AUTH_BASIC_USER", cfg.get("auth_basic_user", ""))
    cmd += _env("AUTH_BASIC_PASS", cfg.get("auth_basic_pass", ""))
    cmd += _env("AUTH_API_KEY", cfg.get("auth_api_key", ""))
    cmd += _env("AUTH_API_KEY_HEADER", cfg.get("auth_api_key_header", ""))
    cmd += _env("AUTH_HOST", cfg.get("auth_host", ""))
    cmd += _env("AUTH_REALM", cfg.get("auth_realm", ""))
    cmd += _env("AUTH_CLIENT_ID", cfg.get("auth_client_id", ""))
    cmd += _env("AUTH_CLIENT_SECRET", cfg.get("auth_client_secret", ""))

    if k6_bin.endswith("bin/k6") and _influx.INFLUX_URL:
        cmd += ["--out", f"xk6-influxdb={_influx.INFLUX_URL}"]

    cmd.append(str(REPO_ROOT / "k6" / "main.js"))
    return cmd


# ── Supervised run thread ──────────────────────────────────────────────────────


def run_k6_supervised(
    profile: str,
    cfg: dict,
    run_id: str | None = None,
    endpoint_config_ref: list | None = None,
    op_group_ref: list | None = None,
) -> None:
    """
    Start k6, poll metrics, finalize on exit — intended for a background thread.

    endpoint_config_ref and op_group_ref are single-element lists used as
    mutable references so this thread sees the live values from server.py.
    """
    base_url = cfg.get("base_url", "")
    run_id = create_run(profile, base_url, run_id=run_id)
    started_at = datetime.now(UTC)
    stop_event = threading.Event()

    call_hook("on_run_start", {"profile": profile, "base_url": base_url, "run_id": run_id, **cfg})

    proc = subprocess.Popen(
        build_k6_cmd(profile, cfg),
        cwd=str(REPO_ROOT),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    with _k6_lock:
        _k6_state.update(
            {
                "proc": proc,
                "run_id": run_id,
                "profile": profile,
                "base_url": base_url,
                "started_at": started_at,
                "stop_event": stop_event,
                "status": "starting",
            }
        )

    print(f"[dashboard] Run {run_id[:8]}… starting ({profile})", flush=True)

    if wait_for_k6_api(30):
        with _k6_lock:
            _k6_state["status"] = "running"
        poller = threading.Thread(
            target=poller_loop,
            args=(run_id, started_at, stop_event),
            daemon=True,
        )
        poller.start()
    else:
        print("[dashboard] WARNING: k6 REST API did not start", flush=True)

    exit_code = proc.wait()
    stop_event.set()

    ep_cfg = endpoint_config_ref[0] if endpoint_config_ref else {}
    og = op_group_ref[0] if op_group_ref else {}
    finalize_run(run_id, started_at, exit_code, ep_cfg, og)

    with _k6_lock:
        _k6_state.update(
            {
                "proc": None,
                "run_id": None,
                "profile": None,
                "base_url": None,
                "started_at": None,
                "stop_event": None,
                "status": "idle",
            }
        )
