"""#28's spawn kit: a budget- and pacing-gated wave/encounter director.

`SpawnDirector` never knows what's being spawned -- a `SpawnEntry`'s
factory is an opaque callable the game builds, closing over whatever
context (position, enemy type) it needs. TD wave-clear-to-advance and
arena/horde continuous pressure are the same mechanism with different
`Wave`/budget parameters, not different code paths.
"""

from pyguara.kits.spawn.director import SpawnDirector, SpawnEntry, Wave

__all__ = ["SpawnDirector", "SpawnEntry", "Wave"]
