from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from .project_config import REPO_ROOT
from .project_constants import RUNTIME_STATE_FILENAME


logger = logging.getLogger(__name__)
STATE_FILE_PATH = REPO_ROOT / RUNTIME_STATE_FILENAME


@dataclass
class RuntimeState:
    record_anomaly_streaks: dict[str, int] = field(default_factory=dict)
    record_rotation_cooldowns: dict[str, int] = field(default_factory=dict)
    line_pollution_scores: dict[str, int] = field(default_factory=dict)


def make_record_key(rr: str, line: str, ip_address: str) -> str:
    return f"{rr}|{line.lower()}|{ip_address}"


def load_runtime_state() -> RuntimeState:
    if not STATE_FILE_PATH.exists():
        return RuntimeState()

    try:
        payload = json.loads(STATE_FILE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("读取运行时状态失败，将使用空状态: path=%s error=%s", STATE_FILE_PATH, exc)
        return RuntimeState()

    streaks = payload.get("record_anomaly_streaks", {})
    cooldowns = payload.get("record_rotation_cooldowns", {})
    pollution_scores = payload.get("line_pollution_scores", {})
    if not isinstance(streaks, dict):
        return RuntimeState()
    if not isinstance(cooldowns, dict):
        cooldowns = {}
    if not isinstance(pollution_scores, dict):
        pollution_scores = {}

    normalized_streaks = {str(key): int(value) for key, value in streaks.items() if isinstance(value, int) and value >= 0}
    normalized_cooldowns = {str(key): int(value) for key, value in cooldowns.items() if isinstance(value, int) and value > 0}
    normalized_pollution_scores = {
        str(key): int(value)
        for key, value in pollution_scores.items()
        if isinstance(value, int) and value >= 0
    }
    state = RuntimeState(
        record_anomaly_streaks=normalized_streaks,
        record_rotation_cooldowns=normalized_cooldowns,
        line_pollution_scores=normalized_pollution_scores,
    )
    prune_expired_runtime_state(state)
    return state


def save_runtime_state(state: RuntimeState) -> None:
    prune_expired_runtime_state(state)
    payload = {
        "record_anomaly_streaks": state.record_anomaly_streaks,
        "record_rotation_cooldowns": state.record_rotation_cooldowns,
        "line_pollution_scores": state.line_pollution_scores,
    }

    try:
        STATE_FILE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("保存运行时状态失败: path=%s error=%s", STATE_FILE_PATH, exc)


def get_record_anomaly_streak(state: RuntimeState, rr: str, line: str, ip_address: str) -> int:
    return state.record_anomaly_streaks.get(make_record_key(rr, line, ip_address), 0)


def mark_record_healthy(state: RuntimeState, rr: str, line: str, ip_address: str) -> None:
    state.record_anomaly_streaks.pop(make_record_key(rr, line, ip_address), None)


def increment_record_anomaly_streak(state: RuntimeState, rr: str, line: str, ip_address: str) -> int:
    record_key = make_record_key(rr, line, ip_address)
    next_value = state.record_anomaly_streaks.get(record_key, 0) + 1
    state.record_anomaly_streaks[record_key] = next_value
    return next_value


def clear_record_state(state: RuntimeState, rr: str, line: str, ip_address: str) -> None:
    state.record_anomaly_streaks.pop(make_record_key(rr, line, ip_address), None)


def prune_expired_runtime_state(state: RuntimeState, now_timestamp: int | None = None) -> None:
    current_timestamp = now_timestamp if now_timestamp is not None else int(time.time())
    expired_keys = [
        record_key
        for record_key, expires_at in state.record_rotation_cooldowns.items()
        if expires_at <= current_timestamp
    ]
    for record_key in expired_keys:
        state.record_rotation_cooldowns.pop(record_key, None)


def set_record_rotation_cooldown(state: RuntimeState, rr: str, line: str, ip_address: str, duration_hours: int) -> None:
    expires_at = int(time.time()) + duration_hours * 3600
    state.record_rotation_cooldowns[make_record_key(rr, line, ip_address)] = expires_at


def is_record_in_rotation_cooldown(state: RuntimeState, rr: str, line: str, ip_address: str) -> bool:
    prune_expired_runtime_state(state)
    return make_record_key(rr, line, ip_address) in state.record_rotation_cooldowns


def increment_line_pollution_score(state: RuntimeState, line: str, score_cap: int) -> int:
    line_key = line.lower()
    next_score = min(state.line_pollution_scores.get(line_key, 0) + 1, score_cap)
    state.line_pollution_scores[line_key] = next_score
    return next_score


def decay_line_pollution_scores(state: RuntimeState, active_lines: set[str]) -> None:
    normalized_active_lines = {line.lower() for line in active_lines}
    for line_key, score in list(state.line_pollution_scores.items()):
        if line_key in normalized_active_lines:
            continue
        next_score = max(score - 1, 0)
        if next_score == 0:
            state.line_pollution_scores.pop(line_key, None)
        else:
            state.line_pollution_scores[line_key] = next_score


def get_line_pollution_score(state: RuntimeState, line: str) -> int:
    return state.line_pollution_scores.get(line.lower(), 0)
