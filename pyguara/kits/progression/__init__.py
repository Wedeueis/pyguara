"""The progression kit: experience, levels, the pick, and the magnet.

Three things: the experience and level substrate, the upgrade offer,
and the pickup magnet. The level-up UI, the upgrade content and any
item model stay with the game.

- Nothing here knows what an upgrade does. `Upgrade.apply` is a
  callable the game writes.
- Nothing here knows what a level is worth. `grant_experience()`
  counts levels into `Experience.pending_levels` and dispatches
  `LeveledUp`; spending them is the game's.
"""

from pyguara.kits.progression.curve import Geometric, LevelCurve, Linear, Table
from pyguara.kits.progression.events import (
    ExperienceGained,
    LeveledUp,
    PickupCollected,
)
from pyguara.kits.progression.experience import Experience, grant_experience
from pyguara.kits.progression.pickup import Attracted, Magnet, MagnetSystem
from pyguara.kits.progression.upgrade import (
    Upgrade,
    UpgradeRecord,
    eligible,
    offer,
    take,
    times_taken,
)

__all__ = [
    "Attracted",
    "Experience",
    "ExperienceGained",
    "Geometric",
    "LevelCurve",
    "LeveledUp",
    "Linear",
    "Magnet",
    "MagnetSystem",
    "PickupCollected",
    "Table",
    "Upgrade",
    "UpgradeRecord",
    "eligible",
    "grant_experience",
    "offer",
    "take",
    "times_taken",
]
