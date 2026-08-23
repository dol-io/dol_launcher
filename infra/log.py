from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from .fs import ensure_safe_subdirectory

_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"

_LOGGER_NAME = "dolctl"


class _NoExcStreamHandler(logging.StreamHandler):
    """StreamHandler that omits traceback formatting.

    The file handler keeps the full ``exc_info`` for post-mortem debugging,
    while stderr only shows the message itself so users aren't drowned in
    stack traces for expected ``DolCtlError`` paths.
    """

    def emit(self, record: logging.LogRecord) -> None:
        saved_info = record.exc_info
        saved_text = record.exc_text
        record.exc_info = None
        record.exc_text = None
        try:
            super().emit(record)
        finally:
            record.exc_info = saved_info
            record.exc_text = saved_text


def setup_logging(root: Path | None, verbose: bool = False) -> logging.Logger:
    """Wire up file + stderr handlers for the dolctl logger tree.

    The file handler (INFO+) is attached when *root* points to a writable
    location; failures to create the log directory (read-only roots, bad
    paths) downgrade silently to stderr-only logging. The stderr handler
    is INFO+ when *verbose*, WARNING+ otherwise.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    stderr_handler = _NoExcStreamHandler()
    stderr_handler.setLevel(logging.INFO if verbose else logging.WARNING)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    if root is not None:
        try:
            log_dir = ensure_safe_subdirectory(root, ".dolctl", "logs")
            file_handler = logging.handlers.TimedRotatingFileHandler(
                filename=log_dir / "dolctl.log",
                when="midnight",
                backupCount=14,
                encoding="utf-8",
                utc=True,
            )
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except (OSError, ValueError):
            # Read-only root or permission issue — keep stderr handler only.
            pass

    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``dolctl.`` namespace."""
    if name.startswith(_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


def log_error(root: Path, message: str, exc: Exception | None = None) -> None:
    """Record an error to the dolctl logger.

    The file handler receives the full traceback (when *exc* is provided)
    while stderr only sees the message — see ``_NoExcStreamHandler``.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        setup_logging(root, verbose=False)
    if exc is not None:
        logger.error("%s", message, exc_info=exc)
    else:
        logger.error("%s", message)
