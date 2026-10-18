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
    """Iterates over sorted commands and groups them.

    Groups consecutive commands sharing a texture and a material into one
    batch, so a backend issues one draw call per group rather than one per
    sprite. Rotation, scale, per-instance tint and atlas source rects
    travel as optional parallel columns, which is what lets sprites that
    differ in any of those still share a draw call.

    **This loop is the engine's largest single Python cost at scale**, so
    what it does *not* do matters as much as what it does. At 20,000
    sprites it used to take 73 ms -- more than four frames -- and almost
    none of that was the grouping. Three things were paid per command and
    thrown away, and removing them is 4.4x to 5.8x at 20,000 sprites and
    6.8x to 7.3x at 1,000, for batches that are identical:

    **The screen transform is four float operations, not two vectors.**
    `(world_position * zoom) + offset` allocates a `Vector2` for the
    product and another for the sum, per command, per frame, both dead by
    the next line. `Vector2` subclasses `pymunk.Vec2d`, so each one is a
    real object with a real allocation. Multiplying and adding the
    components directly is the same two float operations in the same
    order -- bit-identical, and `test_destinations_are_the_camera_
    transform_exactly` asserts that with `==` rather than a tolerance.
    **This single change is 2.8x to 3.9x of it**, which is worth knowing
    before reaching for a faster language: the cost was never the loop.

    **An optional column is filled only once something needs it.** This
    used to collect rotations, scales, colours and source rects for every
    command and discard all four if the batch's flag stayed false -- the
    common case, since most sprites are upright, untinted and whole. The
    price of filling lazily is that the first non-neutral command has to
    backfill the neutral value for the commands already appended, which
    happens at most once per field per batch.

    **The tint test is componentwise.** `color != _OPAQUE_WHITE` against a
    `Color` runs the dataclass `__eq__`, which builds two tuples and
    compares them, per command. Comparing four ints does not. It is worth
    a measurement of its own: the tinted case used to be *slower* than the
    untinted one and is now faster, because an untinted frame pays the
    comparison 20,000 times and never the append.

    A fourth, smaller one: the batch-break check consults the
    `material_id` property only when the two material objects differ, so a
    game using no materials never calls it. Grouping is still by **id**
    and not by identity -- `Material._id` is an ordinary field, so a
    copied or deserialised material carries the id it was given, and
    `test_two_materials_with_the_same_id_stay_in_one_batch` pins that.

    There used to be a fifth thing: a `_static_batches` dict, described in
    this docstring as "static batch caching for pre-computed, reusable
    batches", which **nothing in the engine or the tests ever wrote to**.
    It cost a `list()` and a list concatenation per frame to prepend
    nothing. If pre-computed static batches are wanted, they want
    designing against a caller that has one; an always-empty dict was not
    a head start on that.

    `tests/test_batcher_output.py` is the oracle for all of it, and
    `tests/visual/` records the ordered backend call stream a frame
    produces -- a changed snapshot there is a changed frame.
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
