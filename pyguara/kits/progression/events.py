"""What `grant_experience()` dispatches.

Events, not callbacks, and that is the load-bearing decision in this kit:
it is how a level-up *scene* gets pushed without the kit knowing that
scenes, or UI, or upgrade cards exist. A game subscribes to `LeveledUp`
and does whatever a level-up means to it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExperienceGained:
    """Fired by `grant_experience()` on every grant, before any level-up.

    Fires even when `amount` is 0, matching `DamageDealt`'s rule: a
    listener wanting "did this pickup count" reads the amount, rather than
    needing a silence to mean it.

    Attributes:
        entity: The entity id that gained the experience.
        amount: How much was granted.
        current: Experience toward the *current* level after the grant.
        total: Lifetime experience after the grant.
        level: The level after the grant resolved.
    """

    entity: str
    amount: float
    current: float
    total: float
    level: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class LeveledUp:
    """Fired once per level crossed by a single grant.

    One grant can cross several levels -- a boss's experience early in a
    run -- and each crossing gets its own event, so a listener offering one
    upgrade per level does not have to reconstruct how many it missed.

    Attributes:
        entity: The entity id that levelled.
        level: The level just reached.
        pending_levels: Levels reached but not yet spent, *after* this one
            was counted. A game that queues one upgrade screen per level
            reads this to know how many are still owed.
    """

    entity: str
    level: int
    pending_levels: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class PickupCollected:
    """Fired by `MagnetSystem` when a pickup reaches its collector.

    Carries the payload rather than acting on it: the kit does not know
    whether an orb is worth experience, currency or a key, and a game
    subscribing here is what turns one into the other. Typically that
    listener calls `grant_experience()`.

    Attributes:
        pickup: The collected entity's id. Still alive -- the system marks
            it inactive and leaves destroying, pooling or fading it to the
            game.
        collector: The entity id whose `Magnet` collected it.
        payload: Whatever the pickup's `Attracted.payload` held.
    """

    pickup: str
    collector: str
    payload: Any
    timestamp: float = field(default_factory=time.time)
    source: Any = None
