"""Fixtures for discovery component tests (uses respx to mock HTTP calls).

Run standalone: pytest tests/components/discovery/ -v
No real services required.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "dashboard"))
