import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.healthcheck import run_healthcheck


class HealthcheckTests(unittest.TestCase):
    def test_run_healthcheck_returns_ok_for_expected_status(self):
        fake_response = Mock(status_code=200)

        with patch("src.healthcheck.requests.get", return_value=fake_response):
            result = run_healthcheck("https://example.com/health", timeout_seconds=5, expected_status=200)

        self.assertTrue(result.ok)
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.error)

    def test_run_healthcheck_returns_error_on_exception(self):
        with patch("src.healthcheck.requests.get", side_effect=RuntimeError("boom")):
            result = run_healthcheck("https://example.com/health", timeout_seconds=5, expected_status=200)

        self.assertFalse(result.ok)
        self.assertIsNone(result.status_code)
        self.assertEqual(result.error, "boom")
