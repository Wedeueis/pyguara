"""Core protocols for the Rendering system.

This module defines the essential contracts (interfaces) that decouple the
"What" (Renderable objects) from the "How" (The Renderer backend).

By adhering to these protocols:
1.  Game entities don't need to know if they are being drawn by Pygame or OpenGL.
2.  The Renderer doesn't need to know what an "Enemy" or "Player" is; it just
    knows it received something `Renderable`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable

from pyguara.common.types import Color, Rect, Vector2
from pyguara.config.types import WindowConfig
from pyguara.graphics.types import RenderBatch, ShapeBatch
from pyguara.resources.font import Font
from pyguara.resources.types import Texture


@runtime_checkable
class Renderable(Protocol):
    """An object that provides all necessary data to be drawn on screen.

    Any class implementing this protocol (Game Entities, UI Widgets, Particles)
    can be submitted to the RenderPipeline. This effectively acts as the
    data source for a draw call.

    Note:
        In a pure ECS (Entity Component System), this might strictly be a
        'SpriteComponent'. However, defining it as a protocol allows flexibility
        for non-ECS objects (like debug cursors or simple UI) to be rendered
        through the same pipeline.
    """

    @property
    def texture(self) -> Texture:
        """The visual resource to be rendered.

        Returns:
            Texture: The loaded image/texture resource.
        """
        ...

    @property
    def position(self) -> Vector2:
        """The World Space position of the object.

        Returns:
            Vector2: The (x, y) coordinates where the center of the texture
            should be aligned (assuming centered origin).
        """
        ...

    @property
    def layer(self) -> int:
        """The sorting layer index.

        Lower numbers are drawn first (background). Higher numbers are drawn
        last (foreground/UI).

        Returns:
            int: The layer ID.
        """
        ...

    @property
    def z_index(self) -> float:
        """Manual depth key within the layer, used when `y_sort` is False.

        Set it by hand to decide what covers what among things that do not
        move -- a floor decal under a wall shadow. Anything that *does*
        move wants `y_sort` instead, since a hand-maintained z_index cannot
        track a character walking past a tree.

        Returns:
            float: The sorting key.
        """
        ...

    @property
    def y_sort(self) -> bool:
        """Whether world Y decides this object's depth instead of `z_index`.

        The 2.5D rule: objects lower on the screen (higher Y) cover objects
        higher up, so a character walking down past a tree ends up in front
        of it with nobody maintaining a number.

        Returns:
            bool: True to sort by Y.
        """
        ...

    @property
    def sort_offset(self) -> float:
        """Added to world Y before comparing, when `y_sort` is True.

        An object's depth is its contact point with the ground, not its
        centre: without this a tall tree whose centre sits above a short
        character's centre draws behind the character even while the
        character stands in front of its trunk. Usually half the height.

        Returns:
            float: The offset in world units.
        """
        ...

    @property
    def sort_group(self) -> int:
        """Coarse ordering within the layer, compared before depth.

        What a "sorting group" is for: a character and the sword they are
        holding must stay together relative to the scenery however their
        own depths compare, so both carry the group and sort as one unit.

        Returns:
            int: The group index; 0 for the default group.
        """
        ...

    # Optional properties can be handled via getattr or separate protocols,
    # but for a core Renderable, we might assume these exist with defaults:

    @property
    def rotation(self) -> float:
        """Rotation angle in degrees.

        Returns:
            float: Angle (0.0 to 360.0).
        """
        ...

    @property
    def scale(self) -> Vector2:
        """Scale factor.

        Returns:
            Vector2: (1.0, 1.0) for normal size.
        """
        ...

    @property
    def flip_x(self) -> bool:
        """Mirror the image left to right, inside the same box.

        Returns:
            bool: True to mirror.
        """
        ...

    @property
    def flip_y(self) -> bool:
        """Mirror the image top to bottom, inside the same box.

        Returns:
            bool: True to mirror.
        """
        ...

    @property
    def material(self) -> Any:
        """Optional material for custom rendering.

        When None (the default), the renderer uses the default sprite material.

        Returns:
            Material or None for default sprite rendering.
        """
        ...

    @property
    def color(self) -> Color:
        """Tint multiplied into the texture at draw time.

        `Color(255, 255, 255, 255)` (the default every implementer uses)
        draws the texture unmodified -- a backend only needs to touch its
        per-instance tint path once a batch contains something else.

        Returns:
            Color: The tint colour.
        """
        ...


@runtime_checkable
class ShapeRenderer(Protocol):
    """The primitives `IRenderer` and `UIRenderer` both draw.

    A rectangle, a circle and a line are drawn identically through either
    renderer, in the same screen-pixel coordinates. An art helper that
    uses only those takes this protocol, so one drawing serves the world
    and the HUD. Both renderers satisfy it structurally.
    """

    def draw_rect(self, rect: Rect, color: Color, width: int = 0) -> None:
        """Draw a filled or outlined rectangle."""
        ...

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Draw a filled or outlined circle."""
        ...

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Draw a line."""
        ...

    def draw_text(
        self,
        text: str,
        position: Vector2,
        color: Color,
        size: int = 16,
        *,
        font: Font | None = None,
    ) -> None:
        """Draw a text string, in `font` or the default face."""
        ...


@runtime_checkable
class PrimitiveArrayRenderer(Protocol):
    """A renderer that draws many rectangles, circles or lines in one call.

    A capability, tested for with `isinstance`. Each row draws exactly what
    the matching `draw_rect`, `draw_circle` or `draw_line` call would; the
    column orders are in `pyguara.graphics.primitives`, which also draws
    the same arrays one call at a time on a renderer without this.
    """

    def draw_rects(self, rows: Any) -> None:
        """Draw one rectangle per row of `x, y, w, h, r, g, b, a, outline`."""
        ...

    def draw_circles(self, rows: Any) -> None:
        """Draw one circle per row of `x, y, radius, outline, r, g, b, a`."""
        ...

    def draw_lines(self, rows: Any) -> None:
        """Draw one line per row of `x1, y1, x2, y2, width, r, g, b, a`."""
        ...


@runtime_checkable
class ShapeBatchRenderer(Protocol):
    """A renderer that can take many primitives of one kind in one call.

    A capability, not a requirement: a backend that can batch shapes
    satisfies it structurally, and a caller tests for it with
    `isinstance`. The wgpu world renderer has it; the software renderer
    does not, since it would only loop over the rows.

    Callers keep their per-primitive path and use this when it is offered;
    see `Sparks.render`.
    """

    def render_shapes(self, batch: ShapeBatch) -> None:
        """Draw every primitive in `batch`.

        Drawing order follows the per-kind grouping the backend already
        uses, exactly as a sequence of `draw_circle` calls would -- a batch
        is not a way to reorder a frame.

        Args:
            batch: Packed rows, all of one `ShapeKind`.
        """
        ...


@runtime_checkable
class IRenderer(Protocol):
    """The Hardware Abstraction Layer (HAL) for rendering.

    This protocol defines the low-level operations that a Backend
    (e.g., PygameBackend, HeadlessBackend) must implement. The `RenderSystem`
    uses this interface to execute commands, ensuring the system logic remains
    agnostic of the underlying graphics library.
    """

    @property
    def width(self) -> int:
        """Get the width of the rendering context in pixels."""
        ...

    @property
    def height(self) -> int:
        """Get the height of the rendering context in pixels."""
        ...

    def clear(self, color: Color) -> None:
        """Clear the entire screen/buffer with a specific color.

        Args:
            color (Color): The background color to fill.
        """
        ...

    def set_viewport(self, viewport: Rect) -> None:
        """Set the clipping region for subsequent draw calls.

        All draw operations after this call should be constrained to the
        specified rectangle. Used for split-screen, minimaps, or UI windows.

        Args:
            viewport (Rect): The clipping rectangle in screen coordinates.
        """
        ...

    def begin_frame(self) -> None:
        """Start the frame rendering by batch."""
        ...

    def end_frame(self) -> None:
        """Finish the frame rendering."""
        ...

    def reset_viewport(self) -> None:
        """Reset the viewport to cover the full window/screen."""
        ...

    def draw_texture(
        self,
        texture: Texture,
        destination: Vector2,
        rotation: float = 0.0,
        scale: Vector2 = Vector2(1, 1),
    ) -> None:
        """Draw a texture centred on the given Screen Coordinate.

        Centred, not top-left, so a rotation is about the texture's own
        middle. A caller that wants a top-left anchor shifts by half the
        texture.

        Note:
            This method receives coordinates that have *already* been transformed
            by the Camera/Viewport system (World -> Screen conversion happens
            before calling this).

        Args:
            texture (Texture): The resource to draw.
            destination (Vector2): The centre of the drawn texture.
            rotation (float, optional): Rotation in degrees, counter-clockwise.
                Defaults to 0.0.
            scale (Vector2, optional): Scale factor, multiplied into the
                texture's own size. A negative component flips that axis,
                which is how a sprite is mirrored. Defaults to (1, 1).
        """
        ...

    def draw_rect(self, rect: Rect, color: Color, width: int = 0) -> None:
        """Draw a simple primitive rectangle (useful for Debugging/UI).

        Args:
            rect (Rect): The rectangle bounds.
            color (Color): The color to draw.
            width (int, optional): Border thickness. 0 fills the rect.
        """
        ...

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Draw a circle primitive.

        Args:
            center (Vector2): Center position.
            radius (float): Radius in pixels.
            color (Color): Color to draw.
            width (int): Border thickness. 0 fills the circle.
        """
        ...

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Draw a line between two points.

        Args:
            start (Vector2): Start point.
            end (Vector2): End point.
            color (Color): Line color.
            width (int): Line thickness.
        """
        ...

    def draw_text(
        self,
        text: str,
        position: Vector2,
        color: Color,
        size: int = 16,
        *,
        font: Font | None = None,
    ) -> None:
        """Draw a text string, like the other primitives, in screen space.

        "World-space" text (a floating damage number, a "press E" prompt
        tracking an entity) is the caller's responsibility, exactly as it
        already is for `draw_rect`/`draw_circle`/`draw_line`: convert the
        world position through the camera to a screen position first (see
        `physics/debug_draw.py` for the established pattern), then call this
        with that screen position. This method itself has no camera
        knowledge.

        Args:
            text (str): The string to draw. A no-op for an empty string.
            position (Vector2): Top-left of the text, in screen space.
            color (Color): Text color.
            size (int): Font size in pixels.
            font (Font | None): A game's font, or None for the default face.
        """
        ...

    def resize(self, width: int, height: int) -> None:
        """Adopt a new drawing size.

        `width` and `height` are read-only, so before this there was no way
        to tell a renderer the window had changed -- and the ModernGL one
        builds its orthographic projection from them. A renderer left on
        the size it was constructed with maps the *original* pixel
        rectangle onto the new framebuffer, stretching the world by the
        ratio between the two aspect ratios: a circle came out an ellipse.

        Implementations whose size is read from something else -- a pygame
        surface is its own size -- have nothing to store, and say so.

        Args:
            width: The new width in pixels.
            height: The new height in pixels.
        """
        ...

    def present(self) -> None:
        """Swap the buffers and display the rendered frame to the user.

        This should be called exactly once at the end of the render loop.
        """
        ...

    def render_batch(self, batch: RenderBatch) -> None:
        """Optimized method to draw many instances of the same texture."""
        ...


@runtime_checkable
class IWindowChrome(Protocol):
    """Window-manager controls, for a window that draws its own title bar.

    Separate from `IWindowBackend` because it is genuinely optional: a
    backend that cannot offer these is usable, it simply cannot host a
    borderless editor. A caller tests with `isinstance` and falls back to
    the operating system's own title bar.
    """

    def minimize(self) -> None:
        """Iconify the window."""
        ...

    def maximize(self) -> None:
        """Fill the work area."""
        ...

    def restore(self) -> None:
        """Return to the size before maximising."""
        ...

    @property
    def is_maximized(self) -> bool:
        """Whether the window currently fills the work area."""
        ...

    def request_close(self) -> None:
        """Ask the application to shut down, as the OS close button does."""
        ...

    def begin_move(self) -> None:
        """Start a run of moves, such as a drag.

        Lets an implementation read the window's position once instead of
        once per frame. That read is not free, and worse, it is
        asynchronous: a window manager applies a move when it gets to it,
        so a position read straight after one may still be the old one.
        Adding a delta to that stale value puts the window somewhere
        nobody asked for, and the correction next frame is the small
        wobble a hand-rolled drag is known for.
        """
        ...

    def move_by(self, dx: int, dy: int) -> None:
        """Move the window by a screen-space delta.

        A delta rather than an absolute position: a window manager may
        place a window somewhere other than asked -- WSLg offsets by the
        decoration it would have drawn -- so reading back a position and
        setting an absolute one accumulates that error on every drag frame.
        """
        ...

    def end_move(self) -> None:
        """Finish a run of moves, dropping anything held for it."""
        ...


@runtime_checkable
class IWindowBackend(Protocol):
    """Interface for OS-specific window management systems.

    This protocol abstracts the lifecycle of the operating system window.
    """

    def open(self, config: WindowConfig) -> Any:
        """Create the native OS window."""
        ...

    def close(self) -> None:
        """Close and destroys the window context."""
        ...

    def clear(self, color: Color | None = None) -> None:
        """Clear the window context screen with default clear color."""
        ...

    def set_caption(self, title: str) -> None:
        """Update the window title."""
        ...

    def present(self) -> None:
        """Swap the video buffers (flips the screen).

        The Window owns the swap chain, so it should handle presentation.
        """
        ...

    def poll_events(self) -> Iterable[Any]:
        """Pump the OS event queue and return this frame's engine events.

        Returns:
            Engine events from `pyguara.events` -- `QuitEvent`, `KeyDownEvent`,
            `KeyUpEvent`, `MouseButtonEvent`, `MouseMotionEvent`,
            `WindowResizeEvent`. The backend owns the translation from its
            native events; nothing above this boundary reads a backend
            constant.
        """
        ...

    def post_event(self, event: object) -> None:
        """Deliver an engine event with the next `poll_events`.

        Synthetic input -- a capture tool's click, a test's key press --
        taking the same path as real input.
        """
        ...

    def get_screen(self) -> Any:
        """Return the native OS window."""
        ...

    @property
    def width(self) -> int:
        """The drawable surface width in pixels, as the OS actually granted it.

        Not the width that was requested: a fullscreen window is commonly
        handed the desktop resolution instead, and any resize changes it
        again.
        """
        ...

    @property
    def height(self) -> int:
        """The drawable surface height in pixels, as the OS actually granted it."""
        ...


@runtime_checkable
class UIRenderer(Protocol):
    """Abstract interface for drawing UI elements."""

    def draw_rect(
        self, rect: Rect, color: Color, width: int = 0, border_radius: int = 0
    ) -> None:
        """Draw a filled or outlined rectangle."""
        ...

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Draw a circle (e.g. for Radio buttons or Slider knobs).

        Args:
            center: Center position.
            radius: Radius in pixels.
            color: Circle color.
            width: Border thickness. 0 fills the circle (default).
        """
        ...

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Draw a line."""
        ...

    def draw_polygon(
        self, points: list[tuple[int, int]], color: Color, width: int = 0
    ) -> None:
        """Draw a polygon.

        Args:
            points: List of (x, y) coordinates defining the polygon vertices.
            color: Polygon color.
            width: Border thickness. 0 fills the polygon (default).
        """
        ...

    def draw_text(
        self,
        text: str,
        position: Vector2,
        color: Color,
        size: int = 16,
        *,
        bold: bool = False,
        italic: bool = False,
        font: Font | None = None,
    ) -> None:
        """Draw a text string, in `font` or the default face in a style.

        Args:
            text: The string to draw.
            position: Top-left of the text, in screen pixels.
            color: Text color.
            size: Pixels per em.
            bold: The default face's bold style. Not with `font`.
            italic: The default face's italic style. Not with `font`.
            font: A game's font, loaded through `ResourceManager`.

        Raises:
            ValueError: If `font` is given with `bold` or `italic`: a font
                is one face, and that style is its own file.
        """
        ...

    def draw_texture(
        self,
        texture: Any,
        rect: Rect,
        color: Color | None = None,
        source_rect: Rect | None = None,
    ) -> None:
        """Draw an image texture, or one region of it, scaled into `rect`.

        `source_rect` lets a widget draw one frame of an atlas. The region is
        cut before the scale, so a sub-rect scales as a standalone texture of
        that size would. A region the texture does not contain is clipped to
        the overlap, and the implementation logs it.

        Args:
            texture: A `resources.Texture`, as `ResourceManager.load` returns,
                or a backend surface. Anything else draws nothing and logs
                once.
            rect: Where to draw it
            color: Optional tint color
            source_rect: The region of `texture` to draw, in texture
                pixels. None draws all of it.
        """
        ...

    def get_text_size(
        self,
        text: str,
        size: int,
        *,
        bold: bool = False,
        italic: bool = False,
        font: Font | None = None,
    ) -> tuple[int, int]:
        """Calculate dimensions of text in a style or font, as `draw_text` takes them."""
        ...

    def get_line_height(self, size: int, *, font: Font | None = None) -> int:
        """Return the step between the baselines of consecutive lines.

        Not the same as `get_text_size`'s height, which is how tall one line
        is: this adds the leading the font itself asks for.

        Args:
            size: The font size.
            font: A game's font, or None for the default face.

        Returns:
            The line advance in pixels.
        """
        ...

    def push_clip(self, rect: Rect) -> None:
        """Restrict subsequent drawing to `rect`, in screen coordinates.

        Nesting intersects: a push inside an active clip narrows to the
        overlap of the two, so a scroll container can live inside another.
        An empty intersection clips everything away.

        Every push must be matched by a `pop_clip()`. A widget that draws
        between the two should do it in a `try`/`finally`, or an exception
        leaves the clip set for the rest of the frame.

        Args:
            rect: The region to clip to, in screen pixels.
        """
        ...

    def pop_clip(self) -> None:
        """Undo the most recent `push_clip()`.

        Restores the clip to whatever was in force before that push, which
        may be another clip or none at all. A pop with nothing pushed is a
        no-op rather than an error: a widget that pops in a `finally` should
        not turn one bug into two.
        """
        ...

    def resize(self, width: int, height: int) -> None:
        """Adopt a new drawing size.

        The GL implementation draws onto a surface it uploads whole and
        composites as a fullscreen quad, so a surface left at the original
        size is stretched across the resized window -- which is what left
        the HUD distorted. Implementations that draw straight onto the
        window's own surface have nothing to store.

        Args:
            width: The new width in pixels.
            height: The new height in pixels.
        """
        ...

    def present(self) -> None:
        """Finalize and present UI rendering.

        Called at the end of each frame after all UI drawing is complete.
        For immediate-mode renderers (pygame), this is a no-op.
        For deferred renderers (OpenGL), this composites the UI onto the framebuffer.
        """
        ...


@runtime_checkable
class TextureFactory(Protocol):
    """Factory for creating textures from raw image data.

    This protocol abstracts texture creation, allowing backend-agnostic
    code (like SpriteSheet) to create textures without knowing whether
    the underlying system uses Pygame surfaces or OpenGL textures.
    """

    def create_from_bytes(
        self, path: str, data: bytes, width: int, height: int
    ) -> Texture:
        """Create a texture from raw RGBA pixel data.

        Rows are top-down: 4 bytes per pixel, row-major, the image's top row
        first.

        Args:
            path: Identifier/name for the texture (used for caching/debugging).
            data: Raw RGBA pixel data, 4 bytes per pixel, top row first.
            width: Width of the image in pixels.
            height: Height of the image in pixels.

        Returns:
            A Texture instance appropriate for the current rendering backend.
        """
        ...


@runtime_checkable
class IFramebuffer(Protocol):
    """Interface for framebuffer objects (render targets).

    Framebuffers allow rendering to off-screen textures, enabling
    multi-pass rendering pipelines (lighting, post-processing, etc.).
    """

    @property
    def name(self) -> str:
        """Identifier for this framebuffer."""
        ...

    @property
    def width(self) -> int:
        """Width of the framebuffer in pixels."""
        ...

    @property
    def height(self) -> int:
        """Height of the framebuffer in pixels."""
        ...

    def bind(self) -> None:
        """Bind this framebuffer as the current render target."""
        ...

    def unbind(self) -> None:
        """Unbind this framebuffer, returning to the default target."""
        ...

    def clear(self, color: Color) -> None:
        """Clear the framebuffer with the specified color."""
        ...

    def resize(self, width: int, height: int) -> None:
        """Resize the framebuffer to new dimensions."""
        ...

    def release(self) -> None:
        """Release GPU resources associated with this framebuffer."""
        ...


@runtime_checkable
class IRenderPass(Protocol):
    """Interface for a single pass in the render pipeline.

    Render passes represent discrete stages of rendering (world, lighting,
    post-processing, UI). Each pass reads from input framebuffers and
    writes to output framebuffers.
    """

    @property
    def name(self) -> str:
        """Unique identifier for this pass."""
        ...

    @property
    def enabled(self) -> bool:
        """Whether this pass should execute."""
        ...

    def execute(self, graph: Any) -> None:
        """Execute this render pass.

        Args:
            graph: The RenderGraph orchestrating this pass: its buffers, and
                the device it runs shaders on.
        """
        ...
