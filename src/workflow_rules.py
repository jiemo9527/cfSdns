from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field

from .project_constants import (
    GLOBAL_FREEZE_ANOMALY_RATIO,
    GLOBAL_FREEZE_MIN_LINES,
    DETECTION_POINT_PREFIX_TO_LINE,
    FIRST_PASS_MAX_TOTAL_TIME_SECONDS,
    FIRST_PASS_REQUIRED_STATUS,
    MAX_BAD_RECORDS_BEFORE_TRUNCATION,
    MAX_BAD_RECORDS_TO_DELETE,
    MAX_SELECTED_IPS_PER_CARRIER,
    SECOND_PASS_DELETE_MIN_TOTAL_TIME_SECONDS,
)


logger = logging.getLogger(__name__)


@dataclass
class ValidationSummary:
    healthy_records: set[tuple[str, str]] = field(default_factory=set)
    anomalous_records: set[tuple[str, str]] = field(default_factory=set)
    unresolved_anomaly_points: int = 0
    total_points: int = 0
    healthy_points: int = 0
    anomalous_points: int = 0
    lines_seen: set[str] = field(default_factory=set)
    lines_with_healthy: set[str] = field(default_factory=set)
    lines_with_anomaly: set[str] = field(default_factory=set)


def parse_total_time_seconds(total_time_value: str) -> float | None:
    if not isinstance(total_time_value, str) or not total_time_value.endswith("s"):
        return None

    try:
        return float(total_time_value[:-1])
    except (ValueError, TypeError):
        return None


def filter_and_select_ips(json_string: str, count_per_carrier: int = MAX_SELECTED_IPS_PER_CARRIER) -> dict[str, list[str]]:
    """从 IT-Dog 的 JSON 测试结果中为每个运营商筛选 IP。"""
    if not json_string:
        return {"mobile": [], "unicom": [], "telecom": []}

    try:
        results = json.loads(json_string)
    except json.JSONDecodeError:
        logger.error("解析测速结果 JSON 时出错。")
        return {"mobile": [], "unicom": [], "telecom": []}

    qualified_ips = {"mobile": [], "unicom": [], "telecom": []}
    for item in results:
        detection_point = item.get("检测点", "")
        status = item.get("状态", "")
        total_time_seconds = parse_total_time_seconds(item.get("总耗时", ""))
        ip_address = item.get("响应IP", "")

        if not ip_address or ip_address == "解析失败" or status != FIRST_PASS_REQUIRED_STATUS:
            continue
        if total_time_seconds is None or total_time_seconds >= FIRST_PASS_MAX_TOTAL_TIME_SECONDS:
            continue

        for carrier_prefix, line_name in DETECTION_POINT_PREFIX_TO_LINE.items():
            if detection_point.startswith(carrier_prefix):
                qualified_ips[line_name].append(ip_address)
                break

    final_selection = {}
    for carrier, ips in qualified_ips.items():
        unique_ips = sorted(set(ips))
        if len(unique_ips) > count_per_carrier:
            final_selection[carrier] = random.sample(unique_ips, count_per_carrier)
        else:
            final_selection[carrier] = unique_ips

    return final_selection


def _classify_validation_line(detection_point: str) -> str | None:
    for carrier_prefix, line_name in DETECTION_POINT_PREFIX_TO_LINE.items():
        if detection_point.startswith(carrier_prefix):
            return line_name
    return None


def _is_validation_observation_anomalous(status: str, total_time_seconds: float | None) -> bool:
    if status == "失败":
        return True
    if total_time_seconds is None:
        return True
    if total_time_seconds is not None and total_time_seconds >= SECOND_PASS_DELETE_MIN_TOTAL_TIME_SECONDS:
        return True
    return False


def summarize_validation_results(json_string: str) -> ValidationSummary | None:
    try:
        results = json.loads(json_string)
    except json.JSONDecodeError:
        logger.error("解析第二次测速结果的 JSON 时出错。")
        return None

    summary = ValidationSummary()
    record_observations: dict[tuple[str, str], dict[str, int]] = {}

    for item in results:
        line_name = _classify_validation_line(item.get("检测点", ""))
        if line_name is None:
            continue

        ip_address = item.get("响应IP")
        status = item.get("状态", "")
        total_time_seconds = parse_total_time_seconds(item.get("总耗时", ""))
        is_anomalous = _is_validation_observation_anomalous(status, total_time_seconds)

        summary.total_points += 1
        summary.lines_seen.add(line_name)

        if not ip_address or ip_address == "解析失败":
            summary.anomalous_points += 1
            summary.unresolved_anomaly_points += 1
            summary.lines_with_anomaly.add(line_name)
            continue

        record_key = (ip_address, line_name)
        observation = record_observations.setdefault(record_key, {"healthy": 0, "anomalous": 0})

        if is_anomalous:
            summary.anomalous_points += 1
            summary.lines_with_anomaly.add(line_name)
            observation["anomalous"] += 1
        else:
            summary.healthy_points += 1
            summary.lines_with_healthy.add(line_name)
            observation["healthy"] += 1

    for record_key, observation in record_observations.items():
        if observation["healthy"] > 0:
            summary.healthy_records.add(record_key)
        elif observation["anomalous"] > 0:
            summary.anomalous_records.add(record_key)

    return summary


def should_freeze_production_deletions(summary: ValidationSummary | None) -> bool:
    if summary is None or summary.total_points == 0:
        return True

    if summary.healthy_points == 0:
        return True

    if len(summary.lines_seen) < GLOBAL_FREEZE_MIN_LINES:
        return False

    anomaly_ratio = summary.anomalous_points / summary.total_points
    if len(summary.lines_with_anomaly) == len(summary.lines_seen) and not summary.lines_with_healthy:
        return True
    if len(summary.lines_with_anomaly) == len(summary.lines_seen) and anomaly_ratio >= GLOBAL_FREEZE_ANOMALY_RATIO:
        return True
    return False


def collect_bad_records(json_string: str) -> list[dict[str, str]]:
    summary = summarize_validation_results(json_string)
    if summary is None:
        return []

    unique_records = [{"ip": ip_address, "line": line_name} for ip_address, line_name in sorted(summary.anomalous_records)]
    if len(unique_records) > MAX_BAD_RECORDS_BEFORE_TRUNCATION:
        logger.warning(
            "待删除记录超过 %s 条，将只处理前 %s 条。",
            MAX_BAD_RECORDS_BEFORE_TRUNCATION,
            MAX_BAD_RECORDS_TO_DELETE,
        )
        return unique_records[:MAX_BAD_RECORDS_TO_DELETE]
    return unique_records
