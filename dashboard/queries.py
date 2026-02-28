"""InfluxDB query helpers — all pure functions grouped in RunQueries."""

from influx import INFLUX_BUCKET, influx_query
from lifecycle import compute_slo_checks
from storage import coerce_float as _float
from storage import coerce_int as _int

_DIFF_KEYS = [
    "total_reqs",
    "error_rate",
    "p50_ms",
    "p75_ms",
    "p90_ms",
    "p95_ms",
    "p99_ms",
    "avg_ms",
    "checks_rate",
    "apdex_score",
    "duration_s",
    "vus_max",
]


class RunQueries:
    @staticmethod
    def build_runs() -> dict:
        start_rows = influx_query(f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "k6_run_start")
  |> pivot(rowKey:["_time","run_id","profile"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time","run_id","profile","base_url"])
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 200)
""")
        starts: dict[str, dict] = {}
        for r in start_rows:
            rid = r.get("run_id", "")
            if rid and rid not in starts:
                starts[rid] = {
                    "run_id": rid,
                    "profile": r.get("profile", ""),
                    "base_url": r.get("base_url", ""),
                    "started_at": r.get("_time", ""),
                    "status": "running",
                }

        final_rows = influx_query(f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "k6_run_final")
  |> pivot(rowKey:["_time","run_id"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["run_id","status","total_reqs","error_rate",
                    "p50_ms","p75_ms","p90_ms","p95_ms","p99_ms",
                    "avg_ms","min_ms","med_ms","ttfb_avg","checks_rate",
                    "data_sent","data_received","vus_max","duration_s",
                    "apdex_score","s2xx","s3xx","s4xx","s5xx","conn_reuse_rate",
                    "lat_b50","lat_b200","lat_b500","lat_b1000",
                    "lat_b2000","lat_b5000","lat_binf"])
""")
        finals: dict[str, dict] = {r["run_id"]: r for r in final_rows if r.get("run_id")}

        _int_fields = [
            "total_reqs",
            "vus_max",
            "duration_s",
            "s2xx",
            "s3xx",
            "s4xx",
            "s5xx",
            "lat_b50",
            "lat_b200",
            "lat_b500",
            "lat_b1000",
            "lat_b2000",
            "lat_b5000",
            "lat_binf",
        ]
        _float_fields = [
            "error_rate",
            "p50_ms",
            "p75_ms",
            "p90_ms",
            "p95_ms",
            "p99_ms",
            "avg_ms",
            "min_ms",
            "med_ms",
            "ttfb_avg",
            "checks_rate",
            "data_sent",
            "data_received",
            "apdex_score",
            "conn_reuse_rate",
        ]

        runs = []
        for rid, start in starts.items():
            row = dict(start)
            if rid in finals:
                f = finals[rid]
                row["status"] = f.get("status", "finished")
                for key in _int_fields:
                    row[key] = _int(f.get(key))
                for key in _float_fields:
                    row[key] = _float(f.get(key))
            runs.append(row)

        runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
        return {"runs": runs}

    @staticmethod
    def fetch_snapshots(run_id: str) -> dict:
        rows = influx_query(f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "k6_snapshot" and r.run_id == "{run_id}")
  |> pivot(rowKey:["_time","run_id"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time","elapsed_s","vus","rps",
                    "p50_ms","p75_ms","p95_ms","p99_ms","avg_ms","total_reqs"])
  |> sort(columns: ["_time"])
""")
        return {
            "run_id": run_id,
            "snapshots": [
                {
                    "ts": r.get("_time", ""),
                    "elapsed_s": _int(r.get("elapsed_s")) or 0,
                    "vus": _int(r.get("vus")) or 0,
                    "rps": _float(r.get("rps")) or 0.0,
                    "p50_ms": _float(r.get("p50_ms")) or 0.0,
                    "p75_ms": _float(r.get("p75_ms")) or 0.0,
                    "p95_ms": _float(r.get("p95_ms")) or 0.0,
                    "p99_ms": _float(r.get("p99_ms")) or 0.0,
                    "avg_ms": _float(r.get("avg_ms")) or 0.0,
                    "total_reqs": _int(r.get("total_reqs")) or 0,
                }
                for r in rows
            ],
        }

    @staticmethod
    def fetch_ops(run_id: str) -> dict:
        rows = influx_query(f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -30d)
  |> filter(fn: (r) => r._measurement == "k6_op" and r.run_id == "{run_id}")
  |> pivot(rowKey:["_time","run_id","op_name","op_group"],
           columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["op_name","op_group","reqs","errors",
                    "avg_ms","min_ms","max_ms","p90_ms","p95_ms","p99_ms"])
  |> sort(columns: ["op_group","op_name"])
""")
        return {
            "run_id": run_id,
            "ops": [
                {
                    "op_name": r.get("op_name", ""),
                    "op_group": r.get("op_group", ""),
                    "reqs": _int(r.get("reqs")) or 0,
                    "errors": _int(r.get("errors")) or 0,
                    "avg_ms": _float(r.get("avg_ms")),
                    "min_ms": _float(r.get("min_ms")),
                    "max_ms": _float(r.get("max_ms")),
                    "p90_ms": _float(r.get("p90_ms")),
                    "p95_ms": _float(r.get("p95_ms")),
                    "p99_ms": _float(r.get("p99_ms")),
                }
                for r in rows
            ],
        }

    @staticmethod
    def fetch_slo(run_id: str, endpoint_config: dict) -> dict:
        slo_rows = influx_query(f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -90d)
  |> filter(fn: (r) => r._measurement == "k6_run_slo" and r.run_id == "{run_id}")
  |> pivot(rowKey:["_time","run_id"], columnKey: ["_field"], valueColumn: "_value")
""")
        if slo_rows:
            row = slo_rows[0]
            slos = endpoint_config.get("slos", {})
            checks = {
                metric: {
                    "threshold": float(slos[metric]),
                    "pass": bool(int(float(row[f"{metric}_pass"]))),
                }
                for metric in slos
                if row.get(f"{metric}_pass") is not None
            }
            return {"verdict": row.get("verdict", "unknown"), "checks": checks}

        final_rows = influx_query(f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -90d)
  |> filter(fn: (r) => r._measurement == "k6_run_final" and r.run_id == "{run_id}")
  |> pivot(rowKey:["_time","run_id"], columnKey: ["_field"], valueColumn: "_value")
""")
        if not final_rows:
            return {"verdict": "unknown", "checks": {}}

        row = final_rows[0]
        fields = {
            k: v
            for k, v in {
                "p95_ms": _float(row.get("p95_ms")),
                "p99_ms": _float(row.get("p99_ms")),
                "error_rate": _float(row.get("error_rate")),
                "checks_rate": _float(row.get("checks_rate")),
                "apdex_score": _float(row.get("apdex_score")),
            }.items()
            if v is not None
        }
        slos = endpoint_config.get("slos", {})
        if not slos:
            return {"verdict": "unknown", "checks": {}}
        slo_checks = compute_slo_checks(slos, fields)
        if not slo_checks:
            return {"verdict": "unknown", "checks": {}}
        verdict = "pass" if all(c["pass"] for c in slo_checks.values()) else "fail"
        return {"verdict": verdict, "checks": slo_checks}

    @staticmethod
    def compute_diff(id_a: str, id_b: str) -> dict:
        rows = influx_query(f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -90d)
  |> filter(fn: (r) => r._measurement == "k6_run_final" and
            (r.run_id == "{id_a}" or r.run_id == "{id_b}"))
  |> pivot(rowKey:["_time","run_id"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["run_id","total_reqs","error_rate","p50_ms","p75_ms",
                    "p90_ms","p95_ms","p99_ms","avg_ms","checks_rate",
                    "apdex_score","duration_s","vus_max"])
""")
        run_a: dict = {}
        run_b: dict = {}
        for row in rows:
            rid = row.get("run_id", "")
            if rid == id_a:
                run_a = row
            elif rid == id_b:
                run_b = row

        metrics_a = {k: _float(run_a.get(k)) for k in _DIFF_KEYS}
        metrics_b = {k: _float(run_b.get(k)) for k in _DIFF_KEYS}

        diff = {}
        for k in _DIFF_KEYS:
            a, b = metrics_a.get(k), metrics_b.get(k)
            if a is None or b is None:
                continue
            delta = b - a
            pct = (delta / a * 100) if a != 0 else None
            diff[k] = {"a": a, "b": b, "delta": delta, "pct": round(pct, 2) if pct is not None else None}

        return {
            "run_a": {"run_id": id_a, **{k: v for k, v in metrics_a.items() if v is not None}},
            "run_b": {"run_id": id_b, **{k: v for k, v in metrics_b.items() if v is not None}},
            "diff": diff,
        }

    @staticmethod
    def fetch_op_trend(op_name: str, n: int) -> dict:
        rows = influx_query(f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -90d)
  |> filter(fn: (r) => r._measurement == "k6_op" and r.op_name == "{op_name}")
  |> pivot(rowKey:["_time","run_id","op_name"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time","run_id","p95_ms","avg_ms","errors","reqs"])
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: {n})
  |> sort(columns: ["_time"])
""")
        return {
            "op_name": op_name,
            "trend": [
                {
                    "run_id": r.get("run_id", ""),
                    "ts": r.get("_time", ""),
                    "p95_ms": _float(r.get("p95_ms")),
                    "avg_ms": _float(r.get("avg_ms")),
                    "reqs": _int(r.get("reqs")),
                    "errors": _int(r.get("errors")),
                }
                for r in rows
            ],
        }

    @staticmethod
    def fetch_heatmap(metric: str, days: int) -> dict:
        rows = influx_query(f"""
from(bucket: "{INFLUX_BUCKET}")
  |> range(start: -{days}d)
  |> filter(fn: (r) => r._measurement == "k6_run_final" and r._field == "{metric}")
  |> keep(columns: ["_time", "_value", "run_id"])
  |> sort(columns: ["_time"])
""")
        by_date: dict[str, list] = {}
        for r in rows:
            date = (r.get("_time") or "")[:10]
            v = _float(r.get("_value"))
            if date and v is not None:
                by_date.setdefault(date, []).append(v)

        return {
            "metric": metric,
            "days": days,
            "data": [
                {
                    "date": date,
                    "value": sum(vals) / len(vals),
                    "min": min(vals),
                    "max": max(vals),
                    "run_count": len(vals),
                }
                for date, vals in sorted(by_date.items())
            ],
        }
