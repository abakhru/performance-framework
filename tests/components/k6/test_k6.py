"""Component tests for K6Harness.

bd-k6-component: Verify k6 subprocess launches, runs, and exits cleanly.
Run standalone: pytest tests/components/k6/ -v
"""

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).parents[3]


class TestK6Harness(unittest.TestCase):
    """bd-k6-component: K6Harness subprocess lifecycle."""

    def test_k6_version(self):
        """bd-k6-component: k6 binary is accessible and returns version."""
        k6 = REPO_ROOT / "bin" / "k6"
        result = subprocess.run([str(k6), "version"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("k6", result.stdout.lower())

    def test_k6_harness_modifies_args(self):
        """bd-k6-component: K6Harness.ModifyArgs adds --env flags."""
        from api_tests.harness.k6 import K6Harness

        h = K6Harness(
            test_case=None,
            profile="smoke",
            base_url="http://localhost:8080",
            extra_env={"VUS": "2"},
            binary_path=str(REPO_ROOT / "bin" / "k6"),
        )
        args = h.ModifyArgs(["run", "--env", "LOAD_PROFILE=smoke", "k6/main.js"])
        self.assertIn("--env", args)
        env_values = " ".join(args)
        self.assertIn("VUS=2", env_values)

    def test_k6_harness_modifies_env(self):
        """bd-k6-component: K6Harness.ModifyEnv sets K6_INFLUXDB vars."""
        from api_tests.harness.k6 import K6Harness

        h = K6Harness(
            test_case=None,
            profile="smoke",
            binary_path=str(REPO_ROOT / "bin" / "k6"),
        )
        env = h.ModifyEnv({})
        self.assertIn("K6_INFLUXDB_ORGANIZATION", env)
        self.assertIn("K6_INFLUXDB_BUCKET", env)
        self.assertIn("K6_INFLUXDB_TOKEN", env)
