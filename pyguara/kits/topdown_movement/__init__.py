"""Top-down movement policy: actor-vs-actor soft separation.

A kit rather than core, for the mirror of the reason
`kits.platformer_movement` is: pushing overlapping actors gently apart via
the spatial hash is what a top-down game wants and what a platformer never
asks for -- there, overlap is resolved against level geometry, not against
the other characters standing on the same floor.

Both kits are policy over the one core mechanism they share,
`pyguara.physics.character_mover.CharacterMover`, which stayed in core
because it assumes no gravity and speaks no genre's vocabulary.

Per `pyguara.kits`' layering rule, nothing here registers itself.
"""

from pyguara.kits.topdown_movement.body import TopDownBody
from pyguara.kits.topdown_movement.system import TopDownSystem

__all__ = ["TopDownBody", "TopDownSystem"]
