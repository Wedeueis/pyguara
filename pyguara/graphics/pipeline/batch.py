"""Logic for grouping render calls to minimize CPU/GPU overhead."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyguara.common.types import Rect
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.types import RenderBatch, RenderCommand

if TYPE_CHECKING:
    from pyguara.graphics.materials.material import Material

_NEUTRAL_SCALE = (1.0, 1.0)
_OPAQUE_WHITE = (255, 255, 255, 255)


class Batcher:
    """Group sorted render commands into draw batches.

    Consecutive commands sharing a texture and a material become one
    batch, so a backend issues one draw call per group. Rotation, scale,
    tint and atlas source rect are optional parallel columns, filled only
    from the first command in a batch that needs one.

    Grouping is by `material_id`, not object identity, so a copied or
    deserialised material batches with its original. The loop works on
    floats, not `Vector2`; see `docs/guides/performance.md`.
    """

    def create_batches(
        self, sorted_commands: list[RenderCommand], camera: Camera2D, viewport: Viewport
    ) -> list[RenderBatch]:
        """Group compatible commands into batches to minimize draw calls.

        Commands are grouped by `(texture, material_id)`, and only
        consecutive ones -- the caller is expected to have sorted, which
        `RenderQueue.sort` does on `(layer, sort_group, z_index,
        material_id)`.

        A batch carries transform, tint and source-rect columns only when
        some command in it needs them, so a backend can keep a fast path
        for plain sprites. Those columns are either empty or exactly as
        long as `destinations`; nothing in between.

        Args:
            sorted_commands: The frame's commands, already sorted.
            camera: Supplies the zoom and the world-to-screen offset.
            viewport: The region being drawn into.

        Returns:
            One batch per run of compatible commands, in command order.
        """
        if not sorted_commands:
            return []

        batches: list[RenderBatch] = []

        # Pre-calculated once for the frame, then applied as
        # `x * zoom + offset_x`. See the class docstring: doing this with
        # Vector2 arithmetic instead allocates two vectors per command and
        # was the single largest cost in here.
        offset = camera.screen_offset(viewport)
        zoom = camera.zoom
        offset_x = offset.x
        offset_y = offset.y

        first = sorted_commands[0]
        current_tex = first.texture
        current_material: Material | None = first.material
        current_material_id = first.material_id
        current_dests: list[tuple[float, float]] = []
        current_rotations: list[float] = []
        current_scales: list[tuple[float, float]] = []
        current_colors: list[tuple[int, int, int, int]] = []
        current_source_rects: list[Rect | None] = []
        has_transforms = False
        has_colors = False
        has_source_rects = False

        for cmd in sorted_commands:
            # Break on a texture or material change. The `is not` on the
            # materials short-circuits the `material_id` property away
            # entirely when neither command has a material, which is every
            # command in a game that uses none; when the objects do
            # differ, the ids still decide, so two materials sharing an id
            # do not split a batch.
            material = cmd.material
            if cmd.texture is not current_tex or (
                material is not current_material
                and cmd.material_id != current_material_id
            ):
                if current_dests:
                    batches.append(
                        RenderBatch(
                            texture=current_tex,
                            destinations=current_dests,
                            rotations=current_rotations if has_transforms else [],
                            scales=current_scales if has_transforms else [],
                            transforms_enabled=has_transforms,
                            colors=current_colors if has_colors else [],
                            colors_enabled=has_colors,
                            source_rects=(
                                current_source_rects if has_source_rects else []
                            ),
                            source_rects_enabled=has_source_rects,
                            material=current_material,
                        )
                    )

                current_tex = cmd.texture
                current_material = material
                current_material_id = cmd.material_id
                current_dests = []
                current_rotations = []
                current_scales = []
                current_colors = []
                current_source_rects = []
                has_transforms = False
                has_colors = False
                has_source_rects = False

            position = cmd.world_position
            current_dests.append(
                (position.x * zoom + offset_x, position.y * zoom + offset_y)
            )

            rotation = cmd.rotation
            scale = cmd.scale
            scale_x = scale.x
            scale_y = scale.y
            if has_transforms:
                current_rotations.append(rotation)
                current_scales.append((scale_x, scale_y))
            elif rotation != 0.0 or scale_x != 1.0 or scale_y != 1.0:
                # The first transformed command in this batch. Everything
                # already appended was neutral, so backfill it -- at most
                # once per batch. `len(current_dests) - 1` excludes the
                # destination appended for *this* command just above.
                neutral = len(current_dests) - 1
                current_rotations = [0.0] * neutral
                current_rotations.append(rotation)
                current_scales = [_NEUTRAL_SCALE] * neutral
                current_scales.append((scale_x, scale_y))
                has_transforms = True

            color = cmd.color
            red = color.r
            green = color.g
            blue = color.b
            alpha = color.a
            if has_colors:
                current_colors.append((red, green, blue, alpha))
            elif red != 255 or green != 255 or blue != 255 or alpha != 255:
                current_colors = [_OPAQUE_WHITE] * (len(current_dests) - 1)
                current_colors.append((red, green, blue, alpha))
                has_colors = True

            # None means "the whole texture", resolved by the backend,
            # which is holding the dimensions anyway -- filling a Rect
            # here would allocate one per sprite per frame to say nothing.
            #
            # A source rect does *not* break the batch: two regions of one
            # atlas belong in the same draw call, which is the entire
            # point of having an atlas.
            source_rect = cmd.source_rect
            if has_source_rects:
                current_source_rects.append(source_rect)
            elif source_rect is not None:
                current_source_rects = [None] * (len(current_dests) - 1)
                current_source_rects.append(source_rect)
                has_source_rects = True

        if current_dests:
            batches.append(
                RenderBatch(
                    texture=current_tex,
                    destinations=current_dests,
                    rotations=current_rotations if has_transforms else [],
                    scales=current_scales if has_transforms else [],
                    transforms_enabled=has_transforms,
                    colors=current_colors if has_colors else [],
                    colors_enabled=has_colors,
                    source_rects=current_source_rects if has_source_rects else [],
                    source_rects_enabled=has_source_rects,
                    material=current_material,
                )
            )

        return batches
