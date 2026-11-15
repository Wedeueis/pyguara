"""Events about the player's language."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

__all__ = ["LocaleChanged"]


@dataclass
class LocaleChanged:
    """The text locale changed: anything showing translated text redraws it.

    Attributes:
        locale: The new locale's tag.
        timestamp: Unix time the event was created.
        source: Whatever raised the event, if it identified itself.
    """

    locale: str
    timestamp: float = field(default_factory=time.time)
    source: Any = None
