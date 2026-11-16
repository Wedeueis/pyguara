"""Platformer input-to-motion policy: coyote time, jump buffer, wall jump.

A kit because this is one genre's vocabulary. The mechanism it stands
on is in core: `pyguara.physics.character_mover.CharacterMover`, which
sweeps a collider against solids with no gravity assumption. This kit
and `kits.topdown_movement` are two policies over it.

Nothing here registers itself. A game that wants
`PlatformerController` in its prefabs registers the component.

Example:
    container.get(ComponentRegistry).register(PlatformerController)
"""

from pyguara.kits.platformer_movement.controller import (
    PlatformerController,
    PlatformerInput,
)
from pyguara.kits.platformer_movement.debug_draw import PlatformerProbeDebugRenderer
from pyguara.kits.platformer_movement.system import PlatformerSystem

__all__ = [
    "PlatformerController",
    "PlatformerInput",
    "PlatformerProbeDebugRenderer",
    "PlatformerSystem",
]
