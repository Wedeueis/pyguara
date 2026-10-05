"""The editor's render-graph pass.

Runs last, after `FinalPass` has blitted the composed scene to the default
framebuffer, and draws the editor straight onto it. Being a
`BaseRenderPass` rather than a special case in `Application._render` means
the existing pass loop drives it: `_render_with_graph` already executes
every registered pass in order, so the editor needs no change to the frame
loop to appear.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyguara.graphics.pipeline.render_pass import BaseRenderPass
from pyguara.log import get_logger

if TYPE_CHECKING:
    import moderngl

    from pyguara.editor.layer import EditorLayer
    from pyguara.graphics.pipeline.graph import RenderGraph

logger = get_logger(__name__)

PASS_NAME = "imgui"
"""The pass's name in the graph, for `get_pass()` / `remove_pass()`."""


class ImGuiPass(BaseRenderPass):
    """Draws the editor layer over the finished frame."""

    def __init__(
        self,
        layer: EditorLayer,
        width: int,
        height: int,
        *,
        enabled: bool = True,
    ) -> None:
        """Initialize the pass.

        Args:
            layer: The editor layer to draw. Not owned: releasing the layer
                is `attach_editor`'s caller's job, since the layer outlives
                any single graph.
            width: Initial target width in pixels.
            height: Initial target height in pixels.
            enabled: Whether the pass draws.
        """
        super().__init__(PASS_NAME, enabled=enabled)
        self._layer = layer
        self._width = width
        self._height = height

    @property
    def layer(self) -> EditorLayer:
        """The editor layer this pass draws."""
        return self._layer

    def execute(self, ctx: moderngl.Context, graph: RenderGraph) -> None:
        """Draw the editor onto the default framebuffer.

        Args:
            ctx: The ModernGL context.
            graph: The graph running this pass (unused: the editor reads no
                framebuffers, it draws over whatever is on screen).
        """
        if not self._enabled:
            return

        # Every earlier pass renders into an offscreen FBO and `FinalPass`
        # blits to the screen, but the screen is not guaranteed to still be
        # bound -- a pass added after `final` would have left its own target
        # bound. Binding here makes the editor's target explicit.
        #
        # `ctx.screen` is `None` on a standalone (offscreen) context, where
        # there is no default framebuffer to bind; the editor then draws
        # into whatever the caller bound, which is what an offscreen
        # capture wants anyway.
        if ctx.screen is not None:
            ctx.screen.use()
        self._layer.render(self._width, self._height)

    def on_resize(self, width: int, height: int) -> None:
        """Track the new window size.

        Args:
            width: New viewport width.
            height: New viewport height.
        """
        self._width = width
        self._height = height
