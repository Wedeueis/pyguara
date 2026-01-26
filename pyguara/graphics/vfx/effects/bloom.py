"""Bloom post-processing effect.

Creates a glowing halo around bright areas by:
1. Extracting bright pixels (threshold pass)
2. Blurring the bright pixels (Gaussian blur)
3. Adding the blur back to the original (composite pass)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pyguara.graphics.vfx.post_process import PostProcessEffect

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.pipeline.framebuffer import Framebuffer, FramebufferManager


# Shader directory
_SHADER_DIR = Path(__file__).parent.parent.parent / "backends" / "moderngl" / "shaders"


class BloomEffect(PostProcessEffect):
    """Bloom effect for glowing bright areas.

    Parameters:
        threshold: Brightness level above which pixels glow (default: 0.8).
        intensity: Strength of the glow (default: 1.0).
        blur_passes: Number of blur iterations (default: 2).
    """

    def __init__(
        self,
        ctx: "moderngl.Context",
        fbo_manager: "FramebufferManager",
        *,
        threshold: float = 0.8,
        intensity: float = 1.0,
        blur_passes: int = 2,
        enabled: bool = True,
    ) -> None:
        """Initialize the bloom effect.

        Args:
            ctx: The ModernGL context.
            fbo_manager: Manager for creating temp framebuffers.
            threshold: Brightness threshold (0.0-1.0).
            intensity: Bloom intensity multiplier.
            blur_passes: Number of blur iterations.
            enabled: Whether the effect is active.
        """
        super().__init__("bloom", enabled=enabled)
        self._ctx = ctx
        self._fbo_manager = fbo_manager

        self.threshold = threshold
        self.intensity = intensity
        self.blur_passes = blur_passes

        # Shader programs
        self._threshold_program: Optional["moderngl.Program"] = None
        self._blur_program: Optional["moderngl.Program"] = None
        self._composite_program: Optional["moderngl.Program"] = None
        self._vao: Optional["moderngl.VertexArray"] = None

        # Internal FBO names
        self._bright_fbo_name = "_bloom_bright"
        self._blur_fbo_name = "_bloom_blur"

        self._create_resources()

    def _create_resources(self) -> None:
        """Create shader programs."""
        # Load fullscreen quad vertex shader
        vert_path = _SHADER_DIR / "fullscreen_quad.vert"
        with open(vert_path, "r") as f:
            vert_source = f.read()

        # Threshold shader
        threshold_path = _SHADER_DIR / "bloom_threshold.frag"
        with open(threshold_path, "r") as f:
            threshold_source = f.read()
        self._threshold_program = self._ctx.program(
            vertex_shader=vert_source, fragment_shader=threshold_source
        )

        # Blur shader
        blur_path = _SHADER_DIR / "blur.frag"
        with open(blur_path, "r") as f:
            blur_source = f.read()
        self._blur_program = self._ctx.program(
            vertex_shader=vert_source, fragment_shader=blur_source
        )

        # Composite shader
        composite_path = _SHADER_DIR / "bloom_composite.frag"
        with open(composite_path, "r") as f:
            composite_source = f.read()
        self._composite_program = self._ctx.program(
            vertex_shader=vert_source, fragment_shader=composite_source
        )

        # Create VAO (fullscreen quad uses gl_VertexID)
        self._vao = self._ctx.vertex_array(self._threshold_program, [])

    def apply(
        self,
        ctx: "moderngl.Context",
        input_fbo: "Framebuffer",
        output_fbo: "Framebuffer",
    ) -> None:
        """Apply the bloom effect.

        Args:
            ctx: The ModernGL context.
            input_fbo: Source framebuffer.
            output_fbo: Destination framebuffer.
        """
        if self._threshold_program is None or self._blur_program is None:
            return
        if self._composite_program is None or self._vao is None:
            return

        # Get temp framebuffers
        bright_fbo = self._fbo_manager.get_or_create(self._bright_fbo_name)
        blur_fbo = self._fbo_manager.get_or_create(self._blur_fbo_name)

        texel_size = (1.0 / input_fbo.width, 1.0 / input_fbo.height)

        # Pass 1: Extract bright pixels
        bright_fbo.bind()
        input_fbo.texture.use(0)
        self._threshold_program["u_texture"] = 0
        self._threshold_program["u_threshold"] = self.threshold
        self._vao = self._ctx.vertex_array(self._threshold_program, [])
        self._vao.render(mode=ctx.TRIANGLE_STRIP, vertices=4)

        # Pass 2: Blur bright pixels (ping-pong horizontal/vertical)
        blur_vao = self._ctx.vertex_array(self._blur_program, [])
        self._blur_program["u_texel_size"] = texel_size

        for _ in range(self.blur_passes):
            # Horizontal blur: bright -> blur
            blur_fbo.bind()
            bright_fbo.texture.use(0)
            self._blur_program["u_texture"] = 0
            self._blur_program["u_direction"] = (1.0, 0.0)
            blur_vao.render(mode=ctx.TRIANGLE_STRIP, vertices=4)

            # Vertical blur: blur -> bright
            bright_fbo.bind()
            blur_fbo.texture.use(0)
            self._blur_program["u_texture"] = 0
            self._blur_program["u_direction"] = (0.0, 1.0)
            blur_vao.render(mode=ctx.TRIANGLE_STRIP, vertices=4)

        blur_vao.release()

        # Pass 3: Composite bloom with original
        output_fbo.bind()
        input_fbo.texture.use(0)
        bright_fbo.texture.use(1)
        composite_vao = self._ctx.vertex_array(self._composite_program, [])
        self._composite_program["u_scene"] = 0
        self._composite_program["u_bloom"] = 1
        self._composite_program["u_intensity"] = self.intensity
        composite_vao.render(mode=ctx.TRIANGLE_STRIP, vertices=4)
        composite_vao.release()

    def release(self) -> None:
        """Release GPU resources."""
        if self._vao is not None:
            self._vao.release()
            self._vao = None
        if self._threshold_program is not None:
            self._threshold_program.release()
            self._threshold_program = None
        if self._blur_program is not None:
            self._blur_program.release()
            self._blur_program = None
        if self._composite_program is not None:
            self._composite_program.release()
            self._composite_program = None
