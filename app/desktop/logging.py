"""Windowed builds have no console; keep bounded, redacted portable logs."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.paths import portable_path


class SecretFilter(logging.Filter):
    def __init__(self, secrets=()):
        super().__init__()
        self.secrets = tuple(value for value in secrets if value)

    def filter(self, record):
        # Never retain exception strings from providers/configuration in logs.
        message = record.getMessage()
        for value in self.secrets:
            message = message.replace(value, "[REDACTED]")
        record.msg, record.args = message, ()
        if record.exc_info:
            record.msg += " (" + record.exc_info[0].__name__ + ")"
            record.exc_info = None
        # Records may already have formatted exception text from another handler.
        record.exc_text = None
        return True


def configure_logging(root: Path):
    directory = portable_path(root, root / "logs")
    directory.mkdir(exist_ok=True)
    destination = portable_path(root, directory / "memory-os.log")
    handler = RotatingFileHandler(destination, maxBytes=2*1024*1024, backupCount=3, encoding="utf-8")
    redaction = SecretFilter()
    handler.addFilter(redaction)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "pywebview"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    return redaction
