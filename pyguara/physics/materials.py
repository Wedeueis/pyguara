"""Physics material presets for common surfaces.

This module provides pre-configured PhysicsMaterial instances for common surfaces
and gameplay scenarios. These presets offer realistic physical properties and
improve developer ergonomics by eliminating the need to manually tune friction,
restitution, and density values.

Usage:
    from pyguara.physics.materials import Materials

    player.add_component(Collider(
        shape_type=ShapeType.BOX,
        dimensions=[32, 64],
        material=Materials.PLAYER
    ))

    ground.add_component(Collider(
        shape_type=ShapeType.BOX,
        dimensions=[800, 32],
        material=Materials.GROUND
    ))
"""

from dataclasses import dataclass

from pyguara.physics.types import PhysicsMaterial


@dataclass(frozen=True)
class MaterialConstants:
    """Common physics material presets.

    All materials are frozen dataclass instances to prevent accidental modification.
    Each preset is configured with realistic friction, restitution (bounciness),
    and density values.

    Attributes:
        DEFAULT: Generic material with moderate friction and no bounce.
        WOOD: Wooden surfaces with moderate friction and slight bounce.
        METAL: Metallic surfaces with lower friction and minimal bounce.
        STONE: Stone/concrete surfaces with high friction and minimal bounce.
        RUBBER: Rubber surfaces with very high friction and bounce.
        ICE: Icy surfaces with minimal friction and no bounce (slippery).
        GLASS: Glass surfaces with minimal friction and high bounce (brittle).
        SUPER_BALL: Highly bouncy material for game mechanics.
        PLAYER: Typical player character material with controlled movement.
        GROUND: Standard ground/platform material with no bounce.
    """

    DEFAULT = PhysicsMaterial(friction=0.5, restitution=0.0, density=1.0)
    WOOD = PhysicsMaterial(friction=0.6, restitution=0.3, density=0.7)
    METAL = PhysicsMaterial(friction=0.4, restitution=0.2, density=8.0)
    STONE = PhysicsMaterial(friction=0.8, restitution=0.1, density=2.5)
    RUBBER = PhysicsMaterial(friction=0.9, restitution=0.8, density=1.1)
    ICE = PhysicsMaterial(friction=0.05, restitution=0.1, density=0.9)
    GLASS = PhysicsMaterial(friction=0.1, restitution=0.7, density=2.4)
    SUPER_BALL = PhysicsMaterial(friction=0.6, restitution=0.95, density=1.0)
    PLAYER = PhysicsMaterial(friction=0.7, restitution=0.0, density=1.0)
    GROUND = PhysicsMaterial(friction=0.7, restitution=0.0, density=0.0)


# Singleton instance for convenient access
Materials = MaterialConstants()
