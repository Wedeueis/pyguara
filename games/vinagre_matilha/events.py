"""Vinagre: Matilha - Game Events.

Every event carries `timestamp`/`source` so it structurally satisfies
`pyguara.events.protocols.Event` (see games/true_coral/events.py's
docstring for why that matters).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GateOpenedEvent:
    """Fired when a pressure plate's required count is met."""

    log_entity_id: str
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class JaguarCorneredEvent:
    """Fired when the jaguar has no reachable flee direction left."""

    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class ReinforcementsCalledEvent:
    """Fired when a dog's behavior tree flags the pack as isolated/threatened."""

    dog_entity_id: str
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class StageClearedEvent:
    """Fired when the current stage's win condition is met."""

    stage_index: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None
