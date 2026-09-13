"""#28's progression kit: experience, levels, the pick, and the magnet.

The genre asks for five separable things and **three** belong in a kit:
the experience/level substrate, the upgrade offer, and the pickup magnet.
The level-up UI scene, the upgrade content (names, weights, recipes) and
any weapon or item model stay with the game.

Two rules keep this kit from growing into a framework:

- **Nothing here knows what an upgrade does.** `Upgrade.apply` is an
  opaque callable the game writes, so this package imports neither
  `kits.stats` nor `kits.effects` while composing with both.
- **Nothing here knows what a level is worth.** `grant_experience()`
  counts levels into `Experience.pending_levels` and dispatches
  `LeveledUp`; spending them is the game's, through an event, which is how
  a level-up *scene* gets pushed without this kit learning that scenes
  exist.

There is deliberately no item or inventory model. Weapon evolution needs
none: `Upgrade.requires` plus `UpgradeRecord.taken` already expresses
"evolved whip requires whip x5 and the bracer".
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
