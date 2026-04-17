from __future__ import annotations

import logging
from dataclasses import dataclass

import requests


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HealthcheckResult:
    url: str
    ok: bool
    status_code: int | None = None
    error: str | None = None


def run_healthcheck(url: str, timeout_seconds: int, expected_status: int) -> HealthcheckResult:
    try:
        response = requests.get(url, timeout=timeout_seconds, allow_redirects=True)
        is_ok = response.status_code == expected_status
        return HealthcheckResult(url=url, ok=is_ok, status_code=response.status_code)
    except Exception as exc:
        return HealthcheckResult(url=url, ok=False, error=str(exc))


def log_healthcheck_result(result: HealthcheckResult, expected_status: int) -> None:
    if result.ok:
        logger.info("站点健康检查通过: url=%s status=%s", result.url, result.status_code)
        return

    if result.status_code is not None:
        logger.warning(
            "站点健康检查失败，将冻结删除: url=%s status=%s expected=%s",
            result.url,
            result.status_code,
            expected_status,
        )
        return

    logger.warning("站点健康检查失败，将冻结删除: url=%s error=%s", result.url, result.error)
