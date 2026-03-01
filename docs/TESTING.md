# Testing Guide

This document describes the test strategy, what each suite covers, and how to run it.

---

## Test Pyramid

```
         ┌─────────┐
         │   e2e   │  Full stack — browser + dashboard + k6 + InfluxDB
         ├─────────┤
         │   api   │  Contract + smoke tests against a live HTTP API
         ├─────────┤
         │  integ  │  Multi-component — dashboard + services (no browser)
         ├─────────┤
         │  comp   │  Per-component isolation (real service, mocked peers)
         ├────┬────┤
         │ ui │unit│  Browser UI tests (Playwright)  ·  Unit tests (no I/O)
         └────┴────┘
```

---

## Suite Breakdown

### Unit tests — `tests/unit/`

No external services. Fast. Run on every `just ci`.

| File | Covers |
|---|---|
| `test_storage.py` | `core/storage.py` — JSON read/write, type coercions |
| `test_influx.py` | `core/influx.py` — line-protocol helpers, query parsing |
| `test_lifecycle.py` | `plugins/performance/runner.py` — SLO checks, badge generation, webhook signing |
| `test_discovery.py` | `plugins/discovery/engine.py` — Postman/HAR/WSDL/OpenAPI parsing |
| `test_visual_qa.py` | `plugins/visual_qa/agents.py` — profile loading, bug parsing, run storage |

```bash
just test-unit         # run unit tests
just test              # alias
```

### Component tests — `tests/components/`

Each component tested in isolation with a real backing service (spun up via testcontainers).

| Directory | Covers |
|---|---|
| `dashboard/` | Dashboard API endpoints |
| `discovery/` | Discovery engine with real HTTP targets |
| `influxdb/` | InfluxDB write/query round-trip |
| `k6/` | k6 subprocess execution |

```bash
just test-components
```

### Integration tests — `tests/integration/`

Multi-component scenarios. Requires InfluxDB to be running (`just influx-up`).

| File | Covers |
|---|---|
| `test_dashboard_full.py` | Full dashboard API lifecycle |
| `test_discovery_to_config.py` | Discover → generate endpoints.json → start run |

```bash
just influx-up
just test-integration
```

### E2E tests — `tests/e2e/`

Full stack: real k6 run, InfluxDB storage, dashboard API, and result retrieval.

```bash
just influx-up
just test-e2e
```

### API tests — `tests/api/`

HTTP contract and smoke tests against a live API target. Set `BASE_URL`.

```bash
BASE_URL=https://api.example.com just test-api
```

### UI tests — `tests/ui/`

Playwright-based browser tests against the dashboard. Requires the dashboard to be running.

```
tests/ui/
├── base/                   # Base page object and test case
├── page_objects/dashboard/ # Page objects (Discover, Endpoints, Execute, Overview, Navigation)
├── smoke/                  # Critical path — navigation, tab switching
└── regression/             # Full regression — form interactions, config saving
```

```bash
just dashboard &            # start dashboard in background
just ui-install             # install Playwright browsers (once)
just test-ui-smoke          # smoke suite only (fastest)
just test-ui-regression     # full regression
just test-ui                # both
just test-ui-headed         # headed mode for debugging
```

---

## Writing Tests

### Rules (enforced by CI)

1. **Atomic and independent** — each test creates its own data and cleans up in `tearDown`. No shared mutable state between tests.
2. **Real services in integration tests** — never mock a database or HTTP service in an integration test. Use testcontainers or a local service.
3. **Traceability** — every test class/module must reference the feature or bug it covers in its docstring.

### Template: Unit test

```python
"""
test_my_feature.py — Unit tests for plugins/my_feature/

Feature: My Feature — bd-xyz
Covers: core business logic, edge cases.
"""

import unittest
from plugins.my_feature.engine import do_something


class TestDoSomething(unittest.TestCase):

    def test_returns_ok_for_valid_input(self):
        """bd-xyz — valid input returns status ok."""
        result = do_something("hello")
        self.assertEqual(result["status"], "ok")

    def test_raises_for_empty_input(self):
        """bd-xyz — empty input raises ValueError."""
        with self.assertRaises(ValueError):
            do_something("")
```

### Template: Parameterised test

```python
from parameterized import parameterized

class TestAuthModes(unittest.TestCase):
    @parameterized.expand([
        ("bearer", "Bearer abc", 200),
        ("no_key", "", 401),
        ("wrong_key", "Bearer bad", 401),
    ])
    def test_auth_mode(self, name, header, expected_status):
        resp = self.client.get("/secure", headers={"Authorization": header})
        self.assertEqual(resp.status_code, expected_status)
```

---

## Coverage

```bash
just test-unit     # runs with coverage measurement
just coverage      # combine + html report → htmlcov/
```

Coverage is configured in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["src"]
omit = ["tests/*"]

[tool.coverage.report]
fail_under = 60
```

---

## CI Gate

```bash
just ci            # lint + typecheck + test (unit)
```

This is what runs on every PR. Full integration/E2E suites run on merge to main.

---

## Test Configuration

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests/unit"]       # default suite
pythonpath = ["src", "."]        # import root
markers = [
    "smoke: smoke-level UI tests",
    "regression: regression-level UI tests",
    "sanity: critical sanity check tests",
]
```

Override `testpaths` on the command line:

```bash
uv run pytest tests/integration/ -v
uv run pytest tests/ui/smoke/ -m smoke -v
```
