"""Core exception hierarchy."""

import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from pyguara.error.types import ErrorCategory, ErrorSeverity


@dataclass
class ErrorContext:
    """Context information for debugging and recovery."""

    category: ErrorCategory
    severity: ErrorSeverity = ErrorSeverity.ERROR
    recoverable: bool = True
    data: Dict[str, Any] = field(default_factory=dict)
    stack_trace: str = field(init=False)

    def __post_init__(self) -> None:
        """Capture stack trace automatically."""
        # Limit stack trace to last 10 frames to avoid spam
        self.stack_trace = "".join(traceback.format_stack()[-10:])


class EngineException(Exception):
    """Base exception for all PyGuara engine errors."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        recoverable: bool = True,
        context: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        """Initialize the engine exception.

        Args:
            message: Human readable error description.
            category: The subsystem where error occurred.
            severity: How bad is it?
            recoverable: Can the engine continue running?
            context: Extra debug data (variables, state).
            cause: The original exception if wrapping another.
        """
        super().__init__(message)
        self.message = message
        self.cause = cause
        self.ctx = ErrorContext(
            category=category,
            severity=severity,
            recoverable=recoverable,
            data=context or {},
        )

    def __str__(self) -> str:
        """Return a formatted string representation of the error."""
        return f"[{self.ctx.category.value.upper()}] {self.message}"


# --- Core System Exceptions ---


class SystemException(EngineException):
    """Critical system-level failures (Memory, OS, Threading)."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        """Initialize with critical severity defaults."""
        kwargs.setdefault("category", ErrorCategory.SYSTEM)
        kwargs.setdefault("severity", ErrorSeverity.CRITICAL)
        kwargs.setdefault("recoverable", False)
        super().__init__(message, **kwargs)


class ConfigException(EngineException):
    """Configuration loading or validation errors."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        """Initialize with config category default."""
        kwargs.setdefault("category", ErrorCategory.CONFIG)
        super().__init__(message, **kwargs)


class AssetException(EngineException):
    """Asset loading or management errors."""

    def __init__(
        self, message: str, asset_path: Optional[str] = None, **kwargs: Any
    ) -> None:
        """Initialize with asset context."""
        kwargs.setdefault("category", ErrorCategory.ASSETS)
        context = kwargs.get("context", {})
        if asset_path:
            context["asset_path"] = asset_path
        kwargs["context"] = context
        super().__init__(message, **kwargs)


class GraphicsException(EngineException):
    """Rendering pipeline errors."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        """Initialize with graphics category default."""
        kwargs.setdefault("category", ErrorCategory.GRAPHICS)
        super().__init__(message, **kwargs)
