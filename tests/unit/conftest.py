"""
conftest.py — Shared pytest fixtures for the k6 dashboard test suite.
"""

import sys
from pathlib import Path

import pytest

# src/ is the Python root for all packages (core, plugins, api_tests, cli, dashboard)
_SRC = Path(__file__).parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


@pytest.fixture
def tmp_state_dir(tmp_path):
    """Temporary directory for dashboard state files."""
    d = tmp_path / "state"
    d.mkdir()
    return d


@pytest.fixture
def sample_endpoints():
    """Minimal valid endpoint config dict."""
    return {
        "service": "Test",
        "endpoints": [
            {
                "name": "Foo",
                "group": "g1",
                "type": "rest",
                "method": "GET",
                "path": "/foo",
                "weight": 1,
                "checks": {"status": 200},
            }
        ],
        "setup": [],
        "teardown": [],
    }


@pytest.fixture
def sample_postman():
    """Minimal Postman collection dict."""
    return {
        "item": [
            {
                "name": "List",
                "request": {
                    "method": "GET",
                    "url": {"path": ["api", "v1", "objects"]},
                    "body": {},
                },
            }
        ]
    }


@pytest.fixture
def sample_postman_graphql():
    """Postman collection with a GraphQL request."""
    return {
        "item": [
            {
                "name": "Get User",
                "request": {
                    "method": "POST",
                    "url": {"path": ["graphql"]},
                    "body": {
                        "mode": "graphql",
                        "graphql": {
                            "query": "{ user { id name } }",
                            "variables": "{}",
                        },
                    },
                },
            }
        ]
    }


@pytest.fixture
def sample_openapi_spec():
    """Minimal OpenAPI 3 spec with two paths."""
    return {
        "openapi": "3.0.0",
        "paths": {
            "/api/users": {
                "get": {
                    "operationId": "listUsers",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "createUser",
                    "responses": {"201": {"description": "Created"}},
                },
            },
            "/api/users/{id}": {
                "get": {
                    "operationId": "getUser",
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
    }
