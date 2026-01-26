"""Logic for grouping render calls to minimize CPU/GPU overhead."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Tuple, Dict, Optional

from pyguara.common.types import Vector2
from pyguara.graphics.types import RenderCommand, RenderBatch
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.viewport import Viewport

if TYPE_CHECKING:
    from pyguara.graphics.materials.material import Material


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
        self._static_batches: Dict[int, RenderBatch] = {}
        self._static_batch_keys: List[int] = []

    def create_batches(
        self, sorted_commands: List[RenderCommand], camera: Camera2D, viewport: Viewport
    ) -> List[RenderBatch]:
        """Group compatible commands into batches to minimize draw calls.

        Creates batches with transform data when rotation/scale are non-default.
        Enables backends to use fast path for simple sprites and transform path
        for rotated/scaled sprites.

        Commands are batched by (texture, material_id) combination.
        """
        if not sorted_commands:
            return list(self._static_batches.values())

        batches: List[RenderBatch] = []

        # Initialize first batch state
        current_tex = sorted_commands[0].texture
        current_material: Optional["Material"] = sorted_commands[0].material
        current_material_id = sorted_commands[0].material_id
        current_dests: List[Tuple[float, float]] = []
        current_rotations: List[float] = []
        current_scales: List[Tuple[float, float]] = []
        has_transforms = False

        # Optimization: Pre-calculate viewport offset
        # screen_pos = (world * zoom) + offset
        offset = (
            viewport.center_vec - (camera.position * camera.zoom)
        ) + viewport.position
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
                has_transforms = False

            # Transform to Screen Space HERE (CPU) so the Backend just draws
            screen_pos = (cmd.world_position * zoom) + offset
            current_dests.append((screen_pos.x, screen_pos.y))

            # Always collect transform data (we'll discard it later if not needed)
            current_rotations.append(cmd.rotation)
            current_scales.append((cmd.scale.x, cmd.scale.y))

            # Check if this command has non-default transforms
            if cmd.rotation != 0.0 or cmd.scale != Vector2(1, 1):
                has_transforms = True

        # Append the final batch
        if current_dests:
            batch = RenderBatch(
                texture=current_tex,
                destinations=current_dests,
                rotations=current_rotations if has_transforms else [],
                scales=current_scales if has_transforms else [],
                transforms_enabled=has_transforms,
                material=current_material,
            )
            batches.append(batch)

        # Prepend static batches (rendered first, cached)
        return list(self._static_batches.values()) + batches
