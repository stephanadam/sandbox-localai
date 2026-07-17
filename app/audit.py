"""Audit logging for relevant transactions and AI responses.

Writes structured, human-readable lines to a rotating file at
``<LOG_DIR>/acmeco.log`` (git-ignored). Every auth event, document upload, and
assistant question/response is recorded here so the local server keeps a full
transaction trail.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from app.config import settings

LOG_FILE = "acmeco.log"
_logger: logging.Logger | None = None


def get_audit_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    os.makedirs(settings.log_dir, exist_ok=True)
    logger = logging.getLogger("acmeco.audit")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = RotatingFileHandler(
            os.path.join(settings.log_dir, LOG_FILE),
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        )
        logger.addHandler(handler)
        # Mirror to the console so `python run.py` output shows the trail too.
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter("AUDIT | %(message)s"))
        logger.addHandler(stream)

    _logger = logger
    return logger


def _truncate(value: object, limit: int = 300) -> str:
    text = str(value).replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def log_event(event: str, **fields: object) -> None:
    """Record one audit line, e.g. ``log_event("login", user="a@b.com")``."""
    parts = " ".join(f"{k}={_truncate(v)!r}" for k, v in fields.items() if v != "")
    get_audit_logger().info(f"{event} {parts}".rstrip())
