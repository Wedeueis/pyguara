"""Vinagre: Matilha - Game Components.

Everything genre-generic already lives in core (`pyguara.ai.flocking_system.
FlockingAgent`, `pyguara.ai.components.AIComponent`) or in the pack kit
(`pyguara.kits.pack`). What's left here is specific to this one demo: the
webbed-feet/current-zone/pressure-plate mechanics and the jaguar's tuning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyguara.common.grid import Cell
from pyguara.common.types import Vector2
from pyguara.ecs.component import StrictComponent


@dataclass(slots=True)
class WebbedFeet(StrictComponent):
    """Marker: this entity ignores water-current velocity damping.

    Bush dogs carry this natively (semi-aquatic hunters); the jaguar does
    not -- currents are a tool for cutting off its escape, not a hazard for
    the pack.
    """

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a
        zero-argument `super()` still resolves against the discarded
        original, raising TypeError on every instantiation.
        """
        StrictComponent.__init__(self)


@dataclass(slots=True)
class JaguarState(StrictComponent):
    """Tuning and runtime state for the fleeing predator.

    `JaguarAISystem` calls `SteeringBehavior.flee()` directly rather than
    going through a `SteeringAgent`/`SteeringSystem` -- that dispatch has no
    way to pass a custom `panic_distance` per agent, only its own hardcoded
    default, which would leave `panic_distance` below declared and silently
    ignored. So this component carries the small slice of steering state
    (`velocity`, `max_speed`, `max_force`) `JaguarAISystem` integrates by
    hand, the same F=ma clamp `SteeringSystem` uses internally.

    Attributes:
        velocity: Current velocity, integrated by `JaguarAISystem` each tick.
        max_speed: Base flee speed, before any current-zone damping.
        max_force: Maximum steering force (turn speed/acceleration).
        panic_distance: How close a dog must be before the jaguar reacts.
        cornered: Set by `JaguarAISystem` once escape routes are cut off.
            Read by the scene to trigger the stage-clear sequence.
        previous_position: Written by `JaguarAISystem` before it moves the
            jaguar each tick; used to revert an illegal move into a wall
            cell. `None` until the first tick.
    """

    velocity: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    max_speed: float = 140.0
    max_force: float = 600.0
    panic_distance: float = 220.0
    cornered: bool = False
    previous_position: Vector2 | None = None

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips."""
        StrictComponent.__init__(self)


@dataclass(slots=True)
class CurrentZone(StrictComponent):
    """Marks a `TriggerVolume` entity as a water-current zone.

    Attributes:
        damping: Multiplies the velocity of any entity inside that lacks
            `WebbedFeet`, once per tick -- 0.35 means "lose 65% of your
            speed every tick you're still in the current."
    """

    damping: float = 0.35

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips."""
        StrictComponent.__init__(self)


@dataclass(slots=True)
class PressurePlate(StrictComponent):
    """Marks a `TriggerVolume` entity as a pack-weighted pressure plate.

    Attributes:
        required_count: How many entities must stand on the plate
            simultaneously to open the paired `LogGate`.
        log_entity_id: The gate entity this plate opens.
        opened: Latches `True` the first time `required_count` is met.
            v1 does not re-close the gate.
    """

    required_count: int
    log_entity_id: str
    opened: bool = False

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips."""
        StrictComponent.__init__(self)


@dataclass(slots=True)
class LogGate(StrictComponent):
    """The obstacle a paired `PressurePlate` removes when opened.

    Attributes:
        cells: Grid cells this log occupies -- removed from the pack's
            `GridGraph.walls` (and the flow field recomputed) once opened.
    """

    cells: list[Cell] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips."""
        StrictComponent.__init__(self)
