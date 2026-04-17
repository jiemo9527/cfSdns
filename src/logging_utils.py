from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, cast


UTC_PLUS_8 = timezone(timedelta(hours=8))


def _east8_converter(timestamp: float | None):
    safe_timestamp = timestamp if timestamp is not None else datetime.now(tz=UTC_PLUS_8).timestamp()
    return datetime.fromtimestamp(safe_timestamp, tz=UTC_PLUS_8).timetuple()


def configure_logging(level: int = logging.INFO, format_string: str | None = None) -> None:
    logging.Formatter.converter = cast(Any, staticmethod(_east8_converter))
    logging.basicConfig(
        level=level,
        format=format_string or "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        force=True,
    )
