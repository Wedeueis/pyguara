"""ModernGL implementation of the Rendering Protocol with hardware instancing."""

import math
from pathlib import Path

import numpy as np
import pygame

import moderngl
from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.backends.moderngl import instancing
from pyguara.graphics.backends.moderngl.texture import GLTextureFactory
from pyguara.graphics.types import RenderBatch
from pyguara.resources.types import Texture

# Shader file paths (relative to this module)
_SHADER_DIR = Path(__file__).parent / "shaders"


class ModernGLRenderer:
    """GPU-accelerated renderer using ModernGL with hardware instancing.

    Each unique texture gets its own batch, and all sprites sharing that
    texture are rendered in a single draw call.

    On what "high-performance" means here, measured rather than assumed
    (see `docs/guides/performance.md`): a 20,000-sprite batch costs about
    16 ms end to end, and **four fifths of that is the Python loop that
    packs the instance array**, not the GPU -- a share that grows with
    sprite count. So the useful lever on this path is CPU-side packing,
    and the bottleneck above it is `Batcher`, which costs roughly three
    times as much again for the same batch.

    The coordinate system matches Pygame:
    - Origin at top-left (0, 0)
    - Y-axis pointing downward
    - Positions in screen pixels
    """

    # Instance data layout: pos(2) + rot(1) + scale(2) + size(2) = 7 floats = 28 bytes.
    # The layout itself, and the packing of it, live in `instancing.py`.
    INSTANCE_FLOATS = instancing.INSTANCE_FLOATS
    INSTANCE_STRIDE = INSTANCE_FLOATS * 4  # 28 bytes

    # Initial instance buffer capacity (grows as needed)
    INITIAL_CAPACITY = 1024

    # Shape instance layout: pos(2) + size(2) + rot(1) + color(4) + width(1)
    # + shape_type(1) = 11 floats = 44 bytes.
    SHAPE_INSTANCE_FLOATS = 11
    SHAPE_INSTANCE_STRIDE = SHAPE_INSTANCE_FLOATS * 4

    # Shape-type discriminants, matching shape.frag's branch.
    SHAPE_TYPE_RECT = 0.0
    SHAPE_TYPE_CIRCLE = 1.0
    SHAPE_TYPE_LINE = 2.0

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

        # CPU-rasterized text: rendered via pygame.font, uploaded as an
        # ephemeral GL texture per draw_text() call and released immediately
        # after -- see draw_text() for why this doesn't use a persistent
        # glyph atlas or a shader-based text pipeline.
        if not pygame.font.get_init():
            pygame.font.init()
        self._font_cache: dict[int, pygame.font.Font] = {}
        self._texture_factory = GLTextureFactory(ctx)

        # Compile shaders and create program
        self._program = self._create_shader_program()

        # Create static quad geometry
        self._quad_vbo = self._create_quad_vbo()

        # Create dynamic instance buffer, and the CPU-side scratch array
        # that is packed and uploaded from. The two are grown together so
        # that a frame's pack never allocates.
        self._instance_capacity = self.INITIAL_CAPACITY
        self._instance_vbo = self._ctx.buffer(
            reserve=self._instance_capacity * self.INSTANCE_STRIDE
        )
        self._instance_scratch = np.empty(
            (self._instance_capacity, self.INSTANCE_FLOATS), dtype="f4"
        )

        # Create VAO linking both buffers
        self._vao = self._create_vao()

        # Compile the shape shader and set up one instance bucket per shape
        # type (rect/circle/line), each independently grown like the sprite
        # instance buffer above.
        self._shape_program = self._create_shape_shader_program()
        self._shape_quad_vbo = self._create_shape_quad_vbo()
        self._shape_capacities: dict[float, int] = {}
        self._shape_vbos: dict[float, moderngl.Buffer] = {}
        self._shape_vaos: dict[float, moderngl.VertexArray] = {}
        self._shape_pending: dict[float, list[list[float]]] = {}
        for shape_type in (
            self.SHAPE_TYPE_RECT,
            self.SHAPE_TYPE_CIRCLE,
            self.SHAPE_TYPE_LINE,
        ):
            self._shape_capacities[shape_type] = self.INITIAL_CAPACITY
            vbo = self._ctx.buffer(
                reserve=self.INITIAL_CAPACITY * self.SHAPE_INSTANCE_STRIDE
            )
            self._shape_vbos[shape_type] = vbo
            self._shape_vaos[shape_type] = self._create_shape_vao(vbo)
            self._shape_pending[shape_type] = []

        # Set up orthographic projection (Y-inverted for Pygame coordinates)
        self._update_projection()

        # Viewport state
        self._current_viewport: Rect | None = None

    def _create_shader_program(self) -> moderngl.Program:
        """Load and compile the sprite shaders."""
        vert_path = _SHADER_DIR / "sprite.vert"
        frag_path = _SHADER_DIR / "sprite.frag"

        with open(vert_path) as f:
            vert_source = f.read()

        with open(frag_path) as f:
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

    def _create_shape_shader_program(self) -> moderngl.Program:
        """Load and compile the unified rect/circle/line SDF shaders."""
        vert_path = _SHADER_DIR / "shape.vert"
        frag_path = _SHADER_DIR / "shape.frag"

        with open(vert_path) as f:
            vert_source = f.read()

        with open(frag_path) as f:
            frag_source = f.read()

        return self._ctx.program(
            vertex_shader=vert_source,
            fragment_shader=frag_source,
        )

    def _create_shape_quad_vbo(self) -> moderngl.Buffer:
        """Create the static unit quad geometry for shape instances.

        No UVs are needed here, unlike the sprite quad -- the shape shader
        only needs the quad's local position to evaluate its SDF.
        """
        vertices = np.array(
            [-0.5, -0.5, 0.5, -0.5, -0.5, 0.5, 0.5, 0.5],
            dtype="f4",
        )
        return self._ctx.buffer(vertices.tobytes())

    def _create_shape_vao(self, instance_vbo: moderngl.Buffer) -> moderngl.VertexArray:
        """Create a VAO binding the shape quad and one shape-type's instances."""
        return self._ctx.vertex_array(
            self._shape_program,
            [
                (self._shape_quad_vbo, "2f", "in_vert"),
                (
                    instance_vbo,
                    "2f 2f 1f 4f 1f 1f/i",
                    "in_pos",
                    "in_size",
                    "in_rotation",
                    "in_color",
                    "in_width",
                    "in_shape_type",
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

        shape_uniform = self._shape_program["u_projection"]
        if hasattr(shape_uniform, "write"):
            shape_uniform.write(projection.tobytes())

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
        """Flush accumulated shape primitives.

        One instanced draw call per non-empty shape-type bucket
        (rect/circle/line), issued after all of a frame's draw_rect/
        draw_circle/draw_line calls -- see the ModernGL shape shader ticket.
        """
        for shape_type, pending in self._shape_pending.items():
            count = len(pending)
            if count == 0:
                continue

            if count > self._shape_capacities[shape_type]:
                self._grow_shape_buffer(shape_type, count)

            instance_data = np.array(pending, dtype="f4")
            self._shape_vbos[shape_type].write(instance_data.tobytes())
            self._shape_vaos[shape_type].render(
                moderngl.TRIANGLE_STRIP, instances=count
            )
            pending.clear()

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
        x = viewport.x
        y = self._height - viewport.y - viewport.height  # Flip Y
        w = viewport.width
        h = viewport.height
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

    def _get_font(self, size: int) -> pygame.font.Font:
        """Retrieve or create a font of the given size."""
        if size not in self._font_cache:
            self._font_cache[size] = pygame.font.SysFont("arial", size)
        return self._font_cache[size]

    def draw_text(
        self, text: str, position: Vector2, color: Color, size: int = 16
    ) -> None:
        """Draw a text string, in screen space (see `IRenderer.draw_text`).

        No persistent glyph atlas: this rasterizes the whole string on the
        CPU via `pygame.font` (as `UIRenderer`'s ModernGL implementation
        already does for UI text), uploads it as one ephemeral GL texture,
        draws it through the same single-instance path `draw_texture()`
        uses, then releases the texture immediately -- an ordinary
        `draw_texture()` call keeps its texture alive for reuse across
        frames, but a fresh piece of text has nothing to reuse anyway.
        Fine for occasional world-space text (damage numbers, prompts);
        a hot path drawing many strings a frame would want a real atlas.
        """
        if not text:
            return

        font = self._get_font(size)
        rgba = (color.r, color.g, color.b, color.a)
        surf = font.render(text, True, rgba)

        # Flipped on the way out: `GLTextureFactory.create_from_bytes()`
        # flips what it is given (for GL's bottom-left origin), so handing
        # it a surface in pygame's natural top-down order leaves the glyphs
        # upside down on screen. Every other upload path in this backend
        # pre-flips for the same reason -- see `loaders.py` and
        # `ui_renderer.py`. This path had simply never been run.
        data = pygame.image.tobytes(surf, "RGBA", True)
        gl_texture = self._texture_factory.create_from_bytes(
            "<draw_text>", data, surf.get_width(), surf.get_height()
        )
        try:
            # `draw_texture()` centres its quad on the position, but
            # `draw_text()` is anchored top-left -- that is what the pygame
            # backend does and what callers expect, so shift by half the
            # rendered size to match. Without this, text drawn near an edge
            # is half off-screen, and the two backends disagree about what
            # the same coordinates mean.
            centred = Vector2(
                position.x + surf.get_width() / 2.0,
                position.y + surf.get_height() / 2.0,
            )
            self.draw_texture(gl_texture, centred)
        finally:
            gl_texture.release()

    def render_batch(self, batch: RenderBatch) -> None:
        """Optimized method to draw many instances of the same texture.

        Uses hardware instancing to draw all sprites in a single GPU draw call.
        This is the high-performance path for rendering many sprites.

        Args:
            batch: Collection of sprite positions and transforms sharing one texture.
        """
        count = len(batch.destinations)
        if count == 0:
            return

        # Ensure buffer capacity
        if count > self._instance_capacity:
            self._grow_instance_buffer(count)

        # Pack into the reusable scratch array and upload the filled rows.
        # `.write()` takes the array view directly -- `tobytes()` would copy
        # the whole batch a second time for nothing.
        packed = instancing.pack_sprite_instances(batch, self._instance_scratch)
        self._instance_vbo.write(self._instance_scratch[:packed])

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

        # Grow the scratch array alongside it, so the pack keeps writing
        # into one array for the life of the renderer.
        self._instance_scratch = np.empty(
            (new_capacity, self.INSTANCE_FLOATS), dtype="f4"
        )

        # Recreate VAO with new instance buffer
        self._vao.release()
        self._vao = self._create_vao()

    def _grow_shape_buffer(self, shape_type: float, required_capacity: int) -> None:
        """Grow one shape-type bucket's instance buffer to fit more instances.

        Doubles the buffer size until it can hold the required capacity,
        mirroring `_grow_instance_buffer()` for the sprite path.
        """
        new_capacity = self._shape_capacities[shape_type]
        while new_capacity < required_capacity:
            new_capacity *= 2

        self._shape_vbos[shape_type].release()
        vbo = self._ctx.buffer(reserve=new_capacity * self.SHAPE_INSTANCE_STRIDE)
        self._shape_vbos[shape_type] = vbo
        self._shape_capacities[shape_type] = new_capacity

        self._shape_vaos[shape_type].release()
        self._shape_vaos[shape_type] = self._create_shape_vao(vbo)

    def draw_rect(self, rect: Rect, color: Color, width: int = 0) -> None:
        """Queue a rectangle primitive, flushed at end_frame().

        Args:
            rect: The rectangle bounds.
            color: The color to draw.
            width: Border thickness in pixels. 0 fills the rect.
        """
        half_w = rect.width / 2.0
        half_h = rect.height / 2.0
        pad = width / 2.0 if width > 0 else 0.0
        r, g, b, a = color.normalized

        self._shape_pending[self.SHAPE_TYPE_RECT].append(
            [
                rect.x + half_w,
                rect.y + half_h,
                half_w + pad,
                half_h + pad,
                0.0,
                r,
                g,
                b,
                a,
                float(width),
                self.SHAPE_TYPE_RECT,
            ]
        )

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Queue a circle primitive, flushed at end_frame().

        Args:
            center: Center position.
            radius: Radius in pixels.
            color: Color to draw.
            width: Border thickness in pixels. 0 fills the circle.
        """
        pad = width / 2.0 if width > 0 else 0.0
        r, g, b, a = color.normalized

        self._shape_pending[self.SHAPE_TYPE_CIRCLE].append(
            [
                center.x,
                center.y,
                radius + pad,
                radius + pad,
                0.0,
                r,
                g,
                b,
                a,
                float(width),
                self.SHAPE_TYPE_CIRCLE,
            ]
        )

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Queue a line primitive, flushed at end_frame().

        Lines are always drawn as filled capsules -- `width` sets the
        capsule's thickness rather than a stroke around some other shape.

        Args:
            start: Start point.
            end: End point.
            color: Line color.
            width: Line thickness in pixels.
        """
        dx = end.x - start.x
        dy = end.y - start.y
        length = math.hypot(dx, dy)
        half_length = length / 2.0
        half_width = max(width, 1) / 2.0
        angle = math.atan2(dy, dx)
        r, g, b, a = color.normalized

        self._shape_pending[self.SHAPE_TYPE_LINE].append(
            [
                (start.x + end.x) / 2.0,
                (start.y + end.y) / 2.0,
                half_length + half_width,
                half_width,
                angle,
                r,
                g,
                b,
                a,
                0.0,
                self.SHAPE_TYPE_LINE,
            ]
        )

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

        for vao in self._shape_vaos.values():
            vao.release()
        for vbo in self._shape_vbos.values():
            vbo.release()
        if self._shape_quad_vbo:
            self._shape_quad_vbo.release()
        if self._shape_program:
            self._shape_program.release()
