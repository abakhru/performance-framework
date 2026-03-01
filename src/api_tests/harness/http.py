"""HTTPHarness — wraps httpx.Client for any external HTTP service."""

from __future__ import annotations

import httpx

from api_tests.framework.harness import Harness


class HTTPHarness(Harness):
    """Wraps an httpx.Client for any external HTTP service.

    Use when you do NOT control the server process (remote API, third-party service).
    For local servers under test use ServerProcessHarness instead.

    Lifecycle: call setup() before use, teardown() after. Supports context manager.
    """

    def __init__(
        self,
        test_case=None,
        base_url: str = "",
        headers: dict | None = None,
        timeout: float = 10.0,
    ):
        super().__init__(test_case)
        self._base_url = base_url
        self._headers = headers or {}
        self._timeout = timeout
        self._client: httpx.Client | None = None

    def setup(self) -> None:
        """Open the httpx client."""
        self._client = httpx.Client(
            base_url=self._base_url,
            headers=self._headers,
            timeout=self._timeout,
        )

    def teardown(self) -> None:
        """Close the httpx client."""
        if self._client:
            self._client.close()
            self._client = None

    def health_check(self) -> bool:
        """Return True if the base URL is reachable."""
        try:
            r = self._client.get("/")
            return r.status_code < 500
        except Exception:
            return False

    def __enter__(self) -> HTTPHarness:
        self.setup()
        return self

    def __exit__(self, *_) -> None:
        self.teardown()

    # HTTP convenience methods

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self._client.get(path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self._client.post(path, **kwargs)

    def put(self, path: str, **kwargs) -> httpx.Response:
        return self._client.put(path, **kwargs)

    def delete(self, path: str, **kwargs) -> httpx.Response:
        return self._client.delete(path, **kwargs)

    def patch(self, path: str, **kwargs) -> httpx.Response:
        return self._client.patch(path, **kwargs)

    def graphql(self, query: str, variables: dict | None = None, path: str = "/graphql") -> httpx.Response:
        """POST a GraphQL query."""
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables
        return self._client.post(path, json=payload)
