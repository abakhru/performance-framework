"""LunaClient — high-level Python client for AI agents and CI pipelines.

Provides a single object that wraps the entire Luna workflow:
  discover → configure → run → wait → results

Usage (Python agent):
    from api_tests.luna import LunaClient

    luna = LunaClient("http://localhost:5656")
    result = luna.test_service("https://api.example.com", token="Bearer abc123")
    assert result.success, f"Tests failed: {result.summary}"

Usage (programmatic):
    luna = LunaClient()  # auto-connects to localhost:5656
    endpoints = luna.discover("https://api.example.com")
    luna.save_config(endpoints, service="my-api")
    run = luna.start_run("https://api.example.com", profile="smoke")
    result = luna.wait(run["run_id"])
    print(result.summary)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx


@dataclass
class RunResult:
    """Structured result from a completed k6 run."""

    success: bool
    run_id: str
    profile: str
    status: str
    elapsed_s: float
    endpoint_count: int
    source: str
    endpoints: list[dict]
    error: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def summary(self) -> str:
        if self.error:
            return f"ERROR: {self.error}"
        icon = "✓" if self.success else "✗"
        return f"{icon} {self.profile} · {self.endpoint_count} endpoints · {self.elapsed_s:.0f}s · status={self.status}"

    def assert_success(self) -> None:
        """Raise AssertionError if the run did not succeed."""
        if not self.success:
            raise AssertionError(
                f"Luna run failed: {self.summary}\n"
                f"Run ID: {self.run_id}\n"
                f"Error: {self.error or 'see dashboard for details'}"
            )


class LunaClient:
    """High-level client for the Luna testing platform.

    Agents and CI pipelines should use this class as the primary interface.
    Each method corresponds to one step in the testing workflow.

    Args:
        base_url:  Luna dashboard URL (default: http://localhost:5656)
        timeout:   HTTP request timeout in seconds (default: 30)

    Example — full workflow in one call:
        result = LunaClient().test_service("https://api.example.com")
        result.assert_success()

    Example — step by step:
        luna = LunaClient("https://luna.mycompany.com")
        eps = luna.discover("https://api.mycompany.com", token="Bearer xyz")
        luna.save_config(eps["endpoints"], service="my-api")
        run = luna.start_run("https://api.mycompany.com", profile="ramp", vus=20, duration=120)
        result = luna.wait(run["run_id"], timeout_s=300)
        result.assert_success()
    """

    def __init__(self, base_url: str = "http://localhost:5656", timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self._base_url, timeout=timeout)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def __enter__(self) -> LunaClient:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ── Health ─────────────────────────────────────────────────────────────────

    def health(self) -> dict:
        """Return Luna service health. Raises on connection error."""
        r = self._client.get("/health")
        r.raise_for_status()
        return r.json()

    def is_ready(self) -> bool:
        """Return True if Luna dashboard is reachable."""
        try:
            self.health()
            return True
        except Exception:
            return False

    def wait_until_ready(self, timeout_s: float = 30.0, poll_interval: float = 1.0) -> None:
        """Block until the Luna dashboard responds, or raise TimeoutError."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.is_ready():
                return
            time.sleep(poll_interval)
        raise TimeoutError(f"Luna at {self._base_url} not ready within {timeout_s}s")

    # ── Discovery ──────────────────────────────────────────────────────────────

    def discover(self, url: str, token: str = "") -> dict:
        """Probe *url* for API endpoints via OpenAPI → GraphQL → REST.

        Returns dict with: source, endpoints, setup, teardown.
        """
        r = self._client.get("/discover/url", params={"url": url, "token": token})
        r.raise_for_status()
        return r.json()

    def crawl(self, url: str, token: str = "", max_pages: int = 30) -> dict:
        """Crawl *url* — follow HTML links and scan JS for API paths."""
        r = self._client.get("/discover/crawl", params={"url": url, "token": token, "max_pages": max_pages})
        r.raise_for_status()
        return r.json()

    def from_postman(self, collection: dict) -> dict:
        """Extract endpoints from a Postman Collection v2.x dict."""
        r = self._client.post("/discover/postman", json=collection)
        r.raise_for_status()
        return r.json()

    def from_har(self, har: dict) -> dict:
        """Extract endpoints from an HTTP Archive (HAR) dict."""
        r = self._client.post("/discover/har", json=har)
        r.raise_for_status()
        return r.json()

    def baseline_slos(self, url: str, token: str = "") -> dict:
        """Measure real p95 latency and error rate baselines via /discover/slos."""
        r = self._client.get("/discover/slos", params={"url": url, "token": token})
        r.raise_for_status()
        return r.json()

    # ── Config management ──────────────────────────────────────────────────────

    def save_config(
        self,
        endpoints: list[dict],
        service: str = "my-api",
        base_url: str = "",
        auth_token: str = "",
    ) -> dict:
        """Save and activate an endpoint config. Returns {"ok": True, "filename": ...}."""
        r = self._client.post(
            "/endpoints/save",
            json={
                "service": service,
                "endpoints": endpoints,
                "setup": [],
                "teardown": [],
                "_base_url": base_url,
                "_auth_token": auth_token,
            },
        )
        r.raise_for_status()
        return r.json()

    def get_config(self) -> dict:
        """Return the currently active endpoint config."""
        r = self._client.get("/config/endpoints")
        r.raise_for_status()
        return r.json()

    def list_configs(self) -> list[dict]:
        """List all saved endpoint configs, newest first."""
        r = self._client.get("/configs/saved")
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else data.get("configs", [])

    # ── Run control ────────────────────────────────────────────────────────────

    def start_run(
        self,
        base_url: str,
        auth_token: str = "",
        profile: str = "smoke",
        vus: int = 10,
        duration: int = 60,
    ) -> dict:
        """Start a k6 load test. Returns {"status": "starting", "run_id": "..."}.

        profile: smoke | ramp | soak | stress | spike
        """
        r = self._client.post(
            "/run/start",
            json={
                "base_url": base_url,
                "auth_token": auth_token,
                "profile": profile,
                "vus": str(vus),
                "duration": f"{duration}s",
            },
        )
        r.raise_for_status()
        return r.json()

    def stop_run(self) -> dict:
        """Terminate the currently running k6 process."""
        r = self._client.post("/run/stop")
        r.raise_for_status()
        return r.json()

    def run_status(self) -> dict:
        """Return current k6 run status."""
        r = self._client.get("/run/status")
        r.raise_for_status()
        return r.json()

    def wait(self, run_id: str = "", timeout_s: float = 300.0, poll_s: float = 2.0) -> dict:
        """Block until the current run completes. Returns status dict."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            status = self.run_status()
            if status.get("status") in ("finished", "idle", "error"):
                return {"success": status.get("status") in ("finished", "idle"), **status}
            time.sleep(poll_s)
        return {"success": False, "timed_out": True, "timeout_s": timeout_s}

    def get_history(self, limit: int = 10) -> list[dict]:
        """Return recent run history with SLO verdicts."""
        r = self._client.get("/runs", params={"limit": limit})
        r.raise_for_status()
        data = r.json()
        # /runs may return {"runs": [...]} or directly a list
        return data.get("runs", data) if isinstance(data, dict) else data

    # ── One-shot workflow ──────────────────────────────────────────────────────

    def test_service(
        self,
        url: str,
        token: str = "",
        profile: str = "smoke",
        vus: int = 2,
        duration: int = 30,
        save: bool = True,
    ) -> RunResult:
        """ONE-SHOT: discover → save → run → wait → return structured result.

        This is the primary method for autonomous agents — a single call does
        the complete testing workflow.

        Args:
            url:      Target service URL
            token:    Bearer token (optional)
            profile:  smoke | ramp | soak | stress | spike
            vus:      Virtual users (default 2 for smoke)
            duration: Seconds (default 30 for smoke)
            save:     Save discovered endpoints as active config

        Returns RunResult — call .assert_success() to raise on failure.

        Example:
            result = LunaClient().test_service("https://api.example.com")
            result.assert_success()
            print(f"Tested {result.endpoint_count} endpoints in {result.elapsed_s:.0f}s")
        """
        t0 = time.monotonic()

        # Step 1: Discover
        try:
            discovered = self.discover(url, token=token)
        except Exception as exc:
            return RunResult(
                success=False,
                run_id="",
                profile=profile,
                status="error",
                elapsed_s=time.monotonic() - t0,
                endpoint_count=0,
                source="unknown",
                endpoints=[],
                error=f"Discovery failed: {exc}",
            )

        endpoints = discovered.get("endpoints", [])
        source = discovered.get("source", "unknown")

        if not endpoints:
            return RunResult(
                success=False,
                run_id="",
                profile=profile,
                status="error",
                elapsed_s=time.monotonic() - t0,
                endpoint_count=0,
                source=source,
                endpoints=[],
                error="No endpoints discovered. Try crawl() or supply a Postman collection.",
            )

        # Step 2: Save config
        if save:
            service_name = url.split("//")[-1].split("/")[0]
            try:
                self.save_config(endpoints, service=service_name, base_url=url, auth_token=token)
            except Exception:
                pass  # non-fatal — endpoints already discovered

        # Step 3: Start run
        try:
            run_info = self.start_run(base_url=url, auth_token=token, profile=profile, vus=vus, duration=duration)
            run_id = run_info.get("run_id", "")
        except Exception as exc:
            return RunResult(
                success=False,
                run_id="",
                profile=profile,
                status="error",
                elapsed_s=time.monotonic() - t0,
                endpoint_count=len(endpoints),
                source=source,
                endpoints=endpoints,
                error=f"Failed to start run: {exc}",
            )

        # Step 4: Wait
        timeout = max(duration + 60, 120)
        result = self.wait(run_id=run_id, timeout_s=timeout)

        return RunResult(
            success=result.get("success", False),
            run_id=run_id,
            profile=profile,
            status=result.get("status", "unknown"),
            elapsed_s=time.monotonic() - t0,
            endpoint_count=len(endpoints),
            source=source,
            endpoints=[
                {"name": e.get("name"), "method": e.get("method"), "path": e.get("path")} for e in endpoints[:20]
            ],
            error=result.get("error", ""),
            raw=result,
        )
