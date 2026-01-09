"""
Core protocols for the Rendering system.

This module defines the essential contracts (interfaces) that decouple the
"What" (Renderable objects) from the "How" (The Renderer backend).

By adhering to these protocols:
1.  Game entities don't need to know if they are being drawn by Pygame or OpenGL.
2.  The Renderer doesn't need to know what an "Enemy" or "Player" is; it just
    knows it received something `Renderable`.
"""

from __future__ import annotations
from typing import Protocol, Any, Tuple, Optional, Iterable, runtime_checkable

from pyguara.common.types import Vector2, Color, Rect
from pyguara.resources.types import Texture
from pyguara.graphics.types import RenderBatch
from pyguara.config.types import WindowConfig


@runtime_checkable
class Renderable(Protocol):
    """
    An object that provides all necessary data to be drawn on screen.

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
        """
        The visual resource to be rendered.

        Returns:
            Texture: The loaded image/texture resource.
        """
        ...

    @property
    def position(self) -> Vector2:
        """
        The World Space position of the object.

        Returns:
            Vector2: The (x, y) coordinates where the center of the texture
            should be aligned (assuming centered origin).
        """
        ...

    @property
    def layer(self) -> int:
        """
        The sorting layer index.

        Lower numbers are drawn first (background). Higher numbers are drawn
        last (foreground/UI).

        Returns:
            int: The layer ID.
        """
        ...

    @property
    def z_index(self) -> float:
        """
        The Y-Sort key for depth sorting within the same layer.

        Usually corresponds to the `y` position of the entity's feet.
        Objects lower on the screen (higher Y) cover objects higher up.

        Returns:
            float: The sorting key.
        """
        ...

    # Optional properties can be handled via getattr or separate protocols,
    # but for a core Renderable, we might assume these exist with defaults:

    @property
    def rotation(self) -> float:
        """
        Rotation angle in degrees.

        Returns:
            float: Angle (0.0 to 360.0).
        """
        ...

    @property
    def scale(self) -> Vector2:
        """
        Scale factor.

        Returns:
            Vector2: (1.0, 1.0) for normal size.
        """
        ...


class IRenderer(Protocol):
    """
    The Hardware Abstraction Layer (HAL) for rendering.

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
        """
        Clear the entire screen/buffer with a specific color.

        Args:
            color (Color): The background color to fill.
        """
        ...

    def set_viewport(self, viewport: Rect) -> None:
        """
        Set the clipping region for subsequent draw calls.

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
        """
        Draw a texture at the given Screen Coordinate.

        Note:
            This method receives coordinates that have *already* been transformed
            by the Camera/Viewport system (World -> Screen conversion happens
            before calling this).

        Args:
            texture (Texture): The resource to draw.
            destination (Vector2): The top-left or center position on screen.
            rotation (float, optional): Rotation in degrees. Defaults to 0.0.
            scale (Vector2, optional): Scale factor. Defaults to (1, 1).
        """
        ...

    def draw_rect(self, rect: Rect, color: Color, width: int = 0) -> None:
        """
        Draw a simple primitive rectangle (useful for Debugging/UI).

        Args:
            rect (Rect): The rectangle bounds.
            color (Color): The color to draw.
            width (int, optional): Border thickness. 0 fills the rect.
        """
        ...

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """
        Draw a circle primitive.

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
        """
        Draw a line between two points.

        Args:
            start (Vector2): Start point.
            end (Vector2): End point.
            color (Color): Line color.
            width (int): Line thickness.
        """
        ...

    def present(self) -> None:
        """
        Swap the buffers and display the rendered frame to the user.

        This should be called exactly once at the end of the render loop.
        """
        ...

    def render_batch(self, batch: "RenderBatch") -> None:
        """Optimized method to draw many instances of the same texture."""
        ...


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

    def clear(self, color: Optional[Color] = None) -> None:
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
        """
        Poll system events (input, window events).

        Returns:
            Iterable of opaque event objects to be passed to InputManager.
        """
        ...

    def get_screen(self) -> Any:
        """Return the native OS window."""
        ...


class UIRenderer(Protocol):
    """Abstract interface for drawing UI elements."""

    def draw_rect(
        self, rect: Rect, color: Color, width: int = 0, border_radius: int = 0
    ) -> None:
        """Draw a filled or outlined rectangle."""
        ...

    def draw_circle(self, center: Vector2, radius: float, color: Color) -> None:
        """Draw a circle (e.g. for Radio buttons or Slider knobs)."""
        ...

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Draw a line."""
        ...

    def draw_text(
        self, text: str, position: Vector2, color: Color, size: int = 16
    ) -> None:
        """Draw text string."""
        ...

    def draw_texture(
        self, texture: Any, rect: Rect, color: Optional[Color] = None
    ) -> None:
        """Draw an image texture.

        Args:
            texture: The engine specific texture object (e.g. pygame.Surface)
            rect: Where to draw it
            color: Optional tint color
        """
        ...

    def get_text_size(self, text: str, size: int) -> Tuple[int, int]:
        """Calculate dimensions of text."""
