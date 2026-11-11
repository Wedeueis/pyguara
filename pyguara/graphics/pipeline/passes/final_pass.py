"""Final render pass - composites the result to the screen.

This pass takes the composed scene framebuffer and blits it to
the default framebuffer (screen) for display.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyguara.common.types import Color
from pyguara.graphics.pipeline.device import FullscreenShader, glsl
from pyguara.graphics.pipeline.render_pass import BaseRenderPass

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.pipeline.graph import RenderGraph

BLIT = FullscreenShader(
    "blit",
    inputs=("u_texture",),
    glsl=glsl("blit.frag"),
    wgsl="""
@fragment
fn fragment(in: Varying) -> @location(0) vec4<f32> {
    return textureSample(u_texture, input_sampler, in.uv);
}
""",
)
"""Copy a buffer to the output."""

_BARS = Color(0, 0, 0, 255)


class FinalPass(BaseRenderPass):
    """Blits the final composed image to the screen.

    This pass:
    1. Reads from the input framebuffer (typically post-processed result)
    2. Renders a fullscreen quad to the default framebuffer
    3. The window system then presents this to the display
    """

    def __init__(
        self,
        ctx: Any = None,
        input_fbo_name: str = "world",
        *,
        enabled: bool = True,
    ) -> None:
        """Initialize the final pass.

        Args:
            ctx: Unused. Accepted so callers written when passes needed a
                ModernGL context keep working; removed in stage E.
            input_fbo_name: Name of the framebuffer to blit from.
            enabled: Whether this pass should execute.
        """
        super().__init__("final", enabled=enabled)
        self._input_fbo_name = input_fbo_name

    @property
    def input_fbo_name(self) -> str:
        """Name of the input framebuffer."""
        return self._input_fbo_name

    @input_fbo_name.setter
    def input_fbo_name(self, value: str) -> None:
        """Set the input framebuffer name."""
        self._input_fbo_name = value

    def execute(self, ctx: moderngl.Context | None, graph: RenderGraph) -> None:
        """Execute the final pass - blit to screen.

        With a letterbox, the whole window is cleared first: the bars are
        the part no pass ever writes, and would otherwise show whatever was
        there -- the previous frame, smeared, or uninitialised memory. The
        letterbox stays the screen's viewport afterwards on purpose: the
        game's own UI composites after the graph runs and belongs inside
        the same frame.

        Args:
            ctx: Unused; the pass runs through `graph.device`.
            graph: The RenderGraph providing access to framebuffers.
        """
        if not self._enabled:
            return
        input_fbo = graph.fbo_manager.get(self._input_fbo_name)
        if input_fbo is None:
            return
        rect = graph.screen_rect
        letterboxed = (rect[2], rect[3]) != graph.window_size
        graph.device.run(
            BLIT,
            {"u_texture": input_fbo},
            {},
            None,
            viewport=rect if letterboxed else None,
            clear=_BARS if letterboxed else None,
        )
