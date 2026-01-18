"""ModernGL implementation of the Rendering Protocol with hardware instancing."""

from pathlib import Path
from typing import Optional

import moderngl
import numpy as np

from pyguara.graphics.protocols import IRenderer
from pyguara.common.types import Vector2, Color, Rect
from pyguara.resources.types import Texture
from pyguara.graphics.types import RenderBatch


# Shader file paths (relative to this module)
_SHADER_DIR = Path(__file__).parent / "shaders"


class ModernGLRenderer(IRenderer):
    """GPU-accelerated renderer using ModernGL with hardware instancing.

    This renderer provides high-performance batch rendering for 10,000+ sprites
    at 60 FPS through hardware instancing. Each unique texture gets its own
    batch, and all sprites sharing that texture are rendered in a single
    draw call.

    The coordinate system matches Pygame:
    - Origin at top-left (0, 0)
    - Y-axis pointing downward
    - Positions in screen pixels
    """

    # Instance data layout: pos(2) + rot(1) + scale(2) + size(2) = 7 floats = 28 bytes
    INSTANCE_FLOATS = 7
    INSTANCE_STRIDE = INSTANCE_FLOATS * 4  # 28 bytes

    # Initial instance buffer capacity (grows as needed)
    INITIAL_CAPACITY = 1024

    def __init__(self, ctx: moderngl.Context, width: int, height: int) -> None:
        """Initialize the renderer.

        Args:
            ctx: The ModernGL context from PygameGLWindow.
            width: Viewport width in pixels.
            height: Viewport height in pixels.
        """
        self._ctx = ctx
        self._width = width
        self._height = height

        # Compile shaders and create program
        self._program = self._create_shader_program()

        # Create static quad geometry
        self._quad_vbo = self._create_quad_vbo()

        # Create dynamic instance buffer
        self._instance_capacity = self.INITIAL_CAPACITY
        self._instance_vbo = self._ctx.buffer(
            reserve=self._instance_capacity * self.INSTANCE_STRIDE
        )

        # Create VAO linking both buffers
        self._vao = self._create_vao()

        # Set up orthographic projection (Y-inverted for Pygame coordinates)
        self._update_projection()

        # Viewport state
        self._current_viewport: Optional[Rect] = None

    def _create_shader_program(self) -> moderngl.Program:
        """Load and compile the sprite shaders."""
        vert_path = _SHADER_DIR / "sprite.vert"
        frag_path = _SHADER_DIR / "sprite.frag"

        with open(vert_path, "r") as f:
            vert_source = f.read()

        with open(frag_path, "r") as f:
            frag_source = f.read()

        return self._ctx.program(
            vertex_shader=vert_source,
            fragment_shader=frag_source,
        )

    def _create_quad_vbo(self) -> moderngl.Buffer:
        """Create the static unit quad geometry.

        The quad goes from -0.5 to 0.5, centered at origin.
        This allows rotation around the center of the sprite.

        Vertex format: x, y, u, v
        """
        # Unit quad vertices (position + UV)
        # Triangle strip order: bottom-left, bottom-right, top-left, top-right
        vertices = np.array(
            [
                # x     y    u    v
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

        return self._ctx.buffer(vertices.tobytes())

    def _create_vao(self) -> moderngl.VertexArray:
        """Create the VAO linking static quad and dynamic instance buffers.

        The /i flag marks attributes as instanced (per-instance rather than per-vertex).
        """
        return self._ctx.vertex_array(
            self._program,
            [
                # Static quad geometry (per-vertex)
                (self._quad_vbo, "2f 2f", "in_vert", "in_uv"),
                # Instance data (per-instance, hence /i)
                (
                    self._instance_vbo,
                    "2f 1f 2f 2f/i",
                    "in_pos",
                    "in_rot",
                    "in_scale",
                    "in_size",
                ),
            ],
        )

    def _update_projection(self) -> None:
        """Set up orthographic projection matrix.

        Creates a matrix that:
        - Maps screen coordinates (0,0) at top-left
        - Y increases downward (matching Pygame)
        - No depth (2D rendering)
        """
        # Orthographic projection with Y-flipped for top-left origin
        left = 0.0
        right = float(self._width)
        bottom = float(self._height)  # Flipped: bottom is at height
        top = 0.0  # Flipped: top is at 0
        near = -1.0
        far = 1.0

        # Orthographic projection matrix (column-major for OpenGL)
        projection = np.array(
            [
                2.0 / (right - left),
                0.0,
                0.0,
                0.0,
                0.0,
                2.0 / (top - bottom),
                0.0,
                0.0,
                0.0,
                0.0,
                -2.0 / (far - near),
                0.0,
                -(right + left) / (right - left),
                -(top + bottom) / (top - bottom),
                -(far + near) / (far - near),
                1.0,
            ],
            dtype="f4",
        )

        uniform = self._program["u_projection"]
        if hasattr(uniform, "write"):
            uniform.write(projection.tobytes())

    @property
    def width(self) -> int:
        """Get the width of the rendering context in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Get the height of the rendering context in pixels."""
        return self._height

    def begin_frame(self) -> None:
        """Prepare for a new frame of rendering."""
        pass

    def end_frame(self) -> None:
        """Finalize the frame rendering."""
        pass

    def clear(self, color: Color) -> None:
        """Clear the screen with the specified color."""
        r = color[0] / 255.0
        g = color[1] / 255.0
        b = color[2] / 255.0
        a = color[3] / 255.0 if len(color) > 3 else 1.0

        self._ctx.clear(r, g, b, a)

    def set_viewport(self, viewport: Rect) -> None:
        """Set the clipping region for subsequent draw calls.

        Args:
            viewport: The clipping rectangle in screen coordinates.
        """
        self._current_viewport = viewport
        # OpenGL viewport has origin at bottom-left, so we need to flip Y
        x = int(viewport[0])
        y = self._height - int(viewport[1]) - int(viewport[3])  # Flip Y
        w = int(viewport[2])
        h = int(viewport[3])
        self._ctx.viewport = (x, y, w, h)

    def reset_viewport(self) -> None:
        """Reset the viewport to cover the full window."""
        self._current_viewport = None
        self._ctx.viewport = (0, 0, self._width, self._height)

    def draw_texture(
        self,
        texture: Texture,
        position: Vector2,
        rotation: float = 0.0,
        scale: Vector2 = Vector2(1, 1),
    ) -> None:
        """Draw a single texture at the given position.

        For single sprite draws. For better performance with many sprites,
        use render_batch() instead.
        """
        import math

        # Convert rotation from degrees to radians
        rot_rad = math.radians(rotation)

        # Pack instance data for a single sprite
        instance_data = np.array(
            [
                position.x,  # pos x
                position.y,  # pos y
                rot_rad,  # rotation
                scale.x,  # scale x
                scale.y,  # scale y
                float(texture.width),  # size x
                float(texture.height),  # size y
            ],
            dtype="f4",
        )

        # Upload to instance buffer
        self._instance_vbo.write(instance_data.tobytes())

        # Bind texture
        gl_texture = texture.native_handle
        gl_texture.use(0)
        self._program["u_texture"] = 0

        # Draw single instance
        self._vao.render(moderngl.TRIANGLE_STRIP, instances=1)

    def render_batch(self, batch: RenderBatch) -> None:
        """Optimized method to draw many instances of the same texture.

        Uses hardware instancing to draw all sprites in a single GPU draw call.
        This is the high-performance path for rendering many sprites.

        Args:
            batch: Collection of sprite positions and transforms sharing one texture.
        """
        import math

        count = len(batch.destinations)
        if count == 0:
            return

        # Ensure buffer capacity
        if count > self._instance_capacity:
            self._grow_instance_buffer(count)

        # Pack instance data into numpy array
        instance_data = np.zeros((count, self.INSTANCE_FLOATS), dtype="f4")

        tex_width = float(batch.texture.width)
        tex_height = float(batch.texture.height)

        if not batch.transforms_enabled:
            # Fast path: no transforms
            for i, (x, y) in enumerate(batch.destinations):
                instance_data[i] = [
                    x,  # pos x
                    y,  # pos y
                    0.0,  # rotation
                    1.0,  # scale x
                    1.0,  # scale y
                    tex_width,  # size x
                    tex_height,  # size y
                ]
        else:
            # Transform path: include rotation and scale
            for i, (x, y) in enumerate(batch.destinations):
                rot = 0.0
                scale_x = 1.0
                scale_y = 1.0

                if i < len(batch.rotations):
                    rot = math.radians(batch.rotations[i])

                if i < len(batch.scales):
                    scale_x, scale_y = batch.scales[i]

                instance_data[i] = [
                    x,  # pos x
                    y,  # pos y
                    rot,  # rotation (radians)
                    scale_x,  # scale x
                    scale_y,  # scale y
                    tex_width,  # size x
                    tex_height,  # size y
                ]

        # Upload instance data to GPU
        self._instance_vbo.write(instance_data.tobytes())

        # Bind texture
        gl_texture = batch.texture.native_handle
        gl_texture.use(0)
        self._program["u_texture"] = 0

        # Draw all instances in one call
        self._vao.render(moderngl.TRIANGLE_STRIP, instances=count)

    def _grow_instance_buffer(self, required_capacity: int) -> None:
        """Grow the instance buffer to accommodate more sprites.

        Doubles the buffer size until it can hold the required capacity.
        """
        new_capacity = self._instance_capacity
        while new_capacity < required_capacity:
            new_capacity *= 2

        # Release old buffer and create new one
        self._instance_vbo.release()
        self._instance_vbo = self._ctx.buffer(
            reserve=new_capacity * self.INSTANCE_STRIDE
        )
        self._instance_capacity = new_capacity

        # Recreate VAO with new instance buffer
        self._vao.release()
        self._vao = self._create_vao()

    def draw_rect(self, rect: Rect, color: Color, width: int = 0) -> None:
        """Draw a rectangle primitive.

        Note: This is a stub implementation. A full implementation would
        require a separate shader for shape primitives.
        """
        # TODO: Implement with dedicated shape shader
        pass

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Draw a circle primitive.

        Note: This is a stub implementation.
        """
        # TODO: Implement with dedicated shape shader
        pass

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Draw a line between two points.

        Note: This is a stub implementation.
        """
        # TODO: Implement with dedicated shape shader
        pass

    def present(self) -> None:
        """Swap display buffers.

        Note: In this architecture, the window backend handles buffer swapping.
        This method exists for protocol compatibility.
        """
        # Buffer swap is handled by PygameGLWindow.present()
        pass

    def release(self) -> None:
        """Release all GPU resources.

        Should be called during shutdown to clean up OpenGL objects.
        """
        if self._vao:
            self._vao.release()
        if self._quad_vbo:
            self._quad_vbo.release()
        if self._instance_vbo:
            self._instance_vbo.release()
        if self._program:
            self._program.release()
