"""The core Rendering System that orchestrates the pipeline."""

from typing import Optional

from pyguara.common.types import Color
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.batch import Batcher
from pyguara.graphics.pipeline.queue import RenderQueue
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.protocols import IRenderer, Renderable
from pyguara.graphics.types import RenderCommand


class RenderSystem:
    """
    Manages the rendering pipeline: Sorting, Batching, and Drawing.

    Coordinates the submission of renderables, sorting by Z-index,
    batching for performance, and dispatching to the backend.
    """

    def __init__(self, backend: IRenderer):
        """
        Initialize with a specific backend.

        Args:
            backend: The concrete renderer implementation (e.g., PygameRenderer).
        """
        self._backend = backend
        self._queue = RenderQueue()
        self._batcher = Batcher()

        # Optimization: persistent viewport to avoid per-frame allocation
        self._default_viewport: Optional[Viewport] = None

    def submit(self, item: Renderable) -> None:
        """
        Add a renderable object to the current frame's queue.

        Args:
            item: An entity or component that complies with the Renderable protocol.
        """
        # Direct access - protocol guarantees these attributes exist
        cmd = RenderCommand(
            texture=item.texture,
            world_position=item.position,
            layer=item.layer,
            z_index=item.z_index,
            rotation=item.rotation,
            scale=item.scale,
        )
        self._queue.push(cmd)

    def flush(self, camera: Camera2D, viewport: Optional[Viewport] = None) -> None:
        """
        Process the frame: Sort -> Batch -> Draw.

        Args:
            camera: The active camera for the scene.
            viewport: Optional custom viewport. If None, uses full screen.
        """
        # 1. Setup Defaults (Optimized)
        if viewport is None:
            # Check if we need to (re)create the default viewport
            # We do this if it doesn't exist OR if the window size changed
            win_w, win_h = self._backend.width, self._backend.height

            if (
                self._default_viewport is None
                or self._default_viewport.width != win_w
                or self._default_viewport.height != win_h
            ):
                self._default_viewport = Viewport.create_fullscreen(win_w, win_h)

            viewport = self._default_viewport

        self._backend.set_viewport(viewport)
        self._backend.clear(color=Color(0, 0, 0))

        # 2. Sort (Critical for Z-Index / Painter's Algorithm)
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
        # We clear the queue so it's ready for the next frame
        self._queue.clear()
