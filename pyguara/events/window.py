"""Window management events."""

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WindowResizeEvent:
    """Fired when the OS window dimensions change.

    Attributes:
        width: New window width in pixels.
        height: New window height in pixels.
        timestamp: Unix time the event was created.
        source: Whatever raised the event, if it identified itself.
    """

    width: int
    height: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None
