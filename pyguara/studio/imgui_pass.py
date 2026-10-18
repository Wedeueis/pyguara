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

    from pyguara.graphics.pipeline.graph import RenderGraph
    from pyguara.studio.layer import EditorLayer

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
        clear_colour: tuple[float, float, float] | None = None,
    ) -> None:
        """Initialize the pass.

        Args:
            layer: The editor layer to draw, whose teardown this pass owns
                -- see `release()`.
            width: Initial target width in pixels.
            height: Initial target height in pixels.
            enabled: Whether the pass draws.
            clear_colour: Clear the screen to this before drawing. None
                leaves whatever is on screen, which is what the plain
                editor wants -- it has no viewport panel, so the game
                showing through its dockspace *is* the view. Studio sets
                one, because it shows the frame inside a Viewport panel
                and a second copy of the game behind the panels is the
                thing that makes it look unfinished.
        """
        # `after_ui`, so the editor is drawn on top of everything the game
        # drew -- its HUD included. As an ordinary pass it ran mid-chain
        # and `UIRenderer.present()` composited the game's UI over the
        # panels afterwards.
        super().__init__(PASS_NAME, enabled=enabled, after_ui=True)
        self._layer = layer
        self._width = width
        self._height = height
        self._clear_colour = clear_colour

    @property
    def layer(self) -> EditorLayer:
        """The editor layer this pass draws."""
        return self._layer

    def set_clear_colour(self, colour: tuple[float, float, float] | None) -> None:
        """Clear the screen to `colour` before drawing, or stop clearing.

        Args:
            colour: An RGB triple in 0..1, or None to leave the screen as
                whatever the rest of the frame left on it.
        """
        self._clear_colour = colour

    def execute(self, ctx: moderngl.Context, graph: RenderGraph) -> None:
        """Draw the editor onto the default framebuffer.

        Runs after the game's UI has been composited, not with the rest
        of the chain -- see `after_ui` on `BaseRenderPass`.

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
        # And so is the viewport, which is the part that bit. `ctx.screen`'s
        # viewport is where the **game's** frame goes: with
        # `display.keep_aspect` the graph narrows it to the letterbox, so
        # that the game and its HUD land inside their own frame. The editor
        # is not the game -- it owns the whole window -- and inheriting that
        # viewport squeezed every panel into the letterbox. On a 2000x876
        # window that is a horizontal scale of 0.73: compressed text, and a
        # round sun in the Viewport panel drawn as an ellipse taller than
        # wide. An ultrawide display makes it worse still.
        #
        # Put back afterwards, because the game's UI composites after the
        # graph runs and has to land inside the letterbox rather than
        # spilling onto the bars.
        #
        # `ctx.screen` is `None` on a standalone (offscreen) context, where
        # there is no default framebuffer to bind; the editor then draws
        # into whatever the caller bound, which is what an offscreen
        # capture wants anyway.
        screen = ctx.screen
        previous = screen.viewport if screen is not None else None
        if screen is not None:
            screen.viewport = (0, 0, self._width, self._height)
            screen.use()
            if self._clear_colour is not None:
                # Nothing else writes the screen when Studio owns it: the
                # final blit is disabled so the game appears only inside
                # the Viewport panel, which leaves the default framebuffer
                # holding last frame's contents until something clears it.
                screen.clear(*self._clear_colour, 1.0)
        try:
            self._layer.render(self._width, self._height)
        finally:
            if screen is not None and previous is not None:
                screen.viewport = previous

    def on_resize(self, width: int, height: int) -> None:
        """Track the new window size.

        Args:
            width: New viewport width.
            height: New viewport height.
        """
        self._width = width
        self._height = height

    def release(self) -> None:
        """Release the editor layer with the graph that drives it.

        The layer owns an ImGui context and, through its renderer, GL
        programs, buffers and textures built on this graph's context. The
        graph releases every pass it holds (`Application.shutdown()` calls
        `RenderGraph.release()`), so routing the layer's teardown through
        here is what keeps those from outliving the context they came from.

        `EditorLayer.release()` is idempotent, so a caller that also
        releases the layer itself is fine.
        """
        self._layer.release()
