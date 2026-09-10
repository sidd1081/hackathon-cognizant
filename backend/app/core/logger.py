"""Minimal, centralized logging setup for the backend."""

from __future__ import annotations

import logging

from app.core.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_configured = False


def configure_logging() -> None:
    """Configure root logging once, using the level from settings."""
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=settings.log_level.upper(),
        format=_LOG_FORMAT,
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger, ensuring logging is configured first."""
    configure_logging()
    return logging.getLogger(name)
