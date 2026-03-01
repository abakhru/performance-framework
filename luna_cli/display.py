"""Rich display helpers — panels, tables, spinners, live metrics."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.table import Table
from rich.theme import Theme

# ── Luna colour palette ──────────────────────────────────────────────────────
THEME = Theme(
    {
        "luna.gold": "#C8A84B",
        "luna.gold2": "#E4C86A",
        "luna.gold3": "#8C6E28",
        "luna.silver": "#A4B4CC",
        "luna.muted": "#5A6278",
        "luna.surface": "#0C1020",
        "luna.ok": "#3d9e5a",
        "luna.warn": "#d4a017",
        "luna.err": "#e05555",
        "luna.blue": "#4D8FFF",
        "luna.prompt": "bold #C8A84B",
        "luna.cmd": "bold white",
        "luna.dim": "dim #5A6278",
    }
)

console = Console(theme=THEME, highlight=False)
err_console = Console(theme=THEME, stderr=True)

# ── Branding ─────────────────────────────────────────────────────────────────

BANNER = """[luna.gold]
  ██╗     ██╗   ██╗███╗   ██╗ █████╗
  ██║     ██║   ██║████╗  ██║██╔══██╗
  ██║     ██║   ██║██╔██╗ ██║███████║
  ██║     ██║   ██║██║╚██╗██║██╔══██║
  ███████╗╚██████╔╝██║ ╚████║██║  ██║
  ╚══════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝[/luna.gold]"""

TAGLINE = "[luna.muted]  Testing as a Service · for teams and agents[/luna.muted]"

PROMPT_MARKER = "◆"
PROMPT_SUFFIX = " ❯ "


def print_banner(dashboard_url: str = "http://localhost:5656") -> None:
    """Print the Luna welcome banner."""
    console.print(BANNER)
    console.print(TAGLINE)
    console.print()
    console.print(
        f"  [luna.muted]Dashboard[/luna.muted]  [luna.silver]{dashboard_url}[/luna.silver]"
        f"   [luna.muted]Docs[/luna.muted]  [luna.silver]{dashboard_url}/docs[/luna.silver]"
        f"   [luna.muted]MCP[/luna.muted]   [luna.silver]{dashboard_url}/mcp[/luna.silver]"
    )
    console.print()


def print_help() -> None:
    """Print REPL help."""
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="luna.gold", no_wrap=True)
    table.add_column(style="luna.silver")

    commands = [
        ("test <url>", "Discover + smoke test a service (fastest path)"),
        ("test <url> --profile ramp --vus 20 --duration 120", "Full load test"),
        ("discover <url>", "Probe a URL and list discovered endpoints"),
        ("run <profile>", "Launch k6 with the active endpoint config"),
        ("status", "Show current k6 run status"),
        ("watch", "Stream live metrics until run completes"),
        ("history", "Recent runs with SLO verdicts"),
        ("health", "Check Luna, k6, and InfluxDB health"),
        ("config", "Show active endpoint config"),
        ("", ""),
        ("/help", "Show this help"),
        ("/quit  or  Ctrl-D", "Exit the REPL"),
        ("/clear", "Clear the screen"),
    ]
    for cmd, desc in commands:
        table.add_row(cmd, desc)

    console.print(Panel(table, title="[luna.gold]Commands[/luna.gold]", border_style="luna.gold3", padding=(1, 2)))


# ── Status / health ───────────────────────────────────────────────────────────


def print_health(data: dict) -> None:
    status = data.get("status", "unknown")
    color = "luna.ok" if status == "ok" else "luna.err"
    icon = "✓" if status == "ok" else "✗"

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="luna.muted", no_wrap=True)
    table.add_column()

    components = data.get("components", {})
    for name, val in components.items():
        ok = val == "ok"
        table.add_row(
            name,
            f"[{'luna.ok' if ok else 'luna.err'}]{'●' if ok else '○'}  {val}[/{'luna.ok' if ok else 'luna.err'}]",
        )

    run = data.get("run", {})
    if run.get("status"):
        table.add_row("run", f"[luna.silver]{run['status']}[/luna.silver]")

    console.print(
        Panel(
            table,
            title=f"[{color}]{icon} Luna Health — {status.upper()}[/{color}]",
            border_style=color,
            padding=(1, 2),
        )
    )


# ── Run results ───────────────────────────────────────────────────────────────


def print_run_result(result: Any, verbose: bool = False) -> None:
    """Print a RunResult (or dict) in a rich panel."""
    # Handle both RunResult dataclass and plain dict
    if hasattr(result, "__dataclass_fields__"):
        success = result.success
        profile = result.profile
        elapsed = result.elapsed_s
        endpoint_count = result.endpoint_count
        source = result.source
        status = result.status
        error = result.error
        endpoints = result.endpoints or []
    else:
        success = result.get("success", False)
        profile = result.get("profile", "?")
        elapsed = result.get("elapsed_s", 0)
        endpoint_count = result.get("endpoint_count", 0)
        source = result.get("source", "?")
        status = result.get("status", "?")
        error = result.get("error", "")
        endpoints = result.get("endpoints", [])

    color = "luna.ok" if success else "luna.err"
    icon = "✓" if success else "✗"
    label = "PASSED" if success else "FAILED"

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="luna.muted", no_wrap=True, width=18)
    table.add_column()
    table.add_row("Status", f"[{color}]{icon}  {label}[/{color}]")
    table.add_row("Profile", f"[luna.silver]{profile}[/luna.silver]")
    table.add_row(
        "Endpoints", f"[luna.gold]{endpoint_count}[/luna.gold] discovered via [luna.silver]{source}[/luna.silver]"
    )
    table.add_row("Duration", f"[luna.silver]{elapsed:.0f}s[/luna.silver]")
    table.add_row("Run status", f"[luna.silver]{status}[/luna.silver]")
    if error:
        table.add_row("Error", f"[luna.err]{error}[/luna.err]")

    console.print(Panel(table, title=f"[{color}]Run Results[/{color}]", border_style=color, padding=(1, 2)))

    if verbose and endpoints:
        ep_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
        ep_table.add_column("Method", style="luna.gold", no_wrap=True, width=8)
        ep_table.add_column("Path", style="luna.silver")
        ep_table.add_column("Name", style="luna.muted")
        for ep in endpoints[:20]:
            ep_table.add_row(
                ep.get("method", "GET"),
                ep.get("path", "/"),
                ep.get("name", ""),
            )
        console.print(Panel(ep_table, title="[luna.muted]Endpoints tested[/luna.muted]", border_style="luna.gold3"))


# ── History ───────────────────────────────────────────────────────────────────


def print_history(runs: list) -> None:
    if not runs:
        console.print("[luna.muted]  No runs yet. Try: test https://your-api.com[/luna.muted]")
        return

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="luna.gold3",
        border_style="luna.gold4 on default",
        padding=(0, 1),
    )
    table.add_column("#", style="luna.muted", width=4)
    table.add_column("Profile", style="luna.silver", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("URL", style="luna.silver", max_width=40)
    table.add_column("p95 ms", justify="right", style="luna.gold")
    table.add_column("Err%", justify="right")
    table.add_column("Apdex", justify="right")
    table.add_column("SLO", no_wrap=True)

    for i, run in enumerate(runs, 1):
        slo_pass = run.get("slo_pass") or run.get("slo_verdict") == "pass"
        slo_icon = "[luna.ok]✓ PASS[/luna.ok]" if slo_pass else "[luna.err]✗ FAIL[/luna.err]"
        err_rate = run.get("error_rate") or run.get("checks_rate", 0)
        err_pct = f"{(err_rate or 0) * 100:.1f}%"
        err_style = "luna.err" if (err_rate or 0) > 0.01 else "luna.silver"
        p95 = run.get("p95_ms") or run.get("avg_ms") or 0
        p95_style = "luna.err" if (p95 or 0) > 500 else "luna.ok"
        apdex = run.get("apdex_score", "—")

        table.add_row(
            str(i),
            run.get("profile", "?"),
            "[luna.ok]✓[/luna.ok]" if run.get("status") == "finished" else "[luna.muted]·[/luna.muted]",
            run.get("base_url", "—"),
            f"[{p95_style}]{p95:.0f}[/{p95_style}]" if p95 else "[luna.muted]—[/luna.muted]",
            f"[{err_style}]{err_pct}[/{err_style}]",
            f"{apdex:.2f}" if isinstance(apdex, float) else str(apdex),
            slo_icon,
        )

    console.print(table)


# ── Discovery ─────────────────────────────────────────────────────────────────


def print_discovery(data: dict) -> None:
    source = data.get("source", "unknown")
    endpoints = data.get("endpoints", [])

    if not endpoints:
        console.print(f"  [luna.muted]No endpoints found (source: {source})[/luna.muted]")
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="luna.gold3", padding=(0, 2))
    table.add_column("Method", style="luna.gold", no_wrap=True, width=8)
    table.add_column("Path", style="luna.silver")
    table.add_column("Name", style="luna.muted")
    table.add_column("Group", style="luna.muted")
    table.add_column("Type", style="luna.muted", no_wrap=True)

    for ep in endpoints[:50]:
        table.add_row(
            ep.get("method", "—"),
            ep.get("path", "/"),
            ep.get("name", ""),
            ep.get("group", ""),
            ep.get("type", "rest"),
        )

    if len(endpoints) > 50:
        console.print(f"  [luna.muted]… and {len(endpoints) - 50} more[/luna.muted]")

    console.print(
        Panel(
            table,
            title=f"[luna.gold]{len(endpoints)} endpoints discovered[/luna.gold]  [luna.muted]via {source}[/luna.muted]",
            border_style="luna.gold3",
            padding=(0, 1),
        )
    )


# ── Config ────────────────────────────────────────────────────────────────────


def print_config(cfg: dict) -> None:
    endpoints = cfg.get("endpoints", [])
    service = cfg.get("service", "—")
    source = cfg.get("_source", "—")
    base_url = cfg.get("_base_url", "—")

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="luna.muted", no_wrap=True, width=14)
    table.add_column(style="luna.silver")
    table.add_row("Service", service)
    table.add_row("Base URL", base_url or "—")
    table.add_row("Source", source)
    table.add_row("Endpoints", f"[luna.gold]{len(endpoints)}[/luna.gold]")

    if endpoints:
        groups: dict[str, int] = {}
        for ep in endpoints:
            g = ep.get("group", "default")
            groups[g] = groups.get(g, 0) + 1
        table.add_row(
            "Groups", "  ".join(f"[luna.muted]{g}[/luna.muted] [luna.gold]{n}[/luna.gold]" for g, n in groups.items())
        )

    console.print(Panel(table, title="[luna.gold]Active Config[/luna.gold]", border_style="luna.gold3", padding=(1, 2)))


# ── Status ────────────────────────────────────────────────────────────────────


def print_status(data: dict) -> None:
    status = data.get("status", "idle")
    colors = {
        "idle": "luna.muted",
        "starting": "luna.warn",
        "running": "luna.ok",
        "finishing": "luna.blue",
        "finished": "luna.ok",
        "stopping": "luna.warn",
        "error": "luna.err",
    }
    color = colors.get(status, "luna.silver")
    icons = {
        "idle": "○",
        "starting": "◌",
        "running": "●",
        "finishing": "◑",
        "finished": "◉",
        "stopping": "◐",
        "error": "✗",
    }
    icon = icons.get(status, "·")

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="luna.muted", no_wrap=True, width=14)
    table.add_column()
    table.add_row("Status", f"[{color}]{icon}  {status.upper()}[/{color}]")
    if data.get("run_id"):
        table.add_row("Run ID", f"[luna.dim]{data['run_id'][:8]}…[/luna.dim]")
    if data.get("profile"):
        table.add_row("Profile", f"[luna.silver]{data['profile']}[/luna.silver]")
    if data.get("elapsed_s") is not None:
        table.add_row("Elapsed", f"[luna.silver]{data['elapsed_s']}s[/luna.silver]")

    console.print(Panel(table, title=f"[{color}]k6 Status[/{color}]", border_style=color, padding=(1, 2)))


# ── Spinners ──────────────────────────────────────────────────────────────────


@contextmanager
def spinner(message: str):
    """Context manager that shows a spinner while work is done."""
    with Progress(
        SpinnerColumn(style="luna.gold"),
        TextColumn(f"[luna.silver]{message}[/luna.silver]"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as prog:
        prog.add_task("", total=None)
        yield prog


@contextmanager
def run_progress(profile: str, duration: int):
    """Show a progress bar for a timed k6 run."""
    with Progress(
        SpinnerColumn(style="luna.gold"),
        TextColumn(f"[luna.gold]{profile}[/luna.gold] [luna.silver]running…[/luna.silver]"),
        BarColumn(bar_width=30, style="luna.gold3", complete_style="luna.gold"),
        TextColumn("[luna.silver]{task.fields[elapsed]}s / {task.fields[total]}s[/luna.silver]"),
        console=console,
        transient=True,
    ) as prog:
        task = prog.add_task("", total=duration, elapsed=0)
        yield prog, task


# ── Utility ───────────────────────────────────────────────────────────────────


def ok(message: str) -> None:
    console.print(f"  [luna.ok]✓[/luna.ok]  {message}")


def warn(message: str) -> None:
    console.print(f"  [luna.warn]⚠[/luna.warn]  {message}")


def err(message: str) -> None:
    console.print(f"  [luna.err]✗[/luna.err]  [luna.err]{message}[/luna.err]")


def info(message: str) -> None:
    console.print(f"  [luna.muted]·[/luna.muted]  [luna.silver]{message}[/luna.silver]")


def rule(title: str = "") -> None:
    console.print(Rule(title, style="luna.gold3"))
