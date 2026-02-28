"""Fixtures for k6 component tests.

Requires: bin/k6 binary (run: just build).
Run standalone: pytest tests/components/k6/ -v
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(REPO_ROOT))


def pytest_configure(config):
    """Skip k6 tests if bin/k6 is not built."""
    k6_bin = REPO_ROOT / "bin" / "k6"
    if not k6_bin.exists():
        pytest.skip("bin/k6 not found — run: just build", allow_module_level=True)
