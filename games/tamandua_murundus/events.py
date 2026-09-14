"""What the clearing announces.

Events rather than direct calls, so the scene can react to a kill with a
spark, a popup and a hit-stop without the system that resolved the kill
knowing any of those exist.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pyguara.common.types import Vector2


@dataclass
class TongueLashed:
    """Fired when the tongue lashes, whether or not it connected.

    Fires on a miss too, because the animation and the sound of a lash
    are the same either way -- a listener wanting "did it land" reads
    `hit`.

    Attributes:
        origin: Where the lash started.
        target: Where it reached.
        hit: Whether it connected with anything.
    """

    origin: Vector2
    target: Vector2
    hit: bool
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class InsectKilled:
    """Fired when an insect's health reaches zero.

    Attributes:
        entity: The dead insect's entity id.
        position: Where it died, for the spark and (from D4) the mote.
    """

    entity: str
    position: Vector2
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class MurunduBroken:
    """Fired when a mound stops feeding the swarm.

    Attributes:
        entity: The mound's entity id.
        position: Where it stood.
        remaining: How many mounds are still intact after this one broke.
    """

    entity: str
    position: Vector2
    remaining: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None
