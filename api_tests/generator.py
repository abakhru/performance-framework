"""TestGenerator — converts endpoint config to a typed TestPlan.

Bridges the existing endpoint discovery (discovery.py) and the SmokeTestCase
machinery. Can load from endpoints.json or from a live discover_url() call.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


@dataclass
class TestEntry:
    """A single endpoint to test."""

    name: str
    method: str
    path: str
    group: str
    endpoint_type: str  # "rest" or "graphql"
    expected_status: int = 200
    query: str = ""  # GraphQL query string
    variables: dict = field(default_factory=dict)
    body: dict = field(default_factory=dict)
    checks: dict = field(default_factory=dict)


@dataclass
class TestPlan:
    """A collection of TestEntry items ready for test generation."""

    service: str
    base_url: str
    entries: list[TestEntry]

    def __len__(self) -> int:
        return len(self.entries)


def _safe_name(text: str) -> str:
    """Convert an arbitrary string to a valid Python identifier."""
    s = re.sub(r"[^a-zA-Z0-9_]", "_", text)
    s = re.sub(r"_+", "_", s).strip("_").lower()
    return s or "endpoint"


class TestGenerator:
    """Generates a TestPlan from an endpoint config dict or endpoints.json file.

    Usage::

        # From saved endpoints.json
        gen = TestGenerator.from_endpoints_json()
        plan = gen.generate_test_plan()

        # From a live URL
        gen = TestGenerator.from_discovery("https://api.example.com", token="Bearer ...")
        plan = gen.generate_test_plan()

        # Write a test file
        gen.write_test_file(plan, Path("tests/api/test_generated.py"))
    """

    __test__ = False  # tell pytest not to collect this class

    def __init__(self, config: dict, base_url: str = ""):
        self._config = config
        self._base_url = base_url

    @classmethod
    def from_endpoints_json(cls, path: Path | None = None) -> TestGenerator:
        """Load from k6/config/endpoints.json (default) or a custom path."""
        p = path or (REPO_ROOT / "k6" / "config" / "endpoints.json")
        config = json.loads(p.read_text())
        return cls(config, base_url="")

    @classmethod
    def from_config_dict(cls, config: dict, base_url: str = "") -> TestGenerator:
        """Load from an already-parsed endpoint config dict."""
        return cls(config, base_url=base_url)

    @classmethod
    def from_discovery(cls, url: str, token: str = "") -> TestGenerator:
        """Run auto-discovery against a live URL and build a generator."""
        # Import dashboard discovery — works when dashboard/ is on PYTHONPATH
        sys.path.insert(0, str(REPO_ROOT / "dashboard"))
        from discovery import discover_url  # type: ignore[import]

        config = discover_url(url, token=token)
        return cls(config, base_url=url)

    def generate_test_plan(self) -> TestPlan:
        """Convert the endpoint config into a TestPlan."""
        service = self._config.get("service", "unknown")
        entries: list[TestEntry] = []

        for ep in self._config.get("endpoints", []):
            checks = ep.get("checks", {})
            expected_status = checks.get("status", 200)

            entry = TestEntry(
                name=ep.get("name", "unnamed"),
                method=ep.get("method", "GET").upper(),
                path=ep.get("path", "/"),
                group=ep.get("group", "default"),
                endpoint_type=ep.get("type", "rest"),
                expected_status=expected_status,
                query=ep.get("query", ""),
                variables=ep.get("variables", {}),
                body=ep.get("body", {}),
                checks=checks,
            )
            entries.append(entry)

        return TestPlan(service=service, base_url=self._base_url, entries=entries)

    def write_test_file(self, plan: TestPlan, output: Path) -> None:
        """Emit a test_generated.py file for the given plan."""
        output.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            '"""Auto-generated smoke tests — do not edit by hand.',
            "Regenerate with: python -m api_tests.generator",
            '"""',
            "",
            "from __future__ import annotations",
            "import os",
            "import sys",
            "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'api_tests'))",
            "",
            "from api_tests.framework.smoketestcase import SmokeTestCase, create_tests",
            "",
            'DOMAIN = [os.environ.get("BASE_URL", "http://localhost:5656")]',
            "PATH = [",
        ]
        for entry in plan.entries:
            lines.append(f"    {entry.path!r},  # {entry.name}")
        lines += [
            "]",
            "EXPECTED_OUTPUT = [{}]",
            "",
            "create_tests(DOMAIN, PATH, EXPECTED_OUTPUT)",
            "",
            "",
            "class GeneratedSmokeTest(SmokeTestCase):",
            f'    """Smoke tests for {plan.service} — {len(plan)} endpoints."""',
            "",
        ]
        output.write_text("\n".join(lines))
        print(f"[generator] Wrote {len(plan)} test cases to {output}")
