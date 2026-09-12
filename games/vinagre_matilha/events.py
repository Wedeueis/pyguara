"""Vinagre: Matilha - Game Events.

Every event carries `timestamp`/`source` so it structurally satisfies
`pyguara.events.protocols.Event` (see games/true_coral/events.py's
docstring for why that matters).

The combat events exist so presentation stays fully decoupled from rules:
`combat.py` knows nothing about particles, camera shake or damage numbers,
and `scenes.py` spawns all of that purely by subscribing here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pyguara.common.types import Vector2


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


@dataclass
class PackBitEvent:
    """Fired when one dog lands a bite on the jaguar."""

    dog_entity_id: str
    position: Vector2
    damage: float
    was_punish: bool
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class JaguarSwipedEvent:
    """Fired the instant the jaguar's swipe connects (or whiffs)."""

    position: Vector2
    direction: Vector2
    hit: bool
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class DogDownedEvent:
    """Fired when a swipe knocks one dog out of the fight."""

    dog_entity_id: str
    position: Vector2
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class JaguarDefeatedEvent:
    """Fired when the jaguar's health reaches zero -- the win condition."""

    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class PackBrokenEvent:
    """Fired when too many dogs are downed at once -- the lose condition."""

    downed_count: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None
