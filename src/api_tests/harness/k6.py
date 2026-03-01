"""K6Harness — runs k6 as a subprocess for load/performance tests."""

from __future__ import annotations

import os
from pathlib import Path

from api_tests.framework.harness import ProcessHarness

REPO_ROOT = Path(__file__).parents[2]


class K6Harness(ProcessHarness):
    """Manages a k6 subprocess for load testing.

    NOT a server harness — k6 runs to completion, so no wait_for_ready().
    Use Run() to launch-and-wait, or Launch()/Wait() separately.

    Args:
        test_case:    TestCase instance (or None for standalone use)
        profile:      k6 load profile name (smoke, ramp, soak, stress, spike)
        base_url:     Target service URL
        auth_token:   Bearer token for the target service
        extra_env:    Additional k6 --env flags
        influx_url:   InfluxDB URL for metrics output (optional)
    """

    def __init__(
        self,
        test_case,
        profile: str = "smoke",
        base_url: str = "",
        auth_token: str = "",
        extra_env: dict | None = None,
        influx_url: str = "",
        **kwargs,
    ):
        self._profile = profile
        self._base_url = base_url
        self._auth_token = auth_token
        self._extra_env = extra_env or {}
        self._influx_url = influx_url

        k6_binary = kwargs.pop("binary_path", str(REPO_ROOT / "bin" / "k6"))
        script = str(REPO_ROOT / "k6" / "main.js")

        super().__init__(
            test_case,
            binary_path=k6_binary,
            command_line_args=["run", "--env", f"LOAD_PROFILE={profile}", script],
            **kwargs,
        )

    def ModifyArgs(self, args: list) -> list:
        """Add per-run --env flags."""
        extras = []
        for k, v in self._extra_env.items():
            extras += ["--env", f"{k}={v}"]
        if self._influx_url:
            extras += ["--out", f"xk6-influxdb={self._influx_url}"]
        return args + extras

    def ModifyEnv(self, env: dict) -> dict:
        """Inject k6 env vars for base URL, auth, and InfluxDB credentials."""
        _env = super().ModifyEnv(env or {})
        if self._base_url:
            _env["BASE_URL"] = self._base_url
        if self._auth_token:
            _env["AUTH_TOKEN"] = self._auth_token
        _env.setdefault("K6_INFLUXDB_ORGANIZATION", os.environ.get("INFLUXDB_ORG", "matrix"))
        _env.setdefault("K6_INFLUXDB_BUCKET", os.environ.get("INFLUXDB_BUCKET", "k6"))
        _env.setdefault("K6_INFLUXDB_TOKEN", os.environ.get("INFLUXDB_TOKEN", "matrix-k6-token"))
        return _env

    def AssertGoodExitCode(self) -> None:
        """Assert k6 exited 0 (all thresholds passed)."""
        code = self.GetExitCode()
        assert code == 0, f"k6 exited with code {code}. Non-zero means thresholds failed or a script error occurred."
