"""Window management events."""

from dataclasses import dataclass
import time
from typing import Any


@dataclass
class WindowResizeEvent:
    """Fired when the OS window dimensions change."""

    width: int
    height: int
    timestamp: float = 0.0
    source: Any = None

    def __post_init__(self) -> None:
        """Initialize timestamp if not provided."""
        if self.timestamp == 0.0:
            self.timestamp = time.time()
