"""Animation-driven active frames for a `Hitbox`'s `TriggerVolume`.

The mechanism `Hitbox`'s own docstring named as future work: instead of a
game manually flipping `TriggerVolume.active`, this entity's `Animator`
can drive it through `pyguara.graphics.events.AnimationFrameEvent` --
authored once on the clip (`AnimationClip.frame_events`), not per-frame in
gameplay code. A game not using animation-driven windows keeps flipping
`active` directly; nothing about `Hitbox`/`HitboxSystem` requires this.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.ecs.component import StrictComponent


@dataclass(slots=True)
class ActiveFrameWindow(StrictComponent):
    """Names the two animation frame-events that open and close a hit window.

    `ActiveFrameSystem` reacts to `AnimationFrameEvent`s carrying these
    names on this same entity by setting its `TriggerVolume.active`.

    Attributes:
        activate_on: Frame-event name that sets `TriggerVolume.active =
            True`.
        deactivate_on: Frame-event name that sets it back to `False`.
    """

    activate_on: str
    deactivate_on: str

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a zero-argument
        `super()` still resolves against the discarded original, raising
        TypeError on every instantiation.
        """
        StrictComponent.__init__(self)
