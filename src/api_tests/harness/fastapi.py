"""FastAPIHarness — runs the dashboard FastAPI app via uvicorn as a subprocess."""

from __future__ import annotations

from pathlib import Path

from api_tests.harness.python_server import PythonServerHarness

REPO_ROOT = Path(__file__).parents[2]


class FastAPIHarness(PythonServerHarness):
    """Runs the performance-framework dashboard via uvicorn as a real subprocess.

    Inherits Python coverage instrumentation from PythonServerHarness.
    Use in component tests and integration tests where you need the real
    server startup sequence (env loading, InfluxDB init, plugin hooks).

    Usage in conftest.py:
        @pytest.fixture(scope="module")
        def dashboard_harness(tmp_path):
            h = FastAPIHarness(test_case=None, own_dir=str(tmp_path))
            h.Launch()
            h.wait_for_ready()
            yield h
            h.Terminate()
            h.Wait()
    """

    def __init__(
        self,
        test_case,
        port: int = 5656,
        coverage: bool = True,
        **kwargs,
    ):
        super().__init__(
            test_case,
            port=port,
            coverage=coverage,
            command_line_args=[
                "-m",
                "uvicorn",
                "dashboard.server:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            **kwargs,
        )

    def ModifyEnv(self, env: dict) -> dict:
        _env = super().ModifyEnv(env or {})
        _env["PYTHONPATH"] = str(REPO_ROOT)
        return _env
