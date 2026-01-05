"""Error handling subsystem."""

from pyguara.error.types import ErrorCategory, ErrorSeverity
from pyguara.error.exceptions import (
    EngineException,
    SystemException,
    ConfigException,
    AssetException,
    GraphicsException,
)
from pyguara.error.handlers import safe_execute, retry, RetryPolicy

__all__ = [
    "ErrorCategory",
    "ErrorSeverity",
    "EngineException",
    "SystemException",
    "ConfigException",
    "AssetException",
    "GraphicsException",
    "safe_execute",
    "retry",
    "RetryPolicy",
]
