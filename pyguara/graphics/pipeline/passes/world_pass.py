"""World render pass - renders game sprites to a framebuffer.

This pass collects all submitted renderables, sorts and batches them,
then renders to the world framebuffer for later compositing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pyguara.common.types import Color
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.batch import Batcher
from pyguara.graphics.pipeline.queue import RenderQueue
from pyguara.graphics.pipeline.render_pass import BaseRenderPass
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.protocols import IRenderer, Renderable
from pyguara.graphics.types import RenderCommand

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.pipeline.graph import RenderGraph


# Name of the framebuffer this pass writes to
WORLD_FBO_NAME = "world"


class WorldPass(BaseRenderPass):
    """Renders game world sprites to the world framebuffer.

    This pass:
    1. Accepts submitted renderables throughout the frame
    2. Sorts them by layer and z-index
    3. Batches by texture for efficient GPU rendering
    4. Renders to the world framebuffer
    """

    def __init__(
        self,
        backend: IRenderer,
        *,
        clear_color: Color = Color(0, 0, 0, 255),
        enabled: bool = True,
    ) -> None:
        """Initialize the world pass.

        Args:
            backend: The renderer backend for drawing batches.
            clear_color: Background color for clearing the framebuffer.
            enabled: Whether this pass should execute.
        """
        super().__init__("world", enabled=enabled)
        self._backend = backend
        self._clear_color = clear_color
        self._queue = RenderQueue()
        self._batcher = Batcher()

        # Current frame's camera and viewport
        self._camera: Optional[Camera2D] = None
        self._viewport: Optional[Viewport] = None
        self._default_viewport: Optional[Viewport] = None

    @property
    def clear_color(self) -> Color:
        """Background color for the world buffer."""
        return self._clear_color

    @clear_color.setter
    def clear_color(self, value: Color) -> None:
        """Set the background color."""
        self._clear_color = value

    def submit(self, item: Renderable) -> None:
        """Add a renderable to this frame's queue.

        Args:
            item: An entity/component implementing the Renderable protocol.
        """
        cmd = RenderCommand(
            texture=item.texture,
            world_position=item.position,
            layer=item.layer,
            z_index=item.z_index,
            rotation=item.rotation,
            scale=item.scale,
            material=item.material,
        )
        self._queue.push(cmd)

    def set_camera(self, camera: Camera2D, viewport: Optional[Viewport] = None) -> None:
        """Set the camera and viewport for this frame.

        Args:
            camera: The active camera for world-to-screen transforms.
            viewport: Optional viewport. Defaults to full screen.
        """
        self._camera = camera
        self._viewport = viewport

    def execute(self, ctx: "moderngl.Context", graph: "RenderGraph") -> None:
        """Execute the world render pass.

        Args:
            ctx: The ModernGL rendering context.
            graph: The RenderGraph providing access to framebuffers.
        """
        if not self._enabled:
            return

        # Get or create the world framebuffer
        world_fbo = graph.fbo_manager.get_or_create(WORLD_FBO_NAME)

        # Determine viewport
        viewport = self._viewport
        if viewport is None:
            win_w, win_h = self._backend.width, self._backend.height
            if (
                self._default_viewport is None
                or self._default_viewport.width != win_w
                or self._default_viewport.height != win_h
            ):
                self._default_viewport = Viewport.create_fullscreen(win_w, win_h)
            viewport = self._default_viewport

        # Bind the world framebuffer
        world_fbo.bind()
        world_fbo.clear(self._clear_color)

        # If no camera was set, skip rendering (but still clear)
        if self._camera is None:
            self._queue.clear()
            return

        # Set backend viewport
        self._backend.set_viewport(viewport)

        # Sort and batch
        self._queue.sort()
        batches = self._batcher.create_batches(
            self._queue.commands, self._camera, viewport
        )

        # Render batches
        self._backend.begin_frame()
        for batch in batches:
            self._backend.render_batch(batch)
        self._backend.end_frame()

        # Clear state for next frame
        self._queue.clear()
        self._camera = None
        self._viewport = None

    def on_resize(self, width: int, height: int) -> None:
        """Handle viewport resize.

        Args:
            width: New viewport width.
            height: New viewport height.
        """
        self._default_viewport = None  # Force recreation
