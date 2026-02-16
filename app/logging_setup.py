from __future__ import annotations

import logging

from app.config import get_settings


def setup_logging() -> None:
    settings = get_settings()
    logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO), format='%(message)s')
