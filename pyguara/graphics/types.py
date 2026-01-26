"""Graphics-specific types and enumerations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional
from enum import IntEnum
from pyguara.common.types import Vector2
from pyguara.resources.types import Texture

if TYPE_CHECKING:
    from pyguara.graphics.materials.material import Material


class Layer(IntEnum):
    """
    Defines the rendering order (Z-Layer).

    Lower numbers are drawn first (background).
    Higher numbers are drawn last (on top of everything).

    Usage:
        sprite.layer = Layer.ENTITIES
    """

    BACKGROUND = 0
    WORLD = 10  # Paredes, chão
    DECORATION = 20  # Grama, pedras (atrás do player)
    ENTITIES = 30  # Player, Inimigos, NPCs
    EFFECTS = 40  # Partículas, explosões
    OVERLAY = 50  # Vinhetas, flash de dano
    UI = 60  # HUD, Textos
    DEBUG = 70  # Gizmos, Hitboxes


@dataclass(slots=True)  # slots=True reduces memory usage significantly
class RenderCommand:
    """
    A single atomic instruction to draw something.

    Created every frame for every visible object.
    """

    texture: Texture
    world_position: Vector2
    layer: int
    z_index: float
    rotation: float = 0.0
    scale: Vector2 = field(default_factory=lambda: Vector2(1, 1))
    material: Optional["Material"] = None

    @property
    def material_id(self) -> int:
        """Get the material ID for sorting (0 if no material)."""
        return self.material.id if self.material is not None else 0


@dataclass
class RenderBatch:
    """
    A collection of draw calls that share a common state (Texture + Material).

    This allows backends to use optimized bulk-drawing methods.

    Supports two modes:
    - Fast path: transforms_enabled=False, only positions (for simple sprites)
    - Transform path: transforms_enabled=True, includes rotation/scale data
    """

    texture: Texture
    # List of (screen_x, screen_y) tuples for this texture
    destinations: List[tuple[float, float]]

    # Optional transform data (only used when transforms_enabled=True)
    rotations: List[float] = field(default_factory=list)
    scales: List[tuple[float, float]] = field(default_factory=list)
    transforms_enabled: bool = False

    # Optional material for custom shaders/uniforms
    material: Optional["Material"] = None
