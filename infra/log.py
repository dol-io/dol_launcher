from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from .fs import ensure_dir

_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"

_LOGGER_NAME = "dolctl"
_configured = False


def setup_logging(root: Path | None, verbose: bool = False) -> logging.Logger:
    """Wire up file + stderr handlers for the dolctl logger tree.

    File handler (INFO+) is always attached when *root* is given; stderr
    handler is INFO+ when *verbose*, WARNING+ otherwise. Calling this
    function more than once replaces previously attached handlers so the
    log destination tracks the active root.
    """
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    stderr_handler = logging.StreamHandler()
    stderr_handler.setLevel(logging.INFO if verbose else logging.WARNING)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    if root is not None:
        log_dir = root / ".dolctl" / "logs"
        ensure_dir(log_dir)
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

    # Stop messages from propagating to the root logger (which httpx etc.
    # may also attach handlers to).
    logger.propagate = False
    _configured = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the `dolctl.` namespace."""
    if name.startswith(_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


def log_error(root: Path, message: str, exc: Exception | None = None) -> None:
    """Record an error to the dolctl logger.

    Kept for backwards compatibility with the previous ad-hoc API; new code
    should use ``get_logger(__name__).exception(...)`` directly.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        # No setup yet; attach a minimal file handler so failures are still
        # recorded when commands abort before setup_logging runs.
        setup_logging(root, verbose=False)
    if exc is not None:
        logger.error("%s", message, exc_info=exc)
    else:
        logger.error("%s", message)
