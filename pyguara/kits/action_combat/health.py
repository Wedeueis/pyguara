"""The Health component and its invincibility-timer upkeep."""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.ecs.component import StrictComponent


@dataclass(slots=True)
class Health(StrictComponent):
    """An entity's hit points, plus any active invincibility window.

    Pure data -- `apply_damage()` (`damage.py`) is what actually mutates
    `current`/`invincible_timer`; `HealthSystem` is what ticks
    `invincible_timer` down each frame. Neither lives on this component,
    per the StrictComponent data-only rule.

    Attributes:
        current: Current hit points. Never negative -- `apply_damage()`
            clamps at 0.
        max_health: The ceiling `current` is clamped to on healing.
        invincible_timer: Seconds remaining before this entity can take
            damage again. 0 means vulnerable. `apply_damage()` is a no-op
            while this is positive.
    """

    current: float = 1.0
    max_health: float = 1.0
    invincible_timer: float = 0.0

    @property
    def is_alive(self) -> bool:
        """Whether `current` is still above zero."""
        return self.current > 0

    @property
    def is_invincible(self) -> bool:
        """Whether `invincible_timer` is still counting down."""
        return self.invincible_timer > 0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a zero-argument
        `super()` still resolves against the discarded original, raising
        TypeError on every instantiation.
        """
        StrictComponent.__init__(self)
