"""The spawn kit: a schedule- and pacing-gated wave/encounter director.

`SpawnDirector` never knows what is being spawned: a `SpawnEntry`'s
factory is an opaque callable the game builds. Tower-defence waves and
continuous horde pressure are the same mechanism with different `Wave`
parameters and a different schedule.
"""

from pyguara.kits.spawn.director import SpawnDirector, SpawnEntry, Wave

__all__ = ["SpawnDirector", "SpawnEntry", "Wave"]
