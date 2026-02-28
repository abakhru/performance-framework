"""TestRunner — orchestrates discovery, test generation, and pytest execution."""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

_SUITE_PATHS: dict[str, str] = {
    "unit": "tests/unit",
    "components": "tests/components",
    "integration": "tests/integration",
    "e2e": "tests/e2e",
    "api": "tests/api",
    "all": "tests",
}


@dataclass
class TestResult:
    name: str
    status: str  # "passed" | "failed" | "error" | "skipped"
    duration_ms: float
    message: str = ""


@dataclass
class TestRunResult:
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_ms: float = 0.0
    suite: str = ""
    results: list[TestResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.errors == 0


# Module-level store for last run result (read by dashboard router)
_last_result: TestRunResult | None = None


def get_last_result() -> TestRunResult | None:
    return _last_result


class TestRunner:
    """Runs a pytest suite and returns a structured result.

    Usage:
        runner = TestRunner()
        result = runner.run(suite="components", base_url="http://localhost:5656")
    """

    def run(
        self,
        suite: str = "api",
        base_url: str = "",
        auth_token: str = "",
        extra_args: list[str] | None = None,
    ) -> TestRunResult:
        """Run pytest for the given suite and return structured results."""
        global _last_result

        suite_path = _SUITE_PATHS.get(suite, suite)
        abs_path = str(REPO_ROOT / suite_path)
        (REPO_ROOT / "out").mkdir(exist_ok=True)

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            abs_path,
            "--tb=short",
            "-q",
            f"--junit-xml={REPO_ROOT}/out/test-results-{suite}.xml",
        ]
        if extra_args:
            cmd += extra_args

        env: dict[str, str] = {}
        import os

        env.update(os.environ)
        if base_url:
            env["BASE_URL"] = base_url
        if auth_token:
            env["AUTH_TOKEN"] = auth_token

        start = time.monotonic()
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
        )
        elapsed_ms = (time.monotonic() - start) * 1000

        result = _parse_pytest_output(proc.stdout + proc.stderr, elapsed_ms, suite)
        result.suite = suite
        _last_result = result
        return result


def _parse_pytest_output(output: str, duration_ms: float, suite: str) -> TestRunResult:
    """Parse pytest -q output for summary counts."""
    import re

    result = TestRunResult(duration_ms=duration_ms, suite=suite)

    for line in output.splitlines():
        line = line.strip()
        # Look for: "3 passed, 1 failed, 2 errors in 0.45s"
        if " passed" in line or " failed" in line or " error" in line:
            p = re.search(r"(\d+) passed", line)
            f = re.search(r"(\d+) failed", line)
            e = re.search(r"(\d+) error", line)
            s = re.search(r"(\d+) skipped", line)
            if p:
                result.passed = int(p.group(1))
            if f:
                result.failed = int(f.group(1))
            if e:
                result.errors = int(e.group(1))
            if s:
                result.skipped = int(s.group(1))

    return result
