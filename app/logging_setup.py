from __future__ import annotations

import logging


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("botyara")
    if logger.handlers:
        return logger
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return logger
