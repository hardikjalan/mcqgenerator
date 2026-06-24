"""
logger.py
=========
Centralized logging setup for the MCQ Generator backend.

Usage
-----
    from logger import get_logger, is_debug_mode
    logger = get_logger(__name__)
    logger.info("[EXTRACT] Processing file: %s", filename)
    logger.error("[ERROR] Extraction failed: %s", e)          # known error — no exc_info
    logger.error("[ERROR] Unexpected: %s", e, exc_info=True)  # unexpected — full trace

Log level is controlled via the LOG_LEVEL environment variable (default: INFO).
Set LOG_LEVEL=DEBUG to enable full stack traces and verbose module details.

Log format
----------
    INFO     | [EXTRACT] Processing file: lecture.pdf
    WARNING  | [OCR] API error (attempt 1/3): 503 Service Unavailable
    ERROR    | [ERROR] Unexpected exception: ...
"""

import logging
import os

# Allow overriding log level via environment variable
_LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_NAME, logging.INFO)

# Clean, readable format — level | message
_FORMATTER = logging.Formatter(
    fmt="%(levelname)-8s | %(message)s",
)

# Verbose format for DEBUG mode — adds module name for traceability
_DEBUG_FORMATTER = logging.Formatter(
    fmt="%(levelname)-8s | %(name)s | %(message)s",
)

_initialized = False


def is_debug_mode() -> bool:
    """Return True if the effective log level is DEBUG or lower."""
    return _LOG_LEVEL <= logging.DEBUG


def _setup_root_logger() -> None:
    """Configure the root logger once on first import."""
    global _initialized
    if _initialized:
        return

    root = logging.getLogger("backend")
    root.setLevel(_LOG_LEVEL)

    # Console handler — use verbose format in DEBUG, clean format otherwise
    console_handler = logging.StreamHandler()
    console_handler.setLevel(_LOG_LEVEL)
    console_handler.setFormatter(
        _DEBUG_FORMATTER if is_debug_mode() else _FORMATTER
    )
    root.addHandler(console_handler)

    # Prevent duplicate log entries if uvicorn also sets up logging
    root.propagate = False

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """
    Return a child logger namespaced under 'backend.<name>'.

    Parameters
    ----------
    name : str
        Typically ``__name__`` of the calling module.

    Returns
    -------
    logging.Logger
    """
    _setup_root_logger()
    return logging.getLogger(f"backend.{name}")
