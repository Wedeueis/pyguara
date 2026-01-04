"""Logic for grouping render calls to minimize CPU/GPU overhead."""

from typing import List, Tuple, cast
from pyguara.common.types import Vector2
from pyguara.graphics.types import RenderCommand, RenderBatch
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.viewport import Viewport


class Batcher:
    """
    Iterates over sorted commands and groups them.

    Strategy:
    Groups consecutive commands that use the same Texture into a single Batch.
    This creates 'Texture Atlas' behavior dynamically.
    """

    def create_batches(
        self, sorted_commands: List[RenderCommand], camera: Camera2D, viewport: Viewport
    ) -> List[RenderBatch]:
        """Group compatible commands into batches to minimize draw calls."""
        if not sorted_commands:
            return []

        batches: List[RenderBatch] = []

        # Initialize first batch state
        current_tex = sorted_commands[0].texture
        current_dests: List[Tuple[float, float]] = []

        # Optimization: Pre-calculate viewport offset
        # screen_pos = (world * zoom) + offset
        offset = cast(
            Vector2,
            (viewport.center_vec - (camera.position * camera.zoom)) + viewport.position,
        )
        zoom = camera.zoom

        for cmd in sorted_commands:
            # CHECK: Can we continue the current batch?
            # In a basic engine, we only check if Texture is the same.
            # (If we supported Shaders/BlendModes, we would check those too)
            if cmd.texture is not current_tex:
                # 1. Close current batch
                if current_dests:
                    batches.append(RenderBatch(current_tex, current_dests))

                # 2. Start new batch
                current_tex = cmd.texture
                current_dests = []

            # Transform to Screen Space HERE (CPU) so the Backend just draws
            screen_pos = cast(Vector2, (cmd.world_position * zoom) + offset)

            # For Pygame 'blits', we just need the tuple (x, y)
            current_dests.append((screen_pos.x, screen_pos.y))

        # Append the final straggler batch
        if current_dests:
            batches.append(RenderBatch(current_tex, current_dests))

        return batches
