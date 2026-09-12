"""Vinagre: Matilha - Game Components.

Everything genre-generic already lives in core (`pyguara.ai.flocking_system.
FlockingAgent`, `pyguara.ai.components.AIComponent`) or in a kit
(`pyguara.kits.pack` for coordination, `pyguara.kits.action_combat` for
`Health`/`apply_damage`). What's left here is specific to this one demo:
the webbed-feet/current/plate mechanics, and the two creatures' own combat
state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

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
class DogState(StrictComponent):
    """Per-dog combat and presentation state.

    Attributes:
        bite_cooldown: Seconds until this dog can bite again.
        downed_timer: Seconds remaining knocked out of the fight. A downed
            dog neither bites nor steers; `PackRecoverySystem` counts it
            down faster when packmates are close, so the pack literally
            rallies its own.
        facing: Last non-zero movement direction, for drawing which way the
            dog points. Rendering only.
        bite_flash: Seconds remaining on the lunge animation. Rendering
            only.
        knockback: Residual velocity from a jaguar swipe, decayed by
            `PackCombatSystem` and added on top of steering.
    """

    bite_cooldown: float = 0.0
    downed_timer: float = 0.0
    facing: Vector2 = field(default_factory=lambda: Vector2(1, 0))
    bite_flash: float = 0.0
    knockback: Vector2 = field(default_factory=lambda: Vector2(0, 0))

    @property
    def is_downed(self) -> bool:
        """Whether this dog is currently out of the fight."""
        return self.downed_timer > 0.0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips."""
        StrictComponent.__init__(self)


class JaguarPhase(Enum):
    """What the jaguar is doing right now.

    The loop the whole fight is built on: it flees while it can, and when
    the pack crowds it, it plants and telegraphs a swipe (`WINDUP`) before
    actually swinging (`SWIPE`) -- that wind-up is the player's cue to call
    Scatter. Whiffing leaves it in `RECOVER`, where the pack bites at
    bonus damage. Read the tell, dodge, punish.
    """

    STALK = auto()
    WINDUP = auto()
    SWIPE = auto()
    RECOVER = auto()


@dataclass(slots=True)
class JaguarState(StrictComponent):
    """Tuning, movement, and attack state for the jaguar.

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
        cornered: Set once escape routes are cut off. Read by the scene to
            trigger the stage-clear sequence.
        previous_position: Written before the jaguar moves each tick; used
            to revert an illegal move into a wall cell.
        phase: Current attack-loop phase. See `JaguarPhase`.
        phase_timer: Seconds remaining in `phase`.
        swipe_cooldown: Seconds until it may wind up another swipe.
        swipe_direction: Locked in at `WINDUP`, used by `SWIPE`'s arc.
        facing: Last heading, for drawing. Rendering only.
        hurt_flash: Seconds remaining on the damage flash. Rendering only.
    """

    velocity: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    # Deliberately slower than a dog (158 -> see `_create_dog`): a pack
    # hunts by running its prey down, so prey that simply outruns every
    # dog forever makes the whole demo unwinnable -- which is exactly what
    # an earlier build did at 165 against the pack's 158.
    max_speed: float = 132.0
    max_force: float = 700.0
    panic_distance: float = 260.0
    cornered: bool = False
    previous_position: Vector2 | None = None

    phase: JaguarPhase = JaguarPhase.STALK
    phase_timer: float = 0.0
    swipe_cooldown: float = 0.0
    swipe_direction: Vector2 = field(default_factory=lambda: Vector2(1, 0))
    facing: Vector2 = field(default_factory=lambda: Vector2(1, 0))
    hurt_flash: float = 0.0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips."""
        StrictComponent.__init__(self)


@dataclass(slots=True)
class CurrentZone(StrictComponent):
    """Marks a `TriggerVolume` entity as a water-current zone.

    Attributes:
        damping: Fraction of speed an entity without `WebbedFeet` retains
            after one full *second* in the current -- 0.35 means "35% of
            your speed survives a second of swimming against it." Framed as
            a per-second rate rather than a flat per-tick multiplier so the
            effect reads the same regardless of frame rate: applying 0.35
            directly once per ~1/60s physics tick (an earlier build's bug,
            caught by playtesting) crushes velocity to near zero within a
            couple of frames -- a wall, not a current -- because a per-tick
            multiplier compounds 60 times a second.
        flow: World-space drift the current pushes non-webbed entities
            along, pixels/second. What makes a channel a *current* and not
            just mud.
    """

    damping: float = 0.55
    flow: Vector2 = field(default_factory=lambda: Vector2(0, 40))

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
