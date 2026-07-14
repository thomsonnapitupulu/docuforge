"""
Structured logging configuration for DocuForge.

Call `configure_logging()` once at process startup (done in api/main.py), then
get a bound logger anywhere with `get_logger(__name__)`.
"""

import logging
import sys

import structlog

from core.config import get_settings

_configured = False


def configure_logging() -> None:
    """Configure structlog + stdlib logging. Safe to call multiple times."""
    global _configured
    if _configured:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str = "") -> structlog.BoundLogger:
    return structlog.get_logger(name)
