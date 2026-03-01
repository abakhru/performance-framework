"""
tests/ui/conftest.py — pytest configuration for UI tests.

Registers custom markers so pytest doesn't warn about unknown markers:
    @pytest.mark.smoke
    @pytest.mark.regression
    @pytest.mark.sanity

Also provides a session-scoped fixture for shared Playwright browser setup
when tests run through pytest-playwright rather than unittest.TestCase
(UITestCase manages its own lifecycle via setUpClass/tearDownClass).

Skip the entire session if playwright is not installed.
"""

from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "smoke: smoke-level UI tests — fast sanity check")
    config.addinivalue_line("markers", "regression: regression-level UI tests — full suite")
    config.addinivalue_line("markers", "sanity: critical sanity check tests")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip all UI tests if playwright is not installed."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        skip_marker = pytest.mark.skip(reason="playwright not installed — run: just ui-install")
        for item in items:
            if "tests/ui" in str(item.fspath):
                item.add_marker(skip_marker)
