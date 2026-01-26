"""Vignette post-processing effect.

Darkens the edges of the screen, drawing focus to the center
and creating a cinematic look.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pyguara.graphics.vfx.post_process import PostProcessEffect

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.pipeline.framebuffer import Framebuffer


# Shader directory
_SHADER_DIR = Path(__file__).parent.parent.parent / "backends" / "moderngl" / "shaders"


class VignetteEffect(PostProcessEffect):
    """Vignette effect for darkening screen edges.

    Parameters:
        intensity: How dark the edges get (0.0-1.0, default: 0.5).
        radius: Where the vignette starts from center (default: 0.75).
        softness: Edge softness/feathering (default: 0.45).
    """

    def __init__(
        self,
        ctx: "moderngl.Context",
        *,
        intensity: float = 0.5,
        radius: float = 0.75,
        softness: float = 0.45,
        enabled: bool = True,
    ) -> None:
        """Initialize the vignette effect.

        Args:
            ctx: The ModernGL context.
            intensity: Edge darkness (0.0-1.0).
            radius: Where vignette starts (0.0-1.0 from center).
            softness: Edge transition softness.
            enabled: Whether the effect is active.
        """
        super().__init__("vignette", enabled=enabled)
        self._ctx = ctx

        self.intensity = intensity
        self.radius = radius
        self.softness = softness

        # Shader program
        self._program: Optional["moderngl.Program"] = None
        self._vao: Optional["moderngl.VertexArray"] = None

        self._create_resources()

    def _create_resources(self) -> None:
        """Create shader program."""
        # Load fullscreen quad vertex shader
        vert_path = _SHADER_DIR / "fullscreen_quad.vert"
        frag_path = _SHADER_DIR / "vignette.frag"

        with open(vert_path, "r") as f:
            vert_source = f.read()
        with open(frag_path, "r") as f:
            frag_source = f.read()

        self._program = self._ctx.program(
            vertex_shader=vert_source, fragment_shader=frag_source
        )
        self._vao = self._ctx.vertex_array(self._program, [])

    def apply(
        self,
        ctx: "moderngl.Context",
        input_fbo: "Framebuffer",
        output_fbo: "Framebuffer",
    ) -> None:
        """Apply the vignette effect.

        Args:
            ctx: The ModernGL context.
            input_fbo: Source framebuffer.
            output_fbo: Destination framebuffer.
        """
        if self._program is None or self._vao is None:
            return

        output_fbo.bind()
        input_fbo.texture.use(0)

        self._program["u_texture"] = 0
        self._program["u_intensity"] = self.intensity
        self._program["u_radius"] = self.radius
        self._program["u_softness"] = self.softness

        self._vao.render(mode=ctx.TRIANGLE_STRIP, vertices=4)

    def release(self) -> None:
        """Release GPU resources."""
        if self._vao is not None:
            self._vao.release()
            self._vao = None
        if self._program is not None:
            self._program.release()
            self._program = None
