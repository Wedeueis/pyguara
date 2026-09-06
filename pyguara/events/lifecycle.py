"""Application lifecycle events."""

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QuitEvent:
    """Fired when the user asks the application to close.

    Attributes:
        timestamp: Unix time the event was created.
        source: Whatever raised the event, if it identified itself.
    """

    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class ApplicationStartEvent:
    """Fired once when the engine loop begins.

    Attributes:
        timestamp: Unix time the event was created.
        source: Whatever raised the event, if it identified itself.
    """

    timestamp: float = field(default_factory=time.time)
    source: Any = None
