"""Components for the clearing.

Data only, per the StrictComponent rule -- the behaviour lives in
`systems.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyguara.common.types import Vector2
from pyguara.ecs.component import StrictComponent


@dataclass(slots=True)
class Tamandua(StrictComponent):
    """The player: an anteater with a tongue on a cooldown.

    Attributes:
        speed: Movement speed in pixels per second.
        facing: Heading in radians, clockwise from screen +x -- the same
            convention the spot light's cone uses, because the cone *is*
            this facing.
        tongue_cooldown: Seconds until the tongue may lash again.
        tongue_interval: Seconds between lashes. Lowered by upgrades.
        tongue_range: How far the tongue reaches.
        tongue_arc: Full opening of the arc it can reach into, radians.
    """

    speed: float = 210.0
    facing: float = 0.0
    tongue_cooldown: float = 0.0
    tongue_interval: float = 0.42
    tongue_range: float = 150.0
    tongue_arc: float = 1.7

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass skips."""
        StrictComponent.__init__(self)


@dataclass(slots=True)
class Murundu(StrictComponent):
    """A termite mound: a spawn anchor that can be broken.

    Attributes:
        health: Hits remaining before it breaks.
        max_health: Starting health, for the damage readout.
        radius: Drawn size, and the distance the tongue must reach.
        broken: Whether it has stopped feeding the swarm.
        feed_interval: Seconds between releases while intact.
        feed_timer: Seconds until the next release.
        glow_phase: Offset so a row of mounds does not pulse in lockstep.
    """

    health: float = 12.0
    max_health: float = 12.0
    radius: float = 34.0
    broken: bool = False
    feed_interval: float = 2.6
    feed_timer: float = 0.0
    glow_phase: float = 0.0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass skips."""
        StrictComponent.__init__(self)


@dataclass(slots=True)
class Insect(StrictComponent):
    """One interactive insect.

    D1 keeps a handful alive so the tongue has something to lash; D2
    replaces the spawn path with the pooled swarm and the flock.

    Attributes:
        velocity: Current heading and speed, pixels per second.
        health: Hits remaining.
        wobble: Phase offset for the drift, so they do not move as one.
        anchor: Entity id of the murundu that released it, if any.
    """

    velocity: Vector2 = field(default_factory=Vector2.zero)
    health: float = 1.0
    wobble: float = 0.0
    anchor: str | None = None

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass skips."""
        StrictComponent.__init__(self)
