from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .project_constants import (
    CUSTOM_DNS_SERVER,
    DEFAULT_HEALTHCHECK_EXPECT_STATUS,
    DEFAULT_HEALTHCHECK_TIMEOUT_SECONDS,
    DEFAULT_SLEEP_SECONDS,
    TEMP_SUBDOMAIN,
)


_env_loaded = False
SRC_DIR = Path(__file__).resolve().parent
REPO_ROOT = SRC_DIR.parent


def load_runtime_env() -> None:
    global _env_loaded

    if _env_loaded:
        return

    src_env_path = SRC_DIR / ".env"
    root_env_path = REPO_ROOT / ".env"

    if src_env_path.exists():
        load_dotenv(src_env_path, override=False)

    if root_env_path.exists():
        load_dotenv(root_env_path, override=True)

    _env_loaded = True


@dataclass(frozen=True)
class RuntimeConfig:
    domain_rr: str
    domain_root: str
    sleep_time: int
    temp_subdomain: str = TEMP_SUBDOMAIN
    custom_dns: str = CUSTOM_DNS_SERVER
    healthcheck_url: str | None = None
    healthcheck_timeout_seconds: int = DEFAULT_HEALTHCHECK_TIMEOUT_SECONDS
    healthcheck_expected_status: int = DEFAULT_HEALTHCHECK_EXPECT_STATUS


def load_runtime_config() -> RuntimeConfig:
    load_runtime_env()

    domain_rr = os.getenv("domain_rr")
    domain_root = os.getenv("domain_root")
    sleep_time = int(os.getenv("SLEEPTIME", str(DEFAULT_SLEEP_SECONDS)))
    healthcheck_url = os.getenv("HEALTHCHECK_URL")
    healthcheck_timeout_seconds = int(
        os.getenv("HEALTHCHECK_TIMEOUT_SECONDS", str(DEFAULT_HEALTHCHECK_TIMEOUT_SECONDS))
    )
    healthcheck_expected_status = int(
        os.getenv("HEALTHCHECK_EXPECT_STATUS", str(DEFAULT_HEALTHCHECK_EXPECT_STATUS))
    )

    missing_values = []
    if not domain_rr:
        missing_values.append("domain_rr")
    if not domain_root:
        missing_values.append("domain_root")

    if missing_values:
        raise ValueError(f"缺少必要环境变量: {', '.join(missing_values)}")

    assert domain_rr is not None
    assert domain_root is not None

    return RuntimeConfig(
        domain_rr=domain_rr,
        domain_root=domain_root,
        sleep_time=sleep_time,
        healthcheck_url=healthcheck_url,
        healthcheck_timeout_seconds=healthcheck_timeout_seconds,
        healthcheck_expected_status=healthcheck_expected_status,
    )


def get_aliyun_credentials() -> tuple[str | None, str | None]:
    load_runtime_env()
    return os.getenv("ALIYUN_ACCESS_KEY_ID"), os.getenv("ALIYUN_ACCESS_KEY_SECRET")


def get_package_num() -> int:
    load_runtime_env()
    return int(os.getenv("ALIYUN_PACKAGE_NUM", "100"))
