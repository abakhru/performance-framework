"""Self-contained HTML report builder for a single k6 run."""

import json

from core.influx import now as _now


def build_html_report(run_id: str, run_meta: dict, snapshots: list, ops: list) -> str:
    run_json = json.dumps(run_meta)
    snaps_json = json.dumps(snapshots)
    ops_json = json.dumps(ops)
    generated_at = _now()

    sparkline_svg = _build_sparkline(snapshots)
    cards_html = _build_cards(run_meta)
    ops_rows = _build_ops_rows(ops)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Performance Report — {run_id[:8]}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 0; padding: 24px; background: #0f1117; color: #e2e8f0; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 4px; }}
  .meta {{ color: #64748b; font-size: 0.875rem; margin-bottom: 24px; }}
  .cards {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 32px; }}
  .card {{ background: #1a1d27; border: 1px solid #2d3148; border-radius: 8px; padding: 16px 24px; min-width: 140px; }}
  .card-label {{ font-size: 0.75rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }}
  .card-value {{ font-size: 1.5rem; font-weight: 700; margin-top: 4px; color: #6c63ff; }}
  .section {{ background: #1a1d27; border: 1px solid #2d3148; border-radius: 8px; padding: 24px; margin-bottom: 24px; }}
  h2 {{ font-size: 1rem; margin: 0 0 16px 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
  th {{ text-align: left; padding: 8px 12px; background: #242736; border-bottom: 1px solid #2d3148; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #1a1d27; }}
  .footer {{ color: #64748b; font-size: 0.75rem; margin-top: 24px; }}
</style>
</head>
<body>
<h1>Performance Report</h1>
<div class="meta">
  Run ID: <code>{run_id}</code> &nbsp;|&nbsp;
  Profile: {run_meta.get("profile", "N/A")} &nbsp;|&nbsp;
  Status: {run_meta.get("status", "N/A")} &nbsp;|&nbsp;
  Started: {run_meta.get("started_at", "N/A")}
</div>
<div class="cards">{cards_html}</div>
<div class="section">
  <h2>P95 Latency Over Time</h2>
  {sparkline_svg}
</div>
<div class="section">
  <h2>Per-Operation Metrics</h2>
  <table>
    <thead><tr>
      <th>Operation</th><th>Group</th><th>Requests</th>
      <th>Errors</th><th>Avg (ms)</th><th>P95 (ms)</th>
    </tr></thead>
    <tbody>{ops_rows}</tbody>
  </table>
</div>
<div class="footer">Generated at {generated_at} &nbsp;|&nbsp; run_id: {run_id}</div>
<script>
const RUN = {run_json};
const SNAPSHOTS = {snaps_json};
const OPS = {ops_json};
</script>
</body>
</html>"""


def _build_sparkline(snapshots: list) -> str:
    p95_vals = [s.get("p95_ms", 0) for s in snapshots if s.get("p95_ms") is not None]
    if len(p95_vals) <= 1:
        return "<p style='color:#888'>Not enough snapshot data for sparkline.</p>"

    p95_max = max(p95_vals) or 1
    p95_min = min(p95_vals)
    width, height = 400, 60
    pts = [
        f"{i / (len(p95_vals) - 1) * width:.1f},{height - ((v - p95_min) / (p95_max - p95_min + 0.001)) * height:.1f}"
        for i, v in enumerate(p95_vals)
    ]
    path = "M " + " L ".join(pts)
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'style="display:block;margin:auto">'
        f'<path d="{path}" fill="none" stroke="#6c63ff" stroke-width="2"/>'
        f"</svg>"
    )


def _card(label: str, value, fmt=str) -> str:
    val_str = fmt(value) if value is not None else "N/A"
    return f'<div class="card"><div class="card-label">{label}</div><div class="card-value">{val_str}</div></div>'


def _build_cards(run_meta: dict) -> str:
    return (
        _card("Total Requests", run_meta.get("total_reqs"), lambda v: f"{v:,}")
        + _card("P95 Latency", run_meta.get("p95_ms"), lambda v: f"{v:.1f} ms")
        + _card("Error Rate", run_meta.get("error_rate"), lambda v: f"{v * 100:.2f}%")
        + _card("Apdex Score", run_meta.get("apdex_score"), lambda v: f"{v:.3f}")
        + _card("Duration", run_meta.get("duration_s"), lambda v: f"{v}s")
    )


def _build_ops_rows(ops: list) -> str:
    rows = ""
    for op in ops:
        p95 = op.get("p95_ms")
        avg = op.get("avg_ms")
        rows += (
            f"<tr>"
            f"<td>{op.get('op_name', '')}</td>"
            f"<td>{op.get('op_group', '')}</td>"
            f"<td>{op.get('reqs', 0)}</td>"
            f"<td>{op.get('errors', 0)}</td>"
            f"<td>{'N/A' if avg is None else f'{avg:.1f}'}</td>"
            f"<td>{'N/A' if p95 is None else f'{p95:.1f}'}</td>"
            f"</tr>"
        )
    return rows
