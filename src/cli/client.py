"""Thin display-aware wrapper around LunaClient."""

from __future__ import annotations

import time
from typing import Any

import httpx

from .display import console, info, ok, spinner, warn

# Try to import LunaClient from the framework; fall back gracefully.
try:
    from api_tests.luna import LunaClient as _LunaClient  # type: ignore[import]

    _LUNA_AVAILABLE = True
except ImportError:
    _LUNA_AVAILABLE = False


class LunaAPIError(Exception):
    """Raised when the Luna API returns an error."""


class Client:
    """
    Display-aware Luna client.

    Wraps the HTTP API with rich output, progress spinners, and
    sensible error messages. Falls back to raw httpx if LunaClient
    is not installed.
    """

    def __init__(self, base_url: str = "http://localhost:5656", timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout)
        self._luna: Any = None
        if _LUNA_AVAILABLE:
            self._luna = _LunaClient(base_url=self.base_url)

    # ── Connectivity ──────────────────────────────────────────────────────────

    def is_alive(self) -> bool:
        """Return True if the dashboard is reachable."""
        try:
            r = self._http.get("/health", timeout=3)
            return r.status_code < 500
        except Exception:
            return False

    def wait_for_dashboard(self, retries: int = 5, delay: float = 1.5) -> bool:
        """Poll until dashboard is up or retries exhausted."""
        for i in range(retries):
            if self.is_alive():
                return True
            if i < retries - 1:
                time.sleep(delay)
        return False

    # ── Health ────────────────────────────────────────────────────────────────

    def health(self) -> dict:
        r = self._http.get("/health")
        r.raise_for_status()
        return r.json()

    # ── Discovery ─────────────────────────────────────────────────────────────

    def discover(self, url: str, token: str = "") -> dict:
        params: dict = {"url": url}
        if token:
            params["token"] = token
        with spinner(f"Discovering endpoints at {url}"):
            r = self._http.get("/discovery/discover", params=params, timeout=30)
        if not r.is_success:
            raise LunaAPIError(f"Discovery failed ({r.status_code}): {r.text[:200]}")
        return r.json()

    # ── Config ────────────────────────────────────────────────────────────────

    def get_config(self) -> dict:
        r = self._http.get("/endpoints")
        if not r.is_success:
            raise LunaAPIError(f"Could not load config ({r.status_code})")
        return r.json()

    def save_config(self, endpoints: list, base_url: str = "", service: str = "") -> dict:
        payload: dict = {"endpoints": endpoints}
        if base_url:
            payload["base_url"] = base_url
        if service:
            payload["service"] = service
        r = self._http.post("/endpoints", json=payload)
        if not r.is_success:
            raise LunaAPIError(f"Failed to save config ({r.status_code}): {r.text[:200]}")
        return r.json()

    # ── Runs ──────────────────────────────────────────────────────────────────

    def start_run(
        self,
        profile: str = "smoke",
        vus: int = 2,
        duration: int = 30,
        base_url: str = "",
    ) -> dict:
        payload: dict = {"profile": profile, "vus": vus, "duration": duration}
        if base_url:
            payload["base_url"] = base_url
        r = self._http.post("/run", json=payload, timeout=10)
        if not r.is_success:
            raise LunaAPIError(f"Failed to start run ({r.status_code}): {r.text[:200]}")
        return r.json()

    def stop_run(self) -> dict:
        r = self._http.post("/run/stop")
        r.raise_for_status()
        return r.json()

    def status(self) -> dict:
        r = self._http.get("/run/status")
        r.raise_for_status()
        return r.json()

    def wait_for_run(self, poll_interval: float = 2.0, timeout: float = 600.0) -> dict:
        """Poll until current run finishes; return final status dict."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            s = self.status()
            if s.get("status") in ("finished", "error", "idle"):
                return s
            time.sleep(poll_interval)
        return self.status()

    # ── History ───────────────────────────────────────────────────────────────

    def history(self, limit: int = 10) -> list:
        r = self._http.get("/runs", params={"limit": limit})
        if not r.is_success:
            return []
        data = r.json()
        if isinstance(data, list):
            return data
        return data.get("runs", [])

    # ── One-shot test_service ─────────────────────────────────────────────────

    def test_service(
        self,
        url: str,
        token: str = "",
        profile: str = "smoke",
        vus: int = 2,
        duration: int = 30,
    ) -> dict:
        """
        Discover + save + run + wait — returns a result dict suitable for
        display.print_run_result().
        """
        t0 = time.time()

        # 1. Discover
        disc = self.discover(url, token=token)
        endpoints = disc.get("endpoints", [])
        source = disc.get("source", "?")
        ok(f"Found [bold]{len(endpoints)}[/bold] endpoints via {source}")

        if not endpoints:
            warn("No endpoints discovered — nothing to test")
            return {
                "success": False,
                "profile": profile,
                "elapsed_s": 0,
                "endpoint_count": 0,
                "source": source,
                "status": "aborted",
                "error": "No endpoints discovered",
            }

        # 2. Save config
        info("Saving endpoint config…")
        self.save_config(endpoints, base_url=url)

        # 3. Start run
        info(f"Starting [bold]{profile}[/bold] run ({vus} VUs · {duration}s)…")
        run_data = self.start_run(profile=profile, vus=vus, duration=duration, base_url=url)
        run_id = run_data.get("run_id", "?")
        info(f"Run [dim]{str(run_id)[:8]}…[/dim] started")

        # 4. Wait for completion (with live elapsed display)
        final = self._wait_with_progress(expected_duration=duration)

        elapsed = time.time() - t0
        success = final.get("status") == "finished"

        return {
            "success": success,
            "profile": profile,
            "elapsed_s": elapsed,
            "endpoint_count": len(endpoints),
            "source": source,
            "status": final.get("status", "?"),
            "error": final.get("error", ""),
            "endpoints": endpoints,
        }

    def _wait_with_progress(self, expected_duration: int = 30, poll: float = 2.0) -> dict:
        """Wait for current run, showing a live timer."""
        from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

        with Progress(
            SpinnerColumn(style="luna.gold"),
            TextColumn("[luna.silver]Running…[/luna.silver]"),
            BarColumn(bar_width=30, style="luna.gold3", complete_style="luna.gold"),
            TextColumn("[luna.muted]{task.fields[elapsed]:.0f}s[/luna.muted]"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as prog:
            task = prog.add_task("run", total=expected_duration, elapsed=0)
            t0 = time.time()
            while True:
                s = self.status()
                elapsed = time.time() - t0
                prog.update(task, completed=min(elapsed, expected_duration), elapsed=elapsed)
                if s.get("status") in ("finished", "error", "idle"):
                    return s
                time.sleep(poll)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
