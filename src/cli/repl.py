"""Interactive Luna REPL — prompt_toolkit powered, similar to Claude CLI."""

from __future__ import annotations

import shlex
import time
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style

from . import __version__
from .client import Client, LunaAPIError
from .display import (
    console,
    err,
    info,
    ok,
    print_banner,
    print_config,
    print_discovery,
    print_health,
    print_help,
    print_history,
    print_run_result,
    print_status,
    warn,
)

# ── Prompt style ──────────────────────────────────────────────────────────────

PROMPT_STYLE = Style.from_dict(
    {
        "marker": "#C8A84B bold",
        "at": "#5A6278",
        "host": "#A4B4CC",
        "suffix": "#C8A84B bold",
        "": "#FFFFFF",
    }
)

PROMPT_TOKENS = HTML("<marker>◆</marker><at> </at><host>luna</host><suffix> ❯ </suffix>")

# ── Tab-completion words ───────────────────────────────────────────────────────

COMPLETER = WordCompleter(
    [
        "test",
        "discover",
        "run",
        "status",
        "watch",
        "history",
        "health",
        "config",
        "stop",
        "/help",
        "/quit",
        "/exit",
        "/clear",
        "/version",
        "smoke",
        "ramp",
        "spike",
        "soak",
        "--profile",
        "--vus",
        "--duration",
        "--token",
        "--verbose",
    ],
    ignore_case=True,
    sentence=True,
)


# ── REPL ──────────────────────────────────────────────────────────────────────


class REPL:
    """
    Interactive REPL for Luna.

    Supports both slash commands (/help, /quit, /clear) and plain commands
    (test, discover, run, status, history, health, config, stop, watch).
    """

    def __init__(self, client: Client) -> None:
        self.client = client
        self._running = True
        history_path = "/tmp/.luna_history"
        self._session: PromptSession = PromptSession(
            history=FileHistory(history_path),
            auto_suggest=AutoSuggestFromHistory(),
            completer=COMPLETER,
            style=PROMPT_STYLE,
            key_bindings=self._bindings(),
            enable_history_search=True,
            mouse_support=False,
        )

    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("c-c")
        def _ctrl_c(event):  # noqa: ANN001
            # Soft interrupt — cancel current input line, don't exit
            event.app.current_buffer.reset()
            console.print("\n  [luna.muted]^C — type /quit to exit[/luna.muted]")

        @kb.add("c-d")
        def _ctrl_d(event):  # noqa: ANN001
            self._running = False
            event.app.exit()

        return kb

    def run(self) -> None:
        print_banner(self.client.base_url)
        self._check_connectivity()
        console.print(
            "  [luna.muted]Type a URL to test it, or run [/luna.muted][luna.gold]/help[/luna.gold][luna.muted] for commands.[/luna.muted]"
        )
        console.print()

        while self._running:
            try:
                raw = self._session.prompt(PROMPT_TOKENS, style=PROMPT_STYLE)
            except EOFError:
                break
            except KeyboardInterrupt:
                continue

            line = raw.strip()
            if not line:
                continue

            self._dispatch(line)

        console.print("\n  [luna.muted]Goodbye.[/luna.muted]\n")

    # ── Connectivity ──────────────────────────────────────────────────────────

    def _check_connectivity(self) -> None:
        if self.client.is_alive():
            ok(f"Connected to [bold]{self.client.base_url}[/bold]")
        else:
            warn(
                f"Luna dashboard not found at [bold]{self.client.base_url}[/bold]\n"
                "  Run [bold]just up[/bold] to start, or pass a different URL with [bold]--url[/bold]."
            )
        console.print()

    # ── Dispatcher ────────────────────────────────────────────────────────────

    def _dispatch(self, line: str) -> None:
        # Slash commands
        if line.startswith("/"):
            self._handle_slash(line)
            return

        # Bare URL → quick test
        if line.startswith("http://") or line.startswith("https://"):
            self._cmd_test(["test", line])
            return

        try:
            parts = shlex.split(line)
        except ValueError as exc:
            err(f"Parse error: {exc}")
            return

        if not parts:
            return

        cmd, *rest = parts
        handlers: dict[str, Any] = {
            "test": self._cmd_test,
            "discover": self._cmd_discover,
            "run": self._cmd_run,
            "status": self._cmd_status,
            "watch": self._cmd_watch,
            "history": self._cmd_history,
            "health": self._cmd_health,
            "config": self._cmd_config,
            "stop": self._cmd_stop,
            "help": lambda _: print_help(),
            "quit": lambda _: self._quit(),
            "exit": lambda _: self._quit(),
        }

        handler = handlers.get(cmd.lower())
        if handler:
            try:
                handler([cmd] + rest)
            except LunaAPIError as exc:
                err(str(exc))
            except Exception as exc:
                err(f"Unexpected error: {exc}")
        else:
            err(f"Unknown command: {cmd!r}  — type /help")

    # ── Slash commands ────────────────────────────────────────────────────────

    def _handle_slash(self, line: str) -> None:
        cmd = line.split()[0].lower()
        {
            "/help": lambda: print_help(),
            "/quit": self._quit,
            "/exit": self._quit,
            "/clear": lambda: console.clear(),
            "/version": lambda: console.print(
                f"  [luna.gold]Luna CLI[/luna.gold] [luna.muted]v{__version__}[/luna.muted]"
            ),
        }.get(cmd, lambda: err(f"Unknown slash command: {cmd}  — type /help"))()

    def _quit(self) -> None:
        self._running = False

    # ── Commands ──────────────────────────────────────────────────────────────

    def _cmd_test(self, args: list[str]) -> None:
        """test <url> [--profile smoke] [--vus N] [--duration N] [--token T] [-v]"""
        opts = _parse_args(args[1:], url=True)
        url = opts.get("url")
        if not url:
            err("Usage: test <url> [--profile smoke] [--vus 2] [--duration 30]")
            return

        profile = opts.get("profile", "smoke")
        vus = int(opts.get("vus", 2))
        duration = int(opts.get("duration", 30))
        token = opts.get("token", "")
        verbose = opts.get("verbose", False)

        result = self.client.test_service(url=url, token=token, profile=profile, vus=vus, duration=duration)
        console.print()
        print_run_result(result, verbose=verbose)

    def _cmd_discover(self, args: list[str]) -> None:
        """discover <url> [--token T]"""
        opts = _parse_args(args[1:], url=True)
        url = opts.get("url")
        if not url:
            err("Usage: discover <url> [--token <token>]")
            return

        data = self.client.discover(url, token=opts.get("token", ""))
        ok(f"Discovered via [bold]{data.get('source', '?')}[/bold]")
        print_discovery(data)

    def _cmd_run(self, args: list[str]) -> None:
        """run [<profile>] [--vus N] [--duration N] [--url U]"""
        opts = _parse_args(args[1:], positional="profile")
        profile = opts.get("profile", "smoke")
        vus = int(opts.get("vus", 2))
        duration = int(opts.get("duration", 30))
        base_url = opts.get("url", "")

        info(f"Starting [bold]{profile}[/bold] ({vus} VUs · {duration}s)…")
        data = self.client.start_run(profile=profile, vus=vus, duration=duration, base_url=base_url)
        ok(f"Run started — [dim]{str(data.get('run_id', ''))[:8]}…[/dim]")
        info("Use [bold]watch[/bold] to stream progress, or [bold]status[/bold] to check.")

    def _cmd_status(self, _args: list[str]) -> None:
        data = self.client.status()
        print_status(data)

    def _cmd_watch(self, _args: list[str]) -> None:
        info("Watching run — press Ctrl-C to stop watching (run continues)…")
        try:
            while True:
                s = self.client.status()
                st = s.get("status", "idle")
                elapsed = s.get("elapsed_s", "?")
                console.print(f"  [luna.muted]{elapsed}s[/luna.muted]  [luna.gold]{st}[/luna.gold]", end="\r")
                if st in ("finished", "error", "idle"):
                    console.print()
                    print_status(s)
                    return
                time.sleep(2)
        except KeyboardInterrupt:
            console.print()
            info("Stopped watching (run still active). Use [bold]stop[/bold] to cancel it.")

    def _cmd_history(self, args: list[str]) -> None:
        opts = _parse_args(args[1:])
        limit = int(opts.get("limit", 10))
        runs = self.client.history(limit=limit)
        print_history(runs)

    def _cmd_health(self, _args: list[str]) -> None:
        data = self.client.health()
        print_health(data)

    def _cmd_config(self, _args: list[str]) -> None:
        cfg = self.client.get_config()
        print_config(cfg)

    def _cmd_stop(self, _args: list[str]) -> None:
        data = self.client.stop_run()
        ok(f"Stop requested: {data}")


# ── Argument mini-parser ──────────────────────────────────────────────────────


def _parse_args(tokens: list[str], url: bool = False, positional: str = "") -> dict:
    """
    Minimal flag parser for REPL commands.

    Handles:
      - bare URL (first positional starting with http)
      - --flag value pairs
      - --flag (boolean flags, e.g. --verbose / -v)
    """
    result: dict[str, Any] = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("--"):
            key = tok[2:]
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                result[key] = tokens[i + 1]
                i += 2
            else:
                result[key] = True
                i += 1
        elif tok in ("-v", "-V"):
            result["verbose"] = True
            i += 1
        elif url and (tok.startswith("http://") or tok.startswith("https://")):
            result["url"] = tok
            i += 1
        elif positional and positional not in result:
            result[positional] = tok
            i += 1
        else:
            i += 1
    return result
