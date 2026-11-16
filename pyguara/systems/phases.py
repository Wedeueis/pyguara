"""Named points in a scene's update order.

`Phase` is an `IntEnum`, so a phase is a priority:
`register(system, priority=Phase.LOGIC)` mixes with raw ints, and
`Phase.LOGIC + 10` means "just after".

The values are 100 apart and match the bands the engine uses. `Scene`
registers Tween at 120, Steering at 150, AI at 200, AudioSource at 250
and Animation at 300.

Example:
    systems.register(poison, priority=Phase.LOGIC)
    systems.register(death, priority=Phase.LOGIC + 10)   # after poison
"""

from __future__ import annotations

from enum import IntEnum


class Phase(IntEnum):
    """Named priorities for `SystemManager.register()`.

    Lower runs earlier, matching `priority`. A phase is an ordinary int
    wherever one is expected.
    """

    INPUT = 100
    """Turning device state into intent, before anything reads it."""

    AI = 200
    """Deciding what non-player actors intend this tick."""

    LOGIC = 400
    """Gameplay rules: movement intent, combat, scoring, triggers."""

    PHYSICS = 500
    """Simulation and collision resolution, after intent is settled."""

    POST = 600
    """Reacting to where physics left things: cameras, death, cleanup."""

    PRESENTATION = 700
    """Driving what will be drawn -- animation state, audio emitters."""
