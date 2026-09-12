"""Logic for grouping render calls to minimize CPU/GPU overhead."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyguara.common.types import Color
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.types import RenderBatch, RenderCommand

if TYPE_CHECKING:
    from pyguara.graphics.materials.material import Material

_OPAQUE_WHITE = Color(255, 255, 255, 255)


class Batcher:
    """
    Iterates over sorted commands and groups them.

    Strategy:
    Groups consecutive commands that use the same Texture and Material
    into a single Batch. Supports both simple sprites (fast path) and
    transformed sprites (rotation/scale). Includes static batch caching
    for pre-computed, reusable batches.
    """

    def __init__(self) -> None:
        """Initialize the batcher with static batch cache."""
        # Cache for static sprite batches (pre-computed, reused every frame)
        self._static_batches: dict[int, RenderBatch] = {}
        self._static_batch_keys: list[int] = []

    def create_batches(
        self, sorted_commands: list[RenderCommand], camera: Camera2D, viewport: Viewport
    ) -> list[RenderBatch]:
        """Group compatible commands into batches to minimize draw calls.

        Creates batches with transform data when rotation/scale are non-default,
        and with tint data when any command's color isn't opaque white. Enables
        backends to use a fast path for simple sprites and a slower per-instance
        path only for the batches that actually need transforms and/or tinting.

        Commands are batched by (texture, material_id) combination.
        """
        if not sorted_commands:
            return list(self._static_batches.values())

        batches: list[RenderBatch] = []

        # Initialize first batch state
        current_tex = sorted_commands[0].texture
        current_material: Material | None = sorted_commands[0].material
        current_material_id = sorted_commands[0].material_id
        current_dests: list[tuple[float, float]] = []
        current_rotations: list[float] = []
        current_scales: list[tuple[float, float]] = []
        current_colors: list[tuple[int, int, int, int]] = []
        has_transforms = False
        has_colors = False

        # Optimization: Pre-calculate viewport offset once for the frame.
        # screen_pos = (world * zoom) + offset
        offset = camera.screen_offset(viewport)
        zoom = camera.zoom

        for cmd in sorted_commands:
            # CHECK: Can we continue the current batch?
            # Break batch on texture OR material change
            if cmd.texture is not current_tex or cmd.material_id != current_material_id:
                # 1. Close current batch
                if current_dests:
                    batch = RenderBatch(
                        texture=current_tex,
                        destinations=current_dests,
                        rotations=current_rotations if has_transforms else [],
                        scales=current_scales if has_transforms else [],
                        transforms_enabled=has_transforms,
                        colors=current_colors if has_colors else [],
                        colors_enabled=has_colors,
                        material=current_material,
                    )
                    batches.append(batch)

                # 2. Start new batch
                current_tex = cmd.texture
                current_material = cmd.material
                current_material_id = cmd.material_id
                current_dests = []
                current_rotations = []
                current_scales = []
                current_colors = []
                has_transforms = False
                has_colors = False

            # Transform to Screen Space HERE (CPU) so the Backend just draws
            screen_pos = (cmd.world_position * zoom) + offset
            current_dests.append((screen_pos.x, screen_pos.y))

            # Always collect transform/color data (discarded later if not needed)
            current_rotations.append(cmd.rotation)
            current_scales.append((cmd.scale.x, cmd.scale.y))
            current_colors.append((cmd.color.r, cmd.color.g, cmd.color.b, cmd.color.a))

            # Check if this command has non-default transforms/tint.
            # Compared componentwise rather than against a `Vector2(1, 1)`:
            # building one here allocates a vector per command per frame,
            # to be thrown away immediately. `_OPAQUE_WHITE` on the next
            # line was already hoisted for the same reason.
            if cmd.rotation != 0.0 or cmd.scale.x != 1.0 or cmd.scale.y != 1.0:
                has_transforms = True
            if cmd.color != _OPAQUE_WHITE:
                has_colors = True

        # Append the final batch
        if current_dests:
            batch = RenderBatch(
                texture=current_tex,
                destinations=current_dests,
                rotations=current_rotations if has_transforms else [],
                scales=current_scales if has_transforms else [],
                transforms_enabled=has_transforms,
                colors=current_colors if has_colors else [],
                colors_enabled=has_colors,
                material=current_material,
            )
            batches.append(batch)

        # Prepend static batches (rendered first, cached)
        return list(self._static_batches.values()) + batches
