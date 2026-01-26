"""Light render pass - renders dynamic lights to a light map.

This pass collects all lights in the scene and renders them to
a light framebuffer using additive blending. The result is then
composited with the world in the composite pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np

from pyguara.common.types import Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.render_pass import BaseRenderPass
from pyguara.graphics.pipeline.viewport import Viewport

if TYPE_CHECKING:
    import moderngl

    from pyguara.graphics.lighting.light_system import LightingSystem
    from pyguara.graphics.pipeline.graph import RenderGraph


# Shader file paths
_SHADER_DIR = Path(__file__).parent.parent.parent / "backends" / "moderngl" / "shaders"

# Name of the framebuffer this pass writes to
LIGHT_FBO_NAME = "lightmap"


class LightPass(BaseRenderPass):
    """Renders dynamic lights to a light map framebuffer.

    This pass:
    1. Clears the light FBO to ambient color
    2. Renders each light as a radial gradient quad
    3. Uses additive blending so overlapping lights combine
    """

    # Instance data layout: pos(2) + radius(1) + color(3) + intensity(1) + falloff(1) = 8 floats
    INSTANCE_FLOATS = 8
    INSTANCE_STRIDE = INSTANCE_FLOATS * 4  # 32 bytes
    INITIAL_CAPACITY = 64

    def __init__(
        self,
        ctx: "moderngl.Context",
        lighting_system: "LightingSystem",
        *,
        enabled: bool = True,
    ) -> None:
        """Initialize the light pass.

        Args:
            ctx: The ModernGL rendering context.
            lighting_system: The system that provides light data.
            enabled: Whether this pass should execute.
        """
        super().__init__("light", enabled=enabled)
        self._ctx = ctx
        self._lighting_system = lighting_system

        # Current frame's camera (set before execute)
        self._camera: Optional[Camera2D] = None
        self._viewport: Optional[Viewport] = None

        # GPU resources
        self._program: Optional["moderngl.Program"] = None
        self._quad_vbo: Optional["moderngl.Buffer"] = None
        self._instance_vbo: Optional["moderngl.Buffer"] = None
        self._vao: Optional["moderngl.VertexArray"] = None
        self._instance_capacity = self.INITIAL_CAPACITY

        self._create_resources()

    def _create_resources(self) -> None:
        """Create shader program and buffers."""
        # Load shaders
        vert_path = _SHADER_DIR / "light.vert"
        frag_path = _SHADER_DIR / "light.frag"

        with open(vert_path, "r") as f:
            vert_source = f.read()
        with open(frag_path, "r") as f:
            frag_source = f.read()

        self._program = self._ctx.program(
            vertex_shader=vert_source,
            fragment_shader=frag_source,
        )

        # Create unit quad (same as sprite quad)
        vertices = np.array(
            [
                -0.5,
                -0.5,
                0.0,
                0.0,  # Bottom-left
                0.5,
                -0.5,
                1.0,
                0.0,  # Bottom-right
                -0.5,
                0.5,
                0.0,
                1.0,  # Top-left
                0.5,
                0.5,
                1.0,
                1.0,  # Top-right
            ],
            dtype="f4",
        )
        self._quad_vbo = self._ctx.buffer(vertices.tobytes())

        # Create instance buffer
        self._instance_vbo = self._ctx.buffer(
            reserve=self._instance_capacity * self.INSTANCE_STRIDE
        )

        # Create VAO
        self._vao = self._ctx.vertex_array(
            self._program,
            [
                (self._quad_vbo, "2f 2f", "in_vert", "in_uv"),
                (
                    self._instance_vbo,
                    "2f 1f 3f 1f 1f/i",
                    "in_pos",
                    "in_radius",
                    "in_color",
                    "in_intensity",
                    "in_falloff",
                ),
            ],
        )

    def set_camera(self, camera: Camera2D, viewport: Optional[Viewport] = None) -> None:
        """Set the camera and viewport for this frame.

        Args:
            camera: The active camera.
            viewport: Optional viewport.
        """
        self._camera = camera
        self._viewport = viewport

    def execute(self, ctx: "moderngl.Context", graph: "RenderGraph") -> None:
        """Execute the light pass.

        Args:
            ctx: The ModernGL rendering context.
            graph: The RenderGraph providing access to framebuffers.
        """
        if not self._enabled or self._program is None or self._vao is None:
            return

        # Get or create the light framebuffer
        light_fbo = graph.fbo_manager.get_or_create(LIGHT_FBO_NAME)

        # Determine viewport
        viewport = self._viewport
        if viewport is None:
            viewport = Viewport(0, 0, light_fbo.width, light_fbo.height)

        # Bind light FBO
        light_fbo.bind()

        # Clear to ambient color
        ambient = self._lighting_system.get_ambient_normalized()
        light_fbo.fbo.clear(ambient[0], ambient[1], ambient[2], 1.0)

        # Get camera info for world->screen transform
        if self._camera is None:
            # No camera, can't render lights
            return

        # Calculate viewport offset
        viewport_center = Vector2(viewport.width / 2, viewport.height / 2)
        viewport_offset = viewport_center - (self._camera.position * self._camera.zoom)

        # Get lights in screen space
        lights = self._lighting_system.collect_lights_screen_space(
            self._camera.position,
            self._camera.zoom,
            viewport_offset + viewport.position,
        )

        if not lights:
            return

        # Ensure buffer capacity
        if len(lights) > self._instance_capacity:
            self._grow_instance_buffer(len(lights))

        # Pack instance data
        instance_data = np.zeros((len(lights), self.INSTANCE_FLOATS), dtype="f4")
        for i, light in enumerate(lights):
            instance_data[i] = [
                light.position.x,
                light.position.y,
                light.radius,
                light.color[0],
                light.color[1],
                light.color[2],
                light.intensity,
                light.falloff,
            ]

        # Upload to GPU
        if self._instance_vbo is not None:
            self._instance_vbo.write(instance_data.tobytes())

        # Set projection matrix
        self._update_projection(viewport.width, viewport.height)

        # Enable additive blending
        ctx.enable(ctx.BLEND)
        ctx.blend_func = ctx.ONE, ctx.ONE  # Additive: src + dst

        # Render all lights
        if self._vao is not None:
            self._vao.render(mode=ctx.TRIANGLE_STRIP, instances=len(lights))

        # Restore blend mode
        ctx.blend_func = ctx.SRC_ALPHA, ctx.ONE_MINUS_SRC_ALPHA

        # Clear camera for next frame
        self._camera = None
        self._viewport = None

    def _update_projection(self, width: int, height: int) -> None:
        """Set up orthographic projection."""
        # Same as sprite renderer projection
        projection = np.array(
            [
                2.0 / width,
                0.0,
                0.0,
                0.0,
                0.0,
                2.0 / -height,
                0.0,
                0.0,  # Y-flipped
                0.0,
                0.0,
                -1.0,
                0.0,
                -1.0,
                1.0,
                0.0,
                1.0,
            ],
            dtype="f4",
        )

        if self._program is not None:
            uniform = self._program["u_projection"]
            if hasattr(uniform, "write"):
                uniform.write(projection.tobytes())

    def _grow_instance_buffer(self, required_capacity: int) -> None:
        """Grow the instance buffer."""
        new_capacity = self._instance_capacity
        while new_capacity < required_capacity:
            new_capacity *= 2

        if self._instance_vbo is not None:
            self._instance_vbo.release()
        self._instance_vbo = self._ctx.buffer(
            reserve=new_capacity * self.INSTANCE_STRIDE
        )
        self._instance_capacity = new_capacity

        # Recreate VAO
        if self._vao is not None:
            self._vao.release()
        self._vao = self._ctx.vertex_array(
            self._program,
            [
                (self._quad_vbo, "2f 2f", "in_vert", "in_uv"),
                (
                    self._instance_vbo,
                    "2f 1f 3f 1f 1f/i",
                    "in_pos",
                    "in_radius",
                    "in_color",
                    "in_intensity",
                    "in_falloff",
                ),
            ],
        )

    def release(self) -> None:
        """Release GPU resources."""
        if self._vao is not None:
            self._vao.release()
            self._vao = None
        if self._quad_vbo is not None:
            self._quad_vbo.release()
            self._quad_vbo = None
        if self._instance_vbo is not None:
            self._instance_vbo.release()
            self._instance_vbo = None
        if self._program is not None:
            self._program.release()
            self._program = None
