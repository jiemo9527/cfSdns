from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .project_config import REPO_ROOT
from .project_constants import RUNTIME_STATE_FILENAME


logger = logging.getLogger(__name__)
STATE_FILE_PATH = REPO_ROOT / RUNTIME_STATE_FILENAME


@dataclass
class RuntimeState:
    record_anomaly_streaks: dict[str, int] = field(default_factory=dict)


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
    if not isinstance(streaks, dict):
        return RuntimeState()

    normalized_streaks = {str(key): int(value) for key, value in streaks.items() if isinstance(value, int) and value >= 0}
    return RuntimeState(record_anomaly_streaks=normalized_streaks)


def save_runtime_state(state: RuntimeState) -> None:
    payload = {"record_anomaly_streaks": state.record_anomaly_streaks}

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
