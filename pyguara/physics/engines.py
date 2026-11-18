"""The physics engine a configuration asks for."""

from __future__ import annotations

from pyguara.config.types import PhysicsBackend, PhysicsConfig
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.backends.rapier_impl import RapierEngine


def create_physics_engine(config: PhysicsConfig) -> PymunkEngine | RapierEngine:
    """Build the engine `config.backend` names, tuned by the rest of `config`.

    What bootstrap registers as `IPhysicsEngine`. A game building a world of
    its own -- a room's walls, a preview -- uses it too, so that world follows
    `physics.backend` and `PYGUARA_PHYSICS_BACKEND` like the main one. The
    engine is not initialised: call `initialize(gravity)` on it.

    Args:
        config: The physics section of the game's configuration.

    Returns:
        A new engine.
    """
    if config.backend is PhysicsBackend.RAPIER:
        # Rapier has its own contact solver; Chipmunk's two tunings do not
        # apply to it.
        return RapierEngine(substeps=config.substeps)
    return PymunkEngine(
        substeps=config.substeps,
        penetration_recovery=config.penetration_recovery,
        sleep_time_threshold=config.sleep_time_threshold,
    )
