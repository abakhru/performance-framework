"""
luna — CLI entry point.

Usage:
  luna                                  # interactive REPL
  luna test <url>                       # one-shot: discover + smoke test
  luna test <url> --profile ramp --vus 20 --duration 120
  luna discover <url>
  luna run smoke --vus 10 --duration 60
  luna status
  luna watch
  luna history [--limit N]
  luna health
  luna config
  luna stop

  luna connect [--url https://luna.example.com] [--key <api-key>]
  luna install-claude [--url https://luna.example.com] [--key <api-key>]
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from . import __version__
from .client import Client
from .display import (
    console,
    err,
    info,
    ok,
    print_config,
    print_discovery,
    print_health,
    print_history,
    print_run_result,
    print_status,
    warn,
)
from .repl import REPL

# ── App ───────────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="luna",
    help="Luna Testing Platform CLI",
    add_completion=True,
    rich_markup_mode="rich",
    no_args_is_help=False,
    invoke_without_command=True,
)

# ── Shared options ────────────────────────────────────────────────────────────

URL_OPT = typer.Option("http://localhost:5656", "--url", "-u", help="Luna dashboard URL", envvar="LUNA_URL")
TOKEN_OPT = typer.Option("", "--token", "-t", help="Auth bearer token for target service", envvar="LUNA_TOKEN")
VERBOSE_OPT = typer.Option(False, "--verbose", "-v", help="Show extra detail")


# ── Root callback → REPL when called with no subcommand ──────────────────────


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    url: str = URL_OPT,
    version: bool = typer.Option(False, "--version", "-V", help="Print version and exit", is_eager=True),
) -> None:
    """[bold gold1]Luna[/bold gold1] — Testing as a Service · interactive CLI"""
    if version:
        console.print(f"Luna CLI [bold]v{__version__}[/bold]")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        # No subcommand → launch REPL
        client = Client(base_url=url)
        repl = REPL(client)
        try:
            repl.run()
        finally:
            client.close()


# ── Subcommands ───────────────────────────────────────────────────────────────


@app.command()
def test(
    target_url: Annotated[str, typer.Argument(help="URL of the service to test")],
    url: str = URL_OPT,
    token: str = TOKEN_OPT,
    profile: str = typer.Option("smoke", "--profile", "-p", help="k6 load profile: smoke | ramp | spike | soak"),
    vus: int = typer.Option(2, "--vus", help="Virtual users (overrides profile default)"),
    duration: int = typer.Option(30, "--duration", "-d", help="Test duration in seconds"),
    verbose: bool = VERBOSE_OPT,
) -> None:
    """
    ONE-SHOT: discover endpoints from [bold]TARGET_URL[/bold], save config,
    run k6, and print results.

    Examples:
      luna test https://api.example.com
      luna test https://api.example.com --profile ramp --vus 20 --duration 120
      luna test https://api.example.com --token "Bearer xyz"
    """
    _ensure_banner(url)
    with Client(base_url=url) as client:
        _require_alive(client, url)
        result = client.test_service(target_url, token=token, profile=profile, vus=vus, duration=duration)

    console.print()
    print_run_result(result, verbose=verbose)
    raise typer.Exit(0 if result.get("success") else 1)


@app.command()
def discover(
    target_url: Annotated[str, typer.Argument(help="URL to probe for endpoints")],
    url: str = URL_OPT,
    token: str = TOKEN_OPT,
    verbose: bool = VERBOSE_OPT,
) -> None:
    """
    Probe [bold]TARGET_URL[/bold] and list all discovered API endpoints.

    Luna tries OpenAPI/Swagger, sitemap, common paths, and HTML link
    extraction — in that order.
    """
    with Client(base_url=url) as client:
        _require_alive(client, url)
        data = client.discover(target_url, token=token)

    ok(f"Source: [bold]{data.get('source', '?')}[/bold]")
    print_discovery(data)


@app.command()
def run(
    profile: Annotated[str, typer.Argument(help="Load profile: smoke | ramp | spike | soak")] = "smoke",
    url: str = URL_OPT,
    target: str = typer.Option("", "--target", help="Override base URL in run"),
    vus: int = typer.Option(2, "--vus", help="Virtual users"),
    duration: int = typer.Option(30, "--duration", "-d", help="Duration in seconds"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Block until run completes"),
) -> None:
    """
    Start a k6 [bold]PROFILE[/bold] run against the saved endpoint config.

    The endpoint config must already be saved (use [bold]discover[/bold] first
    or upload via [bold]luna config[/bold]).
    """
    with Client(base_url=url) as client:
        _require_alive(client, url)
        info(f"Starting [bold]{profile}[/bold] ({vus} VUs · {duration}s)…")
        data = client.start_run(profile=profile, vus=vus, duration=duration, base_url=target)
        ok(f"Run started — [dim]{str(data.get('run_id', ''))[:8]}…[/dim]")

        if wait:
            final = client._wait_with_progress(expected_duration=duration)
            print_status(final)
            success = final.get("status") == "finished"
            raise typer.Exit(0 if success else 1)
        else:
            info("Use [bold]luna watch[/bold] to track progress.")


@app.command()
def status(url: str = URL_OPT) -> None:
    """Show the current k6 run status."""
    with Client(base_url=url) as client:
        _require_alive(client, url)
        data = client.status()
    print_status(data)


@app.command()
def watch(
    url: str = URL_OPT,
    poll: float = typer.Option(2.0, "--poll", help="Poll interval in seconds"),
) -> None:
    """Stream live status updates until the current run finishes."""
    import time

    with Client(base_url=url) as client:
        _require_alive(client, url)
        info("Watching run — Ctrl-C to stop watching…")
        try:
            while True:
                s = client.status()
                st = s.get("status", "idle")
                elapsed = s.get("elapsed_s", "?")
                console.print(f"\r  [luna.muted]{elapsed}s[/luna.muted]  [luna.gold]{st:<12}[/luna.gold]", end="")
                if st in ("finished", "error", "idle"):
                    console.print()
                    print_status(s)
                    return
                time.sleep(poll)
        except KeyboardInterrupt:
            console.print()
            info("Stopped watching (run still active). Use [bold]luna stop[/bold] to cancel.")


@app.command()
def history(
    url: str = URL_OPT,
    limit: int = typer.Option(10, "--limit", "-n", help="Number of recent runs to show"),
) -> None:
    """Show recent test runs with SLO verdicts."""
    with Client(base_url=url) as client:
        _require_alive(client, url)
        runs = client.history(limit=limit)
    print_history(runs)


@app.command()
def health(url: str = URL_OPT) -> None:
    """Check Luna, k6, and InfluxDB health."""
    with Client(base_url=url) as client:
        _require_alive(client, url)
        data = client.health()
    print_health(data)


@app.command()
def config(url: str = URL_OPT) -> None:
    """Show the active endpoint configuration."""
    with Client(base_url=url) as client:
        _require_alive(client, url)
        cfg = client.get_config()
    print_config(cfg)


@app.command()
def stop(url: str = URL_OPT) -> None:
    """Stop the currently running k6 job."""
    with Client(base_url=url) as client:
        _require_alive(client, url)
        data = client.stop_run()
    ok(f"Stop requested — {data}")


KEY_OPT = typer.Option("", "--key", "-k", help="Luna API key (LUNA_API_KEY)", envvar="LUNA_API_KEY")


@app.command()
def connect(
    url: str = typer.Option("http://localhost:5656", "--url", "-u", help="Deployed Luna URL", envvar="LUNA_URL"),
    key: str = KEY_OPT,
) -> None:
    """
    Print copy-paste integration snippets for every Claude integration channel.

    Shows configs for: Claude Desktop, Claude API (mcp_servers), Python client,
    REST/curl, and GitHub Actions CI.
    """

    auth_env = f"\n  Authorization: Bearer {key}" if key else "  # No API key set — all requests allowed"
    python_token = f', token="{key}"' if key else ""

    # ── Claude Desktop ─────────────────────────────────────────────────────────
    desktop_cfg = {
        "mcpServers": {
            "luna": {
                "command": "npx",
                "args": ["-y", "mcp-remote", f"{url}/mcp"] + (["--header", f"Authorization: Bearer {key}"] if key else []),
            }
        }
    }
    console.print()
    console.print("[luna.gold]━━  Integration Channels  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/luna.gold]")
    console.print()

    _snippet(
        "1 · Claude Desktop  (engineers on your team)",
        "Add to ~/Library/Application Support/Claude/claude_desktop_config.json\n"
        "[luna.muted]Windows: %APPDATA%\\Claude\\claude_desktop_config.json[/luna.muted]",
        json.dumps(desktop_cfg, indent=2),
        "json",
    )

    # ── Claude API ─────────────────────────────────────────────────────────────
    api_snippet = f"""\
import anthropic

client = anthropic.Anthropic()

response = client.beta.messages.create(
    model="claude-opus-4-5",
    max_tokens=4096,
    mcp_servers=[{{
        "type": "url",
        "url": "{url}/mcp",
        "name": "luna",{f'''
        "authorization_token": "{key}",''' if key else ""}
    }}],
    messages=[{{
        "role": "user",
        "content": "Test https://api.example.com and tell me the p95 latency."
    }}],
    betas=["mcp-client-2025-04-04"],
)
print(response.content)"""
    _snippet(
        "2 · Claude API  (claude.ai, API, Claude for Work)",
        "Pass Luna as an MCP server directly in the Anthropic SDK call",
        api_snippet,
        "python",
    )

    # ── Python client ──────────────────────────────────────────────────────────
    python_snippet = f"""\
from api_tests.luna import LunaClient

luna = LunaClient("{url}"{python_token})
luna.wait_until_ready()

result = luna.test_service("https://your-api.com", profile="smoke")
result.assert_success()
print(result.summary)"""
    _snippet(
        "3 · Python client  (CI scripts, pytest fixtures, agent pipelines)",
        "pip install from the luna package — wraps the REST API",
        python_snippet,
        "python",
    )

    # ── REST / curl ────────────────────────────────────────────────────────────
    curl_auth = f' -H "Authorization: Bearer {key}"' if key else ""
    curl_snippet = f"""\
# Health check (no auth required)
curl {url}/health

# Discover endpoints{auth_env}
curl{curl_auth} \\
  "{url}/discovery/discover?url=https://your-api.com"

# Start a smoke run
curl{curl_auth} -X POST {url}/run \\
  -H "Content-Type: application/json" \\
  -d '{{"base_url":"https://your-api.com","profile":"smoke","vus":2,"duration":30}}'"""
    _snippet(
        "4 · REST API  (any language, Postman, HTTP client)",
        "Plain HTTP — works from any tool that can make web requests",
        curl_snippet,
        "bash",
    )

    # ── Env vars ───────────────────────────────────────────────────────────────
    env_snippet = f"""\
LUNA_URL={url}{"" if not key else f"""
LUNA_API_KEY={key}"""}

# Then:
luna test https://your-api.com          # CLI uses env vars automatically
luna health"""
    _snippet(
        "5 · Environment variables  (12-factor / CI)",
        "Set once, used by luna CLI, LunaClient, and GitHub Actions",
        env_snippet,
        "bash",
    )

    console.print(
        f"\n  [luna.muted]Tip:[/luna.muted]  [luna.gold]luna install-claude --url {url}"
        + (f" --key {key}" if key else "")
        + "[/luna.gold]  [luna.muted]writes Claude Desktop config automatically[/luna.muted]\n"
    )


@app.command(name="install-claude")
def install_claude(
    url: str = typer.Option("http://localhost:5656", "--url", "-u", help="Luna dashboard URL", envvar="LUNA_URL"),
    key: str = KEY_OPT,
    dry_run: bool = typer.Option(False, "--dry-run", help="Print config without writing"),
) -> None:
    """
    Write Luna into Claude Desktop's MCP server config.

    Finds (or creates) claude_desktop_config.json and adds / updates the
    [bold]luna[/bold] MCP server entry.  Restarts Claude Desktop on macOS
    so the change takes effect immediately.

    Run with [bold]--dry-run[/bold] to preview the config without writing.
    """
    config_path = _claude_config_path()
    if config_path is None:
        err("Could not find Claude Desktop config directory. Is Claude Desktop installed?")
        info("Download from: https://claude.ai/download")
        raise typer.Exit(1)

    # Load or initialise
    existing: dict = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            warn(f"Could not parse {config_path} — will overwrite")

    args: list[str] = ["-y", "mcp-remote", f"{url}/mcp"]
    if key:
        args += ["--header", f"Authorization: Bearer {key}"]

    existing.setdefault("mcpServers", {})
    existing["mcpServers"]["luna"] = {"command": "npx", "args": args}

    cfg_text = json.dumps(existing, indent=2)

    if dry_run:
        console.print(f"\n[luna.muted]Would write to:[/luna.muted] [luna.gold]{config_path}[/luna.gold]\n")
        from rich.syntax import Syntax

        console.print(Syntax(cfg_text, "json", theme="monokai", line_numbers=False))
        return

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(cfg_text)

    ok(f"Written to [bold]{config_path}[/bold]")
    ok(f"Luna MCP server → [bold]{url}/mcp[/bold]")

    # Restart Claude Desktop on macOS so the config is picked up
    if platform.system() == "Darwin":
        try:
            subprocess.run(["pkill", "-x", "Claude"], capture_output=True)
            info("Claude Desktop restarted — open it and ask: [bold]Test https://your-api.com[/bold]")
        except Exception:
            info("Restart Claude Desktop manually for the change to take effect.")
    else:
        info("Restart Claude Desktop for the change to take effect.")

    console.print()
    info(
        "Engineers on your team can run the same command pointed at your deployed Luna:\n"
        f"  [luna.gold]luna install-claude --url {url}"
        + (f" --key {key}" if key else "")
        + "[/luna.gold]"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _snippet(title: str, subtitle: str, code: str, lang: str) -> None:
    from rich.syntax import Syntax

    console.print(f"[luna.gold]◆[/luna.gold] [bold white]{title}[/bold white]")
    console.print(f"  [luna.muted]{subtitle}[/luna.muted]")
    console.print(Syntax(code, lang, theme="monokai", line_numbers=False, padding=(1, 2)))
    console.print()


def _claude_config_path() -> Path | None:
    """Return the platform-specific path to claude_desktop_config.json."""
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "Claude"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return None
        base = Path(appdata) / "Claude"
    else:
        # Linux / other — use XDG_CONFIG_HOME or ~/.config
        xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        base = Path(xdg) / "Claude"
    return base / "claude_desktop_config.json"


def _ensure_banner(dashboard_url: str) -> None:
    """Print the banner once for non-REPL single commands."""
    pass  # Banner only in REPL; keep CLI output clean


def _require_alive(client: Client, url: str) -> None:
    if not client.is_alive():
        err(f"Luna dashboard not reachable at [bold]{url}[/bold]")
        info("Start it with: [bold]just up[/bold]  or  [bold]uvicorn dashboard.server:app --port 5656[/bold]")
        raise typer.Exit(1)


# ── Entry ─────────────────────────────────────────────────────────────────────


def main() -> None:
    app()


if __name__ == "__main__":
    main()
