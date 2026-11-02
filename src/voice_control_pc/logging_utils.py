"""Bounded UTF-8 logs with timestamps and clean handler lifecycle."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(
            {
                "time": datetime.fromtimestamp(record.created).astimezone().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            },
            ensure_ascii=False,
        )


def setup_logging(level: str, text_log_path: Path, jsonl_log_path: Path) -> logging.Logger:
    logger = logging.getLogger("lumo")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    logger.propagate = False
    for path, formatter in (
        (text_log_path, logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")),
        (jsonl_log_path, JsonFormatter()),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger
