"""
logger.py
=========
Centralized logging setup for the MCQ Generator backend.

Usage
-----
    from logger import get_logger
    logger = get_logger(__name__)
    logger.info("Processing file: %s", filename)
    logger.error("Extraction failed", exc_info=True)

Log files are written to: backend/logs/backend.log
Console output is also enabled at the level set by the LOG_LEVEL environment
variable (default: INFO).
"""

import logging
import os

# Allow overriding log level via environment variable
_LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_NAME, logging.INFO)

# Format includes timestamp, level, module, and message
_FORMATTER = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_initialized = False


def _setup_root_logger() -> None:
    """Configure the root logger once on first import."""
    global _initialized
    if _initialized:
        return


    root = logging.getLogger("backend")
    root.setLevel(_LOG_LEVEL)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(_LOG_LEVEL)
    console_handler.setFormatter(_FORMATTER)
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
