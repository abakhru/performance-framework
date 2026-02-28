"""API smoke test fixtures — target any live HTTP API.

Set BASE_URL and AUTH_TOKEN environment variables before running.
Run: BASE_URL=https://api.example.com pytest tests/api/ -v
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))


@pytest.fixture(scope="session")
def base_url() -> str:
    url = os.environ.get("BASE_URL", "")
    if not url:
        pytest.skip("BASE_URL env var not set — set it to run API smoke tests")
    return url


@pytest.fixture(scope="session")
def auth_token() -> str:
    return os.environ.get("AUTH_TOKEN", "")


@pytest.fixture(scope="session")
def api_client(base_url, auth_token):
    """HTTPHarness pointed at the target API."""
    import httpx

    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    client = httpx.Client(base_url=base_url, headers=headers, timeout=15.0)
    yield client
    client.close()
