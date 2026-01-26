"""Final render pass - composites the result to the screen.

This pass takes the composed scene framebuffer and blits it to
the default framebuffer (screen) for display.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pyguara.graphics.pipeline.render_pass import BaseRenderPass

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.pipeline.graph import RenderGraph


# Shader file paths
_SHADER_DIR = Path(__file__).parent.parent.parent / "backends" / "moderngl" / "shaders"


class FinalPass(BaseRenderPass):
    """Blits the final composed image to the screen.

    This pass:
    1. Reads from the input framebuffer (typically post-processed result)
    2. Renders a fullscreen quad to the default framebuffer
    3. The window system then presents this to the display
    """

    def __init__(
        self,
        ctx: "moderngl.Context",
        input_fbo_name: str = "world",
        *,
        enabled: bool = True,
    ) -> None:
        """Initialize the final pass.

        Args:
            ctx: The ModernGL rendering context.
            input_fbo_name: Name of the framebuffer to blit from.
            enabled: Whether this pass should execute.
        """
        super().__init__("final", enabled=enabled)
        self._ctx = ctx
        self._input_fbo_name = input_fbo_name

        # Create shader program for fullscreen blit
        self._program: Optional["moderngl.Program"] = None
        self._vao: Optional["moderngl.VertexArray"] = None
        self._create_resources()

    def _create_resources(self) -> None:
        """Create shader program and VAO for fullscreen quad."""
        vert_path = _SHADER_DIR / "fullscreen_quad.vert"
        frag_path = _SHADER_DIR / "blit.frag"

        with open(vert_path, "r") as f:
            vert_source = f.read()

        with open(frag_path, "r") as f:
            frag_source = f.read()

        self._program = self._ctx.program(
            vertex_shader=vert_source,
            fragment_shader=frag_source,
        )

        # Create VAO for fullscreen quad (no vertex buffers needed)
        self._vao = self._ctx.vertex_array(self._program, [])

    @property
    def input_fbo_name(self) -> str:
        """Name of the input framebuffer."""
        return self._input_fbo_name

    @input_fbo_name.setter
    def input_fbo_name(self, value: str) -> None:
        """Set the input framebuffer name."""
        self._input_fbo_name = value

    def execute(self, ctx: "moderngl.Context", graph: "RenderGraph") -> None:
        """Execute the final pass - blit to screen.

        Args:
            ctx: The ModernGL rendering context.
            graph: The RenderGraph providing access to framebuffers.
        """
        if not self._enabled:
            return

        if self._program is None or self._vao is None:
            return

        # Get the input framebuffer
        input_fbo = graph.fbo_manager.get(self._input_fbo_name)
        if input_fbo is None:
            # If input doesn't exist, nothing to blit
            return

        # Bind the default framebuffer (screen)
        ctx.screen.use()

        # Bind the input texture
        input_fbo.texture.use(0)
        self._program["u_texture"] = 0

        # Draw fullscreen quad (4 vertices for triangle strip)
        self._vao.render(mode=self._ctx.TRIANGLE_STRIP, vertices=4)

    def release(self) -> None:
        """Release GPU resources."""
        if self._vao is not None:
            self._vao.release()
            self._vao = None
        if self._program is not None:
            self._program.release()
            self._program = None
