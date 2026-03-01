"""HTTPTestCase and MultiComponentTestCase — extend the ported luna TestCase.

These are built on top of api_tests.framework.testcase.TestCase (ported from luna).
They handle non-process harnesses (HTTP clients, multi-component integration).
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from api_tests.framework.testcase import TestCase
from api_tests.harness.http import HTTPHarness


class HTTPTestCase(TestCase):
    """TestCase for external HTTP services using HTTPHarness.

    Use when the service under test is external (not a subprocess you control).
    For local server subprocesses, use AbstractComponentTestCase + ServerProcessHarness.

    Class variables to set in subclass:
        HARNESS_FACTORY: HTTPHarness subclass to instantiate (default: HTTPHarness)
        BASE_URL:        Base URL of the service
        HEADERS:         Default request headers
        TIMEOUT_SECS:    Request timeout in seconds
    """

    HARNESS_FACTORY: ClassVar[type[HTTPHarness]] = HTTPHarness
    BASE_URL: ClassVar[str] = ""
    HEADERS: ClassVar[dict] = {}
    TIMEOUT_SECS: ClassVar[float] = 10.0

    def setUp(self) -> None:
        TestCase.setUp(self)
        self.harness: HTTPHarness = self.HARNESS_FACTORY(
            test_case=self,
            base_url=self.BASE_URL,
            headers=self.HEADERS,
            timeout=self.TIMEOUT_SECS,
        )
        self.harness.setup()
        self.RunTestCaseSpecificSetup()

    def tearDown(self) -> None:
        self.RunTestCaseSpecificTearDown()
        self.harness.teardown()
        TestCase.tearDown(self)

    # Shared HTTP assertions

    def assert_status(self, response: httpx.Response, expected: int, msg: str = "") -> None:
        """Assert HTTP status code equals expected."""
        self.assertEqual(
            response.status_code,
            expected,
            msg or f"Expected HTTP {expected}, got {response.status_code}. Body: {response.text[:200]}",
        )

    def assert_response_time(self, response: httpx.Response, max_ms: float) -> None:
        """Assert response time is within max_ms milliseconds."""
        elapsed_ms = response.elapsed.total_seconds() * 1000
        self.assertLessEqual(
            elapsed_ms,
            max_ms,
            f"Response time {elapsed_ms:.1f}ms exceeded {max_ms}ms for {response.url}",
        )

    def assert_schema(self, response: httpx.Response, required_keys: list[str]) -> None:
        """Assert response JSON contains all required_keys at top level."""
        data = response.json()
        self.assertIsInstance(data, dict, "Expected JSON object response")
        for key in required_keys:
            self.assertIn(key, data, f"Missing key '{key}' in response: {list(data.keys())}")

    def assert_ok(self, response: httpx.Response) -> None:
        """Assert 2xx status code."""
        self.assertLess(
            response.status_code,
            300,
            f"Expected 2xx, got {response.status_code}. Body: {response.text[:200]}",
        )


class MultiComponentTestCase(TestCase):
    """TestCase for integration tests that compose multiple harnesses.

    HARNESS_FACTORIES maps a name to a (HarnessClass, kwargs_dict) tuple.
    All harnesses are set up in setUp() and torn down in tearDown().

    For harnesses with dynamic config (e.g. container URLs only known at runtime),
    use a @pytest.fixture(autouse=True) to inject pre-built harnesses into
    self.harnesses before individual tests run.

    Example:
        class TestDiscovery(MultiComponentTestCase):
            HARNESS_FACTORIES = {
                "dashboard": (FastAPIHarness, {"port": 5656}),
                "influx":    (InfluxDBHarness, {"url": "http://localhost:8086"}),
            }

            def test_endpoint_stored(self):
                r = self.h("dashboard").client.post("/discover/url", json={"url": "..."})
                self.assert_status(r, 200)
    """

    HARNESS_FACTORIES: ClassVar[dict[str, tuple[type, dict]]] = {}

    def setUp(self) -> None:
        TestCase.setUp(self)
        self.harnesses: dict[str, Any] = {}
        for name, (cls, kwargs) in self.HARNESS_FACTORIES.items():
            h = cls(test_case=self, **kwargs)
            h.setup() if hasattr(h, "setup") else None
            self.harnesses[name] = h
        self.RunTestCaseSpecificSetup()

    def h(self, name: str) -> Any:
        """Return the harness registered under name."""
        harness = self.harnesses.get(name)
        self.assertIsNotNone(harness, f"No harness named '{name}'. Available: {list(self.harnesses)}")
        return harness

    def tearDown(self) -> None:
        self.RunTestCaseSpecificTearDown()
        for h in reversed(list(self.harnesses.values())):
            try:
                if hasattr(h, "teardown"):
                    h.teardown()
                elif hasattr(h, "is_launched") and h.is_launched:
                    h.Kill()
                    h.Wait()
            except Exception:
                pass
        TestCase.tearDown(self)

    # Delegate common assertions to HTTPTestCase for convenience
    def assert_status(self, response: httpx.Response, expected: int, msg: str = "") -> None:
        self.assertEqual(
            response.status_code,
            expected,
            msg or f"Expected HTTP {expected}, got {response.status_code}. Body: {response.text[:200]}",
        )

    def assert_ok(self, response: httpx.Response) -> None:
        self.assertLess(response.status_code, 300, f"Expected 2xx, got {response.status_code}")
