import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.runtime_state import (
    RuntimeState,
    clear_record_state,
    get_record_anomaly_streak,
    increment_record_anomaly_streak,
    load_runtime_state,
    mark_record_healthy,
    save_runtime_state,
)


class RuntimeStateTests(unittest.TestCase):
    def test_increment_and_clear_record_streak(self):
        state = RuntimeState()

        streak = increment_record_anomaly_streak(state, "www", "mobile", "1.1.1.1")
        self.assertEqual(streak, 1)
        self.assertEqual(get_record_anomaly_streak(state, "www", "mobile", "1.1.1.1"), 1)

        mark_record_healthy(state, "www", "mobile", "1.1.1.1")
        self.assertEqual(get_record_anomaly_streak(state, "www", "mobile", "1.1.1.1"), 0)

        increment_record_anomaly_streak(state, "www", "mobile", "1.1.1.1")
        clear_record_state(state, "www", "mobile", "1.1.1.1")
        self.assertEqual(get_record_anomaly_streak(state, "www", "mobile", "1.1.1.1"), 0)

    def test_load_and_save_runtime_state_roundtrip(self):
        state = RuntimeState(record_anomaly_streaks={"www|mobile|1.1.1.1": 2})

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_path = Path(temp_dir) / ".cfsdns_state.json"
            with patch("src.runtime_state.STATE_FILE_PATH", fake_path):
                save_runtime_state(state)
                loaded_state = load_runtime_state()

        self.assertEqual(loaded_state.record_anomaly_streaks, state.record_anomaly_streaks)
