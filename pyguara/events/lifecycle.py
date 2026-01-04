"""Standard lifecycle events for application state."""

from dataclasses import dataclass
from typing import Any
import time


@dataclass
class QuitEvent:
    """Fired when the user requests the application to close."""

    timestamp: float = 0.0
    source: Any = None

    def __post_init__(self) -> None:
        """Initialize timestamp if not provided."""
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class ApplicationStartEvent:
    """Fired when the engine loop begins."""

    timestamp: float = 0.0
    source: Any = None

    def __post_init__(self) -> None:
        """Initialize timestamp if not provided."""
        if self.timestamp == 0.0:
            self.timestamp = time.time()
