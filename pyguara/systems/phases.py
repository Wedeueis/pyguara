"""Named points in a scene's update order.

`SystemManager.register()` takes a bare `priority` int, which works but
does not read: a game adding a `PoisonSystem` that must run before its
`DeathSystem` has to pick a number against the engine's, and against every
other number the game already chose. Nothing says what 175 means.

`Phase` is that number with a name on it. It is an `IntEnum`, so a phase
*is* a priority -- `register(system, priority=Phase.LOGIC)` needs no new
machinery, mixes freely with raw ints, and arithmetic works for the
common "just after that one" case:

```python
systems.register(poison, priority=Phase.LOGIC)
systems.register(death, priority=Phase.LOGIC + 10)   # after poison
```

The values are spaced 100 apart and chosen to match the bands the engine
already occupies, so naming them changes no existing order. `Scene`
registers Steering at 150, AI at 200, AudioSource at 250 and Animation at
300 -- which is to say between INPUT and LOGIC, at AI, and either side of
PRESENTATION.
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
