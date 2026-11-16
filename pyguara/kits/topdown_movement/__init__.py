"""Top-down movement policy: actor-vs-actor soft separation.

Pushes overlapping actors gently apart using the spatial hash, which
is what a top-down game wants. Like `kits.platformer_movement`, it is
a policy over `pyguara.physics.character_mover.CharacterMover`, which
is in core.

Nothing here registers itself.
"""

from pyguara.kits.topdown_movement.body import TopDownBody
from pyguara.kits.topdown_movement.directional_system import (
    DirectionalAnimationSystem,
)
from pyguara.kits.topdown_movement.facing import (
    DirectionalAnimator,
    DirectionalClipSet,
    Facing,
    facing_from_vector,
)
from pyguara.kits.topdown_movement.prediction import TopDownPrediction
from pyguara.kits.topdown_movement.system import TopDownSystem, step_body

__all__ = [
    "TopDownBody",
    "TopDownPrediction",
    "TopDownSystem",
    "step_body",
    # Directional animation: N actions x 4 or 8 facings
    "Facing",
    "DirectionalClipSet",
    "DirectionalAnimator",
    "DirectionalAnimationSystem",
    "facing_from_vector",
]
