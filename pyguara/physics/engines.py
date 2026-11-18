"""The physics engine a configuration asks for."""

from __future__ import annotations

from pyguara.config.types import PhysicsConfig
from pyguara.physics.backends.rapier_impl import RapierEngine


def create_physics_engine(config: PhysicsConfig) -> RapierEngine:
    """Build the engine `config` describes.

    What bootstrap registers as `IPhysicsEngine`. A game building a world of
    its own -- a room's walls, a preview -- uses it too, so that world is
    tuned like the main one. The engine is not initialised: call
    `initialize(gravity)` on it.

    Args:
        config: The physics section of the game's configuration.

    Returns:
        A new engine.
    """
    return RapierEngine(substeps=config.substeps)
