# -*- coding: utf-8 -*-
from __future__ import annotations

if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "src"

import asyncio
import logging
import sys
from time import sleep

from . import cf2alidns, getIPFromW3, webTestUnion
from .healthcheck import log_healthcheck_result, run_healthcheck
from .logging_utils import configure_logging
from .process_lock import SingleInstanceLock
from .project_config import RuntimeConfig, load_runtime_config
from .project_constants import (
    CARRIER_DISPLAY_NAMES,
    CONSECUTIVE_ANOMALY_DELETE_THRESHOLD,
    MAX_SURPLUS_PRUNE_PER_LINE_PER_CYCLE,
    MIN_RECOMMENDED_SLEEP_SECONDS,
    PRODUCTION_RECORD_CEILING,
    PRODUCTION_RECORD_FLOOR,
    PRODUCTION_RECORD_TARGET,
    RECOMMENDED_SLEEP_SECONDS,
)
from .runtime_state import (
    RuntimeState,
    clear_record_state,
    increment_record_anomaly_streak,
    load_runtime_state,
    mark_record_healthy,
    save_runtime_state,
)
from .workflow_rules import (
    ValidationSummary,
    filter_and_select_ips,
    should_freeze_production_deletions,
    summarize_validation_results,
)


logger = logging.getLogger(__name__)


def log_selected_ips(selected_ips_by_carrier: dict[str, list[str]]) -> None:
    logger.info("成功筛选出各线路的优质 IP：")
    for carrier, ips in selected_ips_by_carrier.items():
        logger.info("%s (%s 个): %s", CARRIER_DISPLAY_NAMES[carrier], len(ips), ips)


def run_itdog_test(target_host: str, custom_dns: str) -> str | None:
    return asyncio.run(webTestUnion.run_itdog_test(target_host=target_host, custom_dns=custom_dns))


def log_sleep_time_guidance(config: RuntimeConfig) -> None:
    if config.sleep_time < MIN_RECOMMENDED_SLEEP_SECONDS:
        logger.warning(
            "当前 SLEEPTIME=%s 秒偏低，建议生产环境至少 %s 秒，推荐 %s 秒。",
            config.sleep_time,
            MIN_RECOMMENDED_SLEEP_SECONDS,
            RECOMMENDED_SLEEP_SECONDS,
        )


def log_healthcheck_guidance(config: RuntimeConfig) -> None:
    if config.healthcheck_url:
        logger.info(
            "已启用站点健康检查冻结条件: url=%s expected_status=%s timeout=%ss",
            config.healthcheck_url,
            config.healthcheck_expected_status,
            config.healthcheck_timeout_seconds,
        )
        return

    logger.warning("未配置 HEALTHCHECK_URL；发生疑似源站异常时，只能依赖结果特征冻结删除。")


def _count_records_by_line(records: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        line_key = str(record.get("Line", "")).lower()
        if not line_key:
            continue
        counts[line_key] = counts.get(line_key, 0) + 1
    return counts


def _apply_validation_state(config: RuntimeConfig, state: RuntimeState, summary: ValidationSummary) -> list[dict[str, str]]:
    for ip_address, line_name in summary.healthy_records:
        mark_record_healthy(state, config.domain_rr, line_name, ip_address)

    deletion_candidates = []
    for ip_address, line_name in sorted(summary.anomalous_records):
        streak = increment_record_anomaly_streak(state, config.domain_rr, line_name, ip_address)
        logger.info("生产记录异常累计: ip=%s line=%s streak=%s", ip_address, line_name, streak)
        if streak >= CONSECUTIVE_ANOMALY_DELETE_THRESHOLD:
            deletion_candidates.append({"ip": ip_address, "line": line_name})

    return deletion_candidates


def _filter_deletions_by_floor(config: RuntimeConfig, deletion_candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    existing_records = cf2alidns.query_all_domain_records(config.domain_root, subdomain=config.domain_rr)
    line_counts = _count_records_by_line(existing_records)
    allowed_deletions = []

    for candidate in deletion_candidates:
        line_key = candidate["line"].lower()
        remaining_count = line_counts.get(line_key, 0)
        if remaining_count <= PRODUCTION_RECORD_FLOOR:
            logger.warning(
                "跳过删除以保护生产池下限: ip=%s line=%s current=%s floor=%s",
                candidate["ip"],
                candidate["line"],
                remaining_count,
                PRODUCTION_RECORD_FLOOR,
            )
            continue

        allowed_deletions.append(candidate)
        line_counts[line_key] = remaining_count - 1

    return allowed_deletions


def _should_freeze_for_source_healthcheck(config: RuntimeConfig, has_anomalies: bool) -> bool:
    if not has_anomalies or not config.healthcheck_url:
        return False

    result = run_healthcheck(
        url=config.healthcheck_url,
        timeout_seconds=config.healthcheck_timeout_seconds,
        expected_status=config.healthcheck_expected_status,
    )
    log_healthcheck_result(result, config.healthcheck_expected_status)
    return not result.ok


def _prune_surplus_production_records(config: RuntimeConfig, state: RuntimeState, selected_ips_by_carrier: dict[str, list[str]]) -> None:
    pruned_records = cf2alidns.prune_production_dns_records(
        domain_rr=config.domain_rr,
        domain_root=config.domain_root,
        preferred_ips_by_carrier=selected_ips_by_carrier,
        floor_count=PRODUCTION_RECORD_FLOOR,
        ceiling_count=PRODUCTION_RECORD_CEILING,
        max_prune_per_line=MAX_SURPLUS_PRUNE_PER_LINE_PER_CYCLE,
    )
    for record in pruned_records:
        clear_record_state(state, config.domain_rr, record["line"], record["ip"])


def run_single_cycle(config: RuntimeConfig, state: RuntimeState) -> None:
    logger.info("@@@@@ 开始一次完整的 IP 筛选与更新任务 @@@@@")

    logger.info("步骤1：开始从所有来源获取 IP...")
    ct_ip, cm_ip, cu_ip = getIPFromW3.get_cf_ips()
    logger.info("IP 获取完成。移动: %s, 联通: %s, 电信: %s", len(cm_ip), len(cu_ip), len(ct_ip))

    logger.info("步骤2：更新临时域名并进行第一次测速: %s.%s", config.temp_subdomain, config.domain_root)
    initial_ips_dict = {
        "mobile": cm_ip,
        "unicom": cu_ip,
        "telecom": ct_ip,
    }
    cf2alidns.sync_aliyun_dns_records_exact(
        domain_rr=config.temp_subdomain,
        domain_root=config.domain_root,
        ips_by_carrier=initial_ips_dict,
    )

    json_temp = run_itdog_test(target_host=f"{config.temp_subdomain}.{config.domain_root}", custom_dns=config.custom_dns)
    if not json_temp:
        logger.error("第一次 IT-Dog 测速失败，程序中止。")
        return

    logger.info("步骤3：第一次测速完成，开始筛选优质 IP...")
    selected_ips_by_carrier = filter_and_select_ips(json_temp)
    if not any(selected_ips_by_carrier.values()):
        logger.warning("未能从第一次测速结果中筛选出任何符合条件的 IP，程序中止。")
        return

    log_selected_ips(selected_ips_by_carrier)

    logger.info("步骤4：更新生产域名: %s.%s", config.domain_rr, config.domain_root)
    cf2alidns.ensure_production_dns_records(
        domain_rr=config.domain_rr,
        domain_root=config.domain_root,
        ips_by_carrier=selected_ips_by_carrier,
        floor_count=PRODUCTION_RECORD_FLOOR,
        target_count=PRODUCTION_RECORD_TARGET,
        ceiling_count=PRODUCTION_RECORD_CEILING,
    )

    logger.info("步骤5：执行第二次测速并剔除不良记录...")
    json_validate = run_itdog_test(target_host=f"{config.domain_rr}.{config.domain_root}", custom_dns=config.custom_dns)
    if not json_validate:
        logger.warning("第二次验证测速失败，无法执行剔除操作。")
        return

    summary = summarize_validation_results(json_validate)
    if summary is None:
        logger.warning("无法解析第二次测速结果，跳过状态更新与删除。")
        return

    if should_freeze_production_deletions(summary):
        logger.warning(
            "检测到疑似全局异常，冻结本轮生产删除: total_points=%s healthy_points=%s anomalous_points=%s lines_seen=%s",
            summary.total_points,
            summary.healthy_points,
            summary.anomalous_points,
            sorted(summary.lines_seen),
        )
        return

    if _should_freeze_for_source_healthcheck(config, has_anomalies=bool(summary.anomalous_records)):
        return

    records_to_delete = _apply_validation_state(config, state, summary)
    if not records_to_delete:
        logger.info("最终验证测试结果良好，没有需要删除的 DNS 记录。")
    else:
        records_to_delete = _filter_deletions_by_floor(config, records_to_delete)
        logger.info("共找到 %s 条达到删除阈值的 DNS 记录。", len(records_to_delete))
        for record in records_to_delete:
            logger.info("标记待删除记录: ip=%s line=%s", record["ip"], record["line"])
            cf2alidns.delete_record_by_value(
                domain_name=config.domain_root,
                rr=config.domain_rr,
                value=record["ip"],
                line=record["line"],
            )
            clear_record_state(state, config.domain_rr, record["line"], record["ip"])

    _prune_surplus_production_records(config, state, selected_ips_by_carrier)

    save_runtime_state(state)

    logger.info("@@@@@ 本次任务全部执行完毕 @@@@@")


def main() -> int:
    configure_logging(format_string="%(asctime)s - %(levelname)s - [Main] - %(message)s")

    try:
        runtime_config = load_runtime_config()
    except ValueError as exc:
        logger.error("启动失败: %s", exc)
        return 1

    runtime_state = load_runtime_state()
    log_sleep_time_guidance(runtime_config)
    log_healthcheck_guidance(runtime_config)
    instance_lock = SingleInstanceLock()
    if not instance_lock.acquire():
        logger.error("检测到已有实例正在运行，本次启动将退出。")
        return 1

    try:
        try:
            while True:
                try:
                    run_single_cycle(runtime_config, runtime_state)
                except Exception as exc:
                    logger.error("任务执行周期中发生错误: %s", exc, exc_info=True)
                    save_runtime_state(runtime_state)

                logger.info("本轮任务结束，休眠 %s 秒...", runtime_config.sleep_time)
                sleep(runtime_config.sleep_time)
        except KeyboardInterrupt:
            logger.info("接收到停止信号 (Ctrl+C)，程序正在退出。")
            return 0
    finally:
        save_runtime_state(runtime_state)
        instance_lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
