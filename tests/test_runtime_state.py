import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.runtime_state import (
    RuntimeState,
    clear_record_state,
    decay_line_pollution_scores,
    get_record_anomaly_streak,
    get_line_pollution_score,
    increment_record_anomaly_streak,
    increment_line_pollution_score,
    is_record_in_rotation_cooldown,
    load_runtime_state,
    mark_record_healthy,
    prune_expired_runtime_state,
    save_runtime_state,
    set_record_rotation_cooldown,
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
        state = RuntimeState(
            record_anomaly_streaks={"www|mobile|1.1.1.1": 2},
            record_rotation_cooldowns={"www|mobile|2.2.2.2": int(time.time()) + 3600},
            line_pollution_scores={"telecom": 2},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            fake_path = Path(temp_dir) / ".cfsdns_state.json"
            with patch("src.runtime_state.STATE_FILE_PATH", fake_path):
                save_runtime_state(state)
                loaded_state = load_runtime_state()

        self.assertEqual(loaded_state.record_anomaly_streaks, state.record_anomaly_streaks)
        self.assertEqual(loaded_state.line_pollution_scores, state.line_pollution_scores)

    def test_rotation_cooldown_expires(self):
        state = RuntimeState()

        with patch("src.runtime_state.time.time", return_value=1000):
            set_record_rotation_cooldown(state, "www", "mobile", "1.1.1.1", duration_hours=1)
            self.assertTrue(is_record_in_rotation_cooldown(state, "www", "mobile", "1.1.1.1"))

        prune_expired_runtime_state(state, now_timestamp=1000 + 3601)
        self.assertFalse(is_record_in_rotation_cooldown(state, "www", "mobile", "1.1.1.1"))

    def test_pollution_score_increment_and_decay(self):
        state = RuntimeState()

        score = increment_line_pollution_score(state, "telecom", score_cap=6)
        self.assertEqual(score, 1)
        score = increment_line_pollution_score(state, "telecom", score_cap=6)
        self.assertEqual(score, 2)
        self.assertEqual(get_line_pollution_score(state, "telecom"), 2)

        decay_line_pollution_scores(state, active_lines={"mobile"})
        self.assertEqual(get_line_pollution_score(state, "telecom"), 1)

        decay_line_pollution_scores(state, active_lines={"mobile"})
        self.assertEqual(get_line_pollution_score(state, "telecom"), 0)
