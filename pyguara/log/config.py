"""Logging configuration for PyGuara.

This module provides a centralized logging setup for the PyGuara game engine.
All pyguara modules should use logging instead of print() statements.

Example:
    >>> import logging
    >>> from pyguara.log import setup_logging, get_logger
    >>>
    >>> # At application startup
    >>> setup_logging(level=logging.INFO)
    >>>
    >>> # In modules
    >>> logger = get_logger(__name__)
    >>> logger.info("Scene loaded successfully")
    >>> logger.warning("Resource not found, using fallback")
    >>> logger.error("Critical error occurred", exc_info=True)
"""

import logging
import sys
from pathlib import Path
from typing import Optional


# Default log format
DEFAULT_FORMAT = "[%(levelname)s] [%(name)s] %(message)s"

# Default log file path (relative to cwd)
DEFAULT_LOG_FILE = "pyguara.log"


def setup_logging(
    level: int = logging.INFO,
    format_string: str = DEFAULT_FORMAT,
    log_file: Optional[str] = None,
    file_level: Optional[int] = None,
) -> None:
    """Configure the root logger for PyGuara.

    This should be called once at application startup before any logging occurs.
    It sets up console output and optionally file output with appropriate
    formatters and levels.

    Args:
        level: Logging level for console output. Defaults to INFO.
            Use logging.DEBUG for verbose output during development.
        format_string: Format string for log messages.
            Defaults to "[%(levelname)s] [%(name)s] %(message)s".
        log_file: Optional path to log file. If None, file logging is disabled.
            If specified, creates a file handler that logs to this path.
        file_level: Optional logging level for file output. If None, uses same
            level as console. Typically set to DEBUG to capture more detail.

    Example:
        >>> # Development mode - verbose console, debug file
        >>> setup_logging(level=logging.DEBUG, log_file="debug.log")
        >>>
        >>> # Production mode - info console, no file
        >>> setup_logging(level=logging.INFO)
        >>>
        >>> # Production with detailed file logs
        >>> setup_logging(
        ...     level=logging.WARNING,
        ...     log_file="pyguara.log",
        ...     file_level=logging.DEBUG
        ... )
    """
    # Get the root logger for the pyguara package
    root_logger = logging.getLogger("pyguara")
    root_logger.setLevel(logging.DEBUG)  # Capture everything, filter at handler level

    # Clear any existing handlers (in case setup is called multiple times)
    root_logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(format_string)

    # Console handler (StreamHandler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        # Ensure parent directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setLevel(file_level if file_level is not None else level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Prevent propagation to root logger (avoid duplicate logs)
    root_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Get a logger for the specified module.

    This is a convenience function that creates a logger under the pyguara
    namespace. Modules should call this with __name__ to create their logger.

    Args:
        name: The name of the logger, typically __name__ of the calling module.

    Returns:
        A Logger instance configured according to the pyguara logging setup.

    Example:
        >>> # In a module file (e.g., pyguara/scene/manager.py)
        >>> logger = get_logger(__name__)
        >>> logger.info("Scene manager initialized")
    """
    # Ensure the name is under the pyguara namespace
    if not name.startswith("pyguara."):
        name = f"pyguara.{name}"

    return logging.getLogger(name)
