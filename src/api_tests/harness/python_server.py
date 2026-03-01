"""PythonServerHarness — ServerProcessHarness with Python coverage instrumentation."""

from __future__ import annotations

import sys
from pathlib import Path

from api_tests.harness.server import ServerProcessHarness

REPO_ROOT = Path(__file__).parents[2]


class PythonServerHarness(ServerProcessHarness):
    """ServerProcessHarness for Python HTTP services.

    Automatically sets binary_path to the current Python interpreter and
    injects COVERAGE_PROCESS_START so coverage.py measures the subprocess.

    Subclasses supply command_line_args and may override ModifyEnv further.

    Example — FastAPI via uvicorn:
        class MyAPIHarness(PythonServerHarness):
            def __init__(self, test_case, port=8000, **kwargs):
                super().__init__(
                    test_case, port=port,
                    command_line_args=["-m", "uvicorn", "myapp.main:app",
                                       "--host", "127.0.0.1", "--port", str(port)],
                    **kwargs,
                )
    """

    def __init__(
        self,
        test_case,
        coverage: bool = True,
        **kwargs,
    ):
        kwargs.setdefault("binary_path", sys.executable)
        super().__init__(test_case, **kwargs)
        self._coverage = coverage

    def ModifyEnv(self, env: dict) -> dict:
        """Inject COVERAGE_PROCESS_START for Python subprocess coverage."""
        _env = super().ModifyEnv(env or {})
        if self._coverage:
            coveragerc = REPO_ROOT / ".coveragerc"
            if coveragerc.exists():
                _env["COVERAGE_PROCESS_START"] = str(coveragerc)
        return _env
