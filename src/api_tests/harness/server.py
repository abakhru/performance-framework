"""ServerProcessHarness — language-agnostic base for any local server subprocess."""

from __future__ import annotations

import time

import httpx

from api_tests.framework.harness import ProcessHarness


class ServerProcessHarness(ProcessHarness):
    """Language-agnostic base for any HTTP server that runs as a local subprocess.

    Works for Python, Java, Elixir, Scala, Go — any runtime that binds a TCP port.

    Subclasses must supply binary_path and command_line_args via kwargs.
    Subclasses override ModifyArgs() / ModifyEnv() for runtime-specific flags
    (e.g. JaCoCo for Java, COVERAGE_PROCESS_START for Python).

    Adds two things on top of ProcessHarness:
      - wait_for_ready(): polls IsListening(host, port) until the server is up
      - client property: returns httpx.Client pointed at http://host:port
    """

    def __init__(
        self,
        test_case,
        host: str = "127.0.0.1",
        port: int = 8080,
        **kwargs,
    ):
        # binary_path and command_line_args must come from subclass/caller via kwargs
        super().__init__(test_case, **kwargs)
        self._host = host
        self._port = port

    def wait_for_ready(self, timeout: float = 15.0) -> None:
        """Block until the server port accepts TCP connections.

        Raises TimeoutError if the server does not start within timeout seconds.
        Language-agnostic — uses raw TCP socket via IsListening().
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.IsListening(host=self._host, port=self._port):
                return
            time.sleep(0.25)
        raise TimeoutError(f"{self.__class__.__name__} did not start on {self._host}:{self._port} within {timeout}s")

    @property
    def base_url(self) -> str:
        """Base URL of this server."""
        return f"http://{self._host}:{self._port}"

    @property
    def client(self) -> httpx.Client:
        """Return an httpx.Client pointed at this server.

        Each call creates a new client — caller is responsible for closing it,
        or use as a context manager: with harness.client as c: ...
        """
        return httpx.Client(base_url=self.base_url, timeout=10.0)
