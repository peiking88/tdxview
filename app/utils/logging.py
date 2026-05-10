"""
Logging utilities — unified logging via loguru, all logs saved to log/ directory.
"""

import sys
from pathlib import Path

from loguru import logger


def setup_logger(level: str = "INFO", log_path: str = "log/tdxview.log", rotation: str = "100 MB", retention: int = 5):
    """Configure the application-wide logger.

    All log files are stored under the log/ directory per project rules.
    """
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    logger.remove()  # Remove default handler

    # Console output
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )

    # File output — structured JSON
    logger.add(
        log_path,
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=rotation,
        retention=retention,
        compression="gz",
        encoding="utf-8",
    )

    return logger


def get_logger(name: str = "tdxview"):
    """Get a named logger instance."""
    return logger.bind(name=name)
