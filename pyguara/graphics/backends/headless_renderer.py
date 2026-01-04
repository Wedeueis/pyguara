"""
Headless rendering backend.

Used for server-side logic, unit tests, or CI/CD pipelines where no display exists.
"""

from pyguara.graphics.protocols import IRenderer
from pyguara.graphics.types import RenderBatch
from pyguara.resources.types import Texture
from pyguara.common.types import Vector2, Color, Rect


class HeadlessBackend(IRenderer):
    """A backend that discards all draw calls."""

    def __init__(self, width: int, height: int):
        """Initialize the dummy backend."""
        self._width = width
        self._height = height
        print(f"[HeadlessBackend] Initialized virtual display {width}x{height}")

    @property
    def width(self) -> int:
        """Get the width of the rendering context in pixels."""
        return 800

    @property
    def height(self) -> int:
        """Get the height of the rendering context in pixels."""
        return 600

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
