"""A growing/shrinking chain of grid cells following a head.

Genre-agnostic mechanism, not just a snake's body: a Tron-style
light-cycle trail, a rope/tail follow, a visual combo chain all need the
same "advance the head, grow on demand, detect self-overlap" shape. No
snake vocabulary lives here -- `games/true_coral` is this kit's first
consumer, built entirely on top via its own components/systems.
"""

from pyguara.kits.trail.trail import (
    Trail,
    advance,
    contains,
    grow,
    overlaps_self,
    reset,
)

__all__ = [
    "Trail",
    "advance",
    "contains",
    "grow",
    "overlaps_self",
    "reset",
]
