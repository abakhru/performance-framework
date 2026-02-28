"""Auto-generated smoke tests from endpoints.json.

bd-api-smoke: Verify each discovered endpoint responds within SLO.
Requires: BASE_URL env var pointing at the target service.
Run: BASE_URL=https://api.example.com pytest tests/api/test_smoke.py -v
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

from api_tests.generator import TestGenerator  # noqa: E402


def _load_plan():
    """Load the test plan from endpoints.json."""
    try:
        gen = TestGenerator.from_endpoints_json()
        return gen.generate_test_plan()
    except Exception:
        return None


_plan = _load_plan()
_entries = _plan.entries if _plan else []


@pytest.mark.skipif(not _entries, reason="No endpoints.json or empty endpoint list")
class TestEndpointSmoke:
    """bd-api-smoke: Smoke test each endpoint from the active endpoint config."""

    @pytest.mark.parametrize(
        "entry",
        _entries,
        ids=[e.name for e in _entries] if _entries else [],
    )
    def test_endpoint_responds(self, entry, api_client):
        """bd-api-smoke: Endpoint responds with expected status within 2000ms."""
        if entry.endpoint_type == "graphql":
            r = api_client.post(
                entry.path,
                json={"query": entry.query, "variables": entry.variables},
            )
        else:
            method = getattr(api_client, entry.method.lower())
            kwargs = {}
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
