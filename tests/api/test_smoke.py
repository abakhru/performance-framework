"""Auto-generated smoke tests — created from endpoint config at import time.

bd-api-smoke: Verify each discovered endpoint responds within the SLO
(status code + 2000ms response time).

Test plan is built at module import time from k6/config/endpoints.json.
If BASE_URL is not set the whole class is skipped.

Run:
    BASE_URL=https://api.example.com pytest tests/api/test_smoke.py -v
    BASE_URL=https://api.example.com AUTH_TOKEN="Bearer xyz" pytest tests/api/ -v

Skip behaviour:
    - No BASE_URL env var          → entire TestEndpointSmoke class skipped
    - endpoints.json missing/empty → entire TestEndpointSmoke class skipped
    - Individual endpoint 404      → that parametrize case fails (not skipped)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the dashboard and project root are importable
REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

from api_tests.generator import TestGenerator  # noqa: E402


def _safe_entry_id(entry) -> str:
    """Return a pytest-safe ID string for a TestEntry."""
    safe = entry.name.replace("/", "_").replace(" ", "_").replace("-", "_")
    return f"{entry.method}_{safe}"[:60]


def _load_plan():
    """Build the test plan at import time from endpoints.json.

    Returns None if no plan is available (missing file, empty list, etc.).
    The caller must handle None by marking tests as skipped.
    """
    try:
        gen = TestGenerator.from_endpoints_json()
        return gen.generate_test_plan()
    except Exception:
        return None


# Build once at module import — same pattern as artemis create_endpoint_tests()
_plan = _load_plan()
_entries = _plan.entries if _plan else []


@pytest.mark.skipif(not _entries, reason="No endpoints.json or empty endpoint list")
class TestEndpointSmoke:
    """bd-api-smoke: Smoke test each endpoint in the active endpoint config.

    Parametrized at import time from endpoints.json — identical to the
    artemis create_endpoint_tests() pattern but using pytest.mark.parametrize.
    Each test verifies: expected HTTP status + response within 2000ms SLO.
    """

    @pytest.mark.smoke
    @pytest.mark.parametrize(
        "entry",
        _entries,
        ids=[_safe_entry_id(e) for e in _entries] if _entries else [],
    )
    def test_endpoint_responds(self, entry, api_client) -> None:
        """bd-api-smoke: endpoint responds with expected status within 2000ms SLO."""
        if entry.endpoint_type == "graphql":
            r = api_client.post(
                entry.path,
                json={"query": entry.query or "{__typename}", "variables": entry.variables},
            )
        else:
            method = getattr(api_client, entry.method.lower(), None)
            if method is None:
                pytest.skip(f"Unsupported HTTP method: {entry.method}")
            kwargs: dict = {}
            if entry.body and entry.method in ("POST", "PUT", "PATCH"):
                kwargs["json"] = entry.body
            r = method(entry.path, **kwargs)

        assert r.status_code == entry.expected_status, (
            f"{entry.name} [{entry.method} {entry.path}]: "
            f"expected {entry.expected_status}, got {r.status_code}"
        )
        elapsed_ms = r.elapsed.total_seconds() * 1000
        assert elapsed_ms < 2000, (
            f"{entry.name}: response time {elapsed_ms:.0f}ms exceeded 2000ms SLO"
        )
