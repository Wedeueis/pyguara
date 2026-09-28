"""Platformer input-to-motion policy: coyote time, jump buffer, wall jump.

A kit rather than core, on the same line that put `Hitbox`/`Hurtbox` in
`kits/action_combat`: this is one genre's vocabulary. Coyote time, jump
buffering, wall-slide and wall-jump are answers to *a platformer's*
questions, and a top-down or isometric game has no use for any of them.

What stayed in core is `pyguara.physics.character_mover.CharacterMover` --
axis-separated sweep-and-resolve against solids, with no gravity
assumption and no genre vocabulary. Every genre with character-based
movement needs "sweep a collider without tunnelling or getting stuck",
and #99 confirmed it empirically: `CharacterMover` needed zero changes to
serve 8-directional top-down motion. This kit and
`kits.topdown_movement` are two policies over that one mechanism.

Per `pyguara.kits`' layering rule, nothing here registers itself. A game
that wants `PlatformerController` in its prefabs registers the component
itself:

```python
container.get(ComponentRegistry).register(PlatformerController)
```
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
