"""Graphics-specific types and enumerations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

from pyguara.common.types import Color, Rect, Vector2
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

    # The depth key *within* `layer` and `sort_group`. For an ordinary
    # sprite this is its own `z_index`; for a y-sorted one `RenderSystem`
    # puts the submitted world Y here, so the queue has one number to
    # compare either way rather than a branch per command inside the sort.
    z_index: float

    # Coarse ordering within the layer, compared before `z_index`. Lets a
    # cluster of sprites sort as one unit against the scenery -- see
    # `Sprite.sort_group`.
    sort_group: int = 0

    rotation: float = 0.0
    scale: Vector2 = field(default_factory=lambda: Vector2(1, 1))
    material: Material | None = None
    color: Color = field(default_factory=lambda: Color(255, 255, 255, 255))

    # The sub-rectangle of `texture` to draw, in pixels, or None for all of
    # it. This is what lets an atlas be an atlas: two commands naming
    # different regions of one texture still batch together, where slicing
    # the sheet into separate textures forces a batch break per region.
    source_rect: Rect | None = None

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
    destinations: list[tuple[float, float]]

    # Optional transform data (only used when transforms_enabled=True)
    rotations: list[float] = field(default_factory=list)
    scales: list[tuple[float, float]] = field(default_factory=list)
    transforms_enabled: bool = False

    # Optional per-instance tint (only used when colors_enabled=True). RGBA
    # tuples, not Color instances, to keep the hot path free of per-instance
    # dataclass overhead -- same reasoning as `destinations` staying tuples.
    colors: list[tuple[int, int, int, int]] = field(default_factory=list)
    colors_enabled: bool = False

    # Optional per-instance sub-rectangle of `texture`, in pixels. Rects
    # rather than normalised UVs, because that is what `AtlasRegion.rect`
    # and a sprite sheet's grid already speak; the backend divides by the
    # texture's dimensions, which it is holding anyway.
    #
    # A region also sets the sprite's drawn size: an atlas entry is the
    # size of its rect, not of the sheet it sits in. `None` in the list
    # means "all of the texture", so one batch can mix atlas entries with
    # ordinary sprites.
    source_rects: list[Rect | None] = field(default_factory=list)
    source_rects_enabled: bool = False

    # Optional material for custom shaders/uniforms
    material: Material | None = None


class ShapeKind(IntEnum):
    """Which primitive a packed shape row describes.

    The values are the ones the ModernGL shape shader branches on, so a
    row's kind column and the bucket it lands in are the same number.
    """

    RECT = 0
    CIRCLE = 1
    LINE = 2


# A packed primitive is eleven floats, in this order:
#
#     0  centre x          in screen pixels
#     1  centre y
#     2  half width        a circle's radius; a capsule's half length
#                          plus its half thickness
#     3  half height       a circle's radius; a capsule's half thickness
#     4  rotation          radians, counter-clockwise
#     5  red               0.0 - 1.0
#     6  green
#     7  blue
#     8  alpha
#     9  stroke width      pixels; 0 fills the shape
#     10 kind              a `ShapeKind` value
#
# This is not a new representation: it is what `GLRenderer.draw_rect`,
# `draw_circle` and `draw_line` have always built and what the shape shader
# reads per instance. It is named and documented here because `ShapeBatch`
# now carries it across a boundary, and a layout that crosses a boundary
# undeclared is how the texture-orientation convention drifted.
SHAPE_INSTANCE_FLOATS = 11


@dataclass(frozen=True, slots=True)
class ShapeBatch:
    """Many primitives of one kind, packed for a single instanced draw.

    `RenderBatch` for shapes. It exists because the per-primitive calls are
    the wrong granularity for anything that draws thousands of them: a
    1000-spark frame spends 55-71% of itself in `draw_circle`/`draw_line`
    call overhead, and handing the rows over in one call removes it
    (measured 8-15x on the render half; see `docs/guides/performance.md`).

    Rows arrive already packed because the producer is usually better
    placed to pack them -- `Sparks`' native pool fills them in Rust, and
    anything that re-walked them element by element in Python would give
    the saving straight back.

    Attributes:
        kind: The primitive every row describes.
        instances: One row of `SHAPE_INSTANCE_FLOATS` floats per primitive,
            in the layout documented above.
    """

    kind: ShapeKind
    instances: Sequence[Sequence[float]]
