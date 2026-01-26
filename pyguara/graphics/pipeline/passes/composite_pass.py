"""Composite render pass - combines world and light map.

This pass multiplies the world texture by the light map to create
the final lit scene. The result is either written to another FBO
for post-processing or directly to the screen.
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

# Name of the framebuffer this pass writes to
COMPOSITE_FBO_NAME = "composite"


class CompositePass(BaseRenderPass):
    """Composites world and light map into a lit scene.

    This pass:
    1. Reads from the world FBO (rendered sprites)
    2. Reads from the light FBO (accumulated lights)
    3. Multiplies them together (world * light)
    4. Writes to the composite FBO (or screen if no post-processing)
    """

    def __init__(
        self,
        ctx: "moderngl.Context",
        world_fbo_name: str = "world",
        light_fbo_name: str = "lightmap",
        output_fbo_name: Optional[str] = COMPOSITE_FBO_NAME,
        *,
        enabled: bool = True,
    ) -> None:
        """Initialize the composite pass.

        Args:
            ctx: The ModernGL rendering context.
            world_fbo_name: Name of the world framebuffer.
            light_fbo_name: Name of the light map framebuffer.
            output_fbo_name: Name of output FBO (None = screen).
            enabled: Whether this pass should execute.
        """
        super().__init__("composite", enabled=enabled)
        self._ctx = ctx
        self._world_fbo_name = world_fbo_name
        self._light_fbo_name = light_fbo_name
        self._output_fbo_name = output_fbo_name

        # GPU resources
        self._program: Optional["moderngl.Program"] = None
        self._vao: Optional["moderngl.VertexArray"] = None

        self._create_resources()

    def _create_resources(self) -> None:
        """Create shader program and VAO."""
        # Load fullscreen quad vertex shader
        vert_path = _SHADER_DIR / "fullscreen_quad.vert"
        frag_path = _SHADER_DIR / "composite.frag"

        with open(vert_path, "r") as f:
            vert_source = f.read()
        with open(frag_path, "r") as f:
            frag_source = f.read()

        self._program = self._ctx.program(
            vertex_shader=vert_source,
            fragment_shader=frag_source,
        )

        # Create VAO (no vertex buffers needed - fullscreen quad uses gl_VertexID)
        self._vao = self._ctx.vertex_array(self._program, [])

    def execute(self, ctx: "moderngl.Context", graph: "RenderGraph") -> None:
        """Execute the composite pass.

        Args:
            ctx: The ModernGL rendering context.
            graph: The RenderGraph providing access to framebuffers.
        """
        if not self._enabled or self._program is None or self._vao is None:
            return

        # Get input framebuffers
        world_fbo = graph.fbo_manager.get(self._world_fbo_name)
        light_fbo = graph.fbo_manager.get(self._light_fbo_name)

        if world_fbo is None:
            # Can't composite without world
            return

        # Bind output
        if self._output_fbo_name is not None:
            output_fbo = graph.fbo_manager.get_or_create(self._output_fbo_name)
            output_fbo.bind()
        else:
            ctx.screen.use()

        # Bind input textures
        world_fbo.texture.use(0)
        self._program["u_world"] = 0

        if light_fbo is not None:
            light_fbo.texture.use(1)
            self._program["u_lightmap"] = 1
        else:
            # No light map - use world texture as "fully lit" fallback
            world_fbo.texture.use(1)
            self._program["u_lightmap"] = 1

        # Draw fullscreen quad
        self._vao.render(mode=ctx.TRIANGLE_STRIP, vertices=4)

    def release(self) -> None:
        """Release GPU resources."""
        if self._vao is not None:
            self._vao.release()
            self._vao = None
        if self._program is not None:
            self._program.release()
            self._program = None
