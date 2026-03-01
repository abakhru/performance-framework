"""InfluxDBHarness — runs InfluxDB as a subprocess or uses an external URL."""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from api_tests.harness.server import ServerProcessHarness

REPO_ROOT = Path(__file__).parents[2]

# Default InfluxDB connection settings (match docker-compose.yml)
DEFAULT_URL = "http://localhost:8086"
DEFAULT_ORG = "matrix"
DEFAULT_BUCKET = "k6"
DEFAULT_TOKEN = "matrix-k6-token"


class InfluxDBHarness(ServerProcessHarness):
    """InfluxDB harness — supports two modes:

    1. External mode (use_container=False, default):
       Connects to an already-running InfluxDB at `url`.
       Does NOT manage any process — setup/teardown are no-ops on the process.
       Use when InfluxDB is started by docker-compose or the CI environment.

    2. Subprocess mode (binary_path provided):
       Launches influxd as a subprocess. Caller supplies binary_path and own_dir.
       Use for fully isolated component tests.

    Either way, exposes write() and query() for test assertions.
    """

    def __init__(
        self,
        test_case=None,
        url: str = DEFAULT_URL,
        org: str = DEFAULT_ORG,
        bucket: str = DEFAULT_BUCKET,
        token: str = DEFAULT_TOKEN,
        use_subprocess: bool = False,
        **kwargs,
    ):
        self._url = url
        self._org = org
        self._bucket = bucket
        self._token = token
        self._use_subprocess = use_subprocess
        self._http_client: httpx.Client | None = None

        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 8086

        if use_subprocess:
            kwargs.setdefault("binary_path", "influxd")
            super().__init__(test_case, host=host, port=port, **kwargs)
        else:
            # External mode — pass dummy binary_path so ProcessHarness doesn't complain
            kwargs.setdefault("binary_path", "/bin/true")
            super().__init__(test_case, host=host, port=port, **kwargs)

    def Launch(self):  # type: ignore[override]
        if self._use_subprocess:
            super().Launch()
        # External mode: nothing to launch

    def Wait(self):  # type: ignore[override]
        if self._use_subprocess:
            super().Wait()

    def Kill(self):  # type: ignore[override]
        if self._use_subprocess:
            super().Kill()

    def _open_client(self) -> None:
        self._http_client = httpx.Client(
            base_url=self._url,
            headers={"Authorization": f"Token {self._token}"},
            timeout=10.0,
        )

    def _close_client(self) -> None:
        if self._http_client:
            self._http_client.close()
            self._http_client = None

    def health_check(self) -> bool:
        """Return True if InfluxDB /health returns 200."""
        try:
            r = httpx.get(f"{self._url}/health", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    def wait_for_ready(self, timeout: float = 15.0) -> None:
        """Wait until InfluxDB /health returns 200."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.health_check():
                self._open_client()
                return
            time.sleep(0.5)
        raise TimeoutError(f"InfluxDB at {self._url} not ready within {timeout}s")

    def write(self, measurement: str, fields: dict, tags: dict | None = None) -> None:
        """Write a single data point using the InfluxDB v2 line protocol."""
        tag_str = ""
        if tags:
            tag_str = "," + ",".join(f"{k}={v}" for k, v in tags.items())
        field_str = ",".join(f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}" for k, v in fields.items())
        lp = f"{measurement}{tag_str} {field_str}"
        r = self._http_client.post(
            "/api/v2/write",
            params={"org": self._org, "bucket": self._bucket, "precision": "ns"},
            content=lp.encode(),
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
        r.raise_for_status()

    def query(self, flux: str) -> list[dict]:
        """Run a Flux query and return rows as dicts."""
        r = self._http_client.post(
            "/api/v2/query",
            params={"org": self._org},
            json={"query": flux, "type": "flux"},
            headers={"Accept": "application/csv"},
        )
        r.raise_for_status()
        rows = []
        lines = r.text.splitlines()
        if len(lines) < 2:
            return rows
        headers = [h.strip() for h in lines[0].split(",")]
        for line in lines[1:]:
            if line.strip() and not line.startswith("#"):
                values = [v.strip() for v in line.split(",")]
                rows.append(dict(zip(headers, values)))
        return rows

    def __del__(self):
        self._close_client()
