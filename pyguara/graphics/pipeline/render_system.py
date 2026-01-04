"""The core Rendering System that orchestrates the pipeline."""

from typing import Optional

from pyguara.common.types import Color, Vector2
from pyguara.graphics.types import RenderCommand
from pyguara.graphics.protocols import IRenderer, Renderable
from pyguara.graphics.pipeline.queue import RenderQueue
from pyguara.graphics.pipeline.batch import Batcher
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.components.camera import Camera2D


class RenderSystem:
    """Manages the rendering pipeline: Sorting, Batching, and Drawing."""

    def __init__(self, backend: IRenderer):
        """Initialize with a specific backend."""
        self._backend = backend
        self._queue = RenderQueue()
        self._batcher = Batcher()

    def submit(self, item: Renderable) -> None:
        """Add a renderable object to the current frame's queue."""
        cmd = RenderCommand(
            texture=item.texture,
            world_position=item.position,
            layer=item.layer,
            z_index=item.z_index,
            rotation=getattr(item, "rotation", 0.0),
            scale=item.scale if item.scale is not None else Vector2(1, 1),
        )
        self._queue.push(cmd)

    def flush(self, camera: Camera2D, viewport: Optional[Viewport] = None) -> None:
        """Process the frame: Sort -> Batch -> Draw."""
        # 1. Setup Defaults
        if viewport is None:
            viewport = Viewport.create_fullscreen(
                self._backend.width, self._backend.height
            )

        self._backend.set_viewport(viewport)
        self._backend.clear(color=Color(0, 0, 0))  # Or pass a clear color

        # 2. Sort (Critical for Z-Index)
        self._queue.sort()

        # 3. Batch (Critical for Performance)
        # The batcher also handles the World->Screen coordinate transform loop
        batches = self._batcher.create_batches(self._queue.commands, camera, viewport)

        # 4. Execute
        self._backend.begin_frame()
        for batch in batches:
            self._backend.render_batch(batch)
        self._backend.end_frame()

        # 5. Cleanup
        self._queue.clear()
        self._backend.reset_viewport()
