
"""Loguru-based logger with console + file sinks."""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from .config import settings


def setup_logger() -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    log_dir: Path = settings.ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "app_{time:YYYYMMDD}.log",
        level=settings.LOG_LEVEL,
        rotation="100 MB",
        retention="14 days",
        encoding="utf-8",
        enqueue=True,
    )


setup_logger()

__all__ = ["logger"]
