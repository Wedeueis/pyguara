"""
Headless graphics backend.

Used for server-side logic, unit tests, or CI/CD pipelines where no display
exists. Unlike the Pygame backend under `SDL_VIDEODRIVER=dummy`, none of these
classes ever touch `pygame.display` (or any other SDL video call), so they
carry no SDL video dependency at all. Hosts the full composition-root trio a
real backend needs -- `HeadlessWindowBackend` (`IWindowBackend`),
`HeadlessBackend` (`IRenderer`), `HeadlessUIRenderer` (`UIRenderer`), and
`HeadlessTextureFactory` (`TextureFactory`) -- in one module since each is a
handful of no-op lines.
"""

from collections.abc import Iterable
from typing import Any

from pyguara.common.types import Color, Rect, Vector2
from pyguara.config.types import WindowConfig
from pyguara.graphics.types import RenderBatch
from pyguara.log import get_logger
from pyguara.resources.types import Texture

logger = get_logger(__name__)


class HeadlessWindowBackend:
    """A window backend that never opens a real OS window."""

    def __init__(self) -> None:
        """Initialize the dummy window backend."""
        self._is_open = False

    def open(self, config: WindowConfig) -> bool:
        """Pretend to open a window; no real display is ever created."""
        self._is_open = True
        return True

    def close(self) -> None:
        """Mark the window closed."""
        self._is_open = False

    def clear(self, color: Color | None = None) -> None:
        """No-op: nothing to clear."""

    def set_caption(self, title: str) -> None:
        """No-op: no window chrome to caption."""

    def present(self) -> None:
        """No-op: nothing to flip."""

    def poll_events(self) -> Iterable[Any]:
        """Return no events; nothing generates them without a real window."""
        return []

    def get_screen(self) -> Any:
        """Return `None`: there is no native surface/handle."""
        return None


class HeadlessBackend:
    """A world renderer backend that discards all draw calls."""

    def __init__(self, width: int, height: int):
        """Initialize the dummy backend."""
        self._width = width
        self._height = height
        logger.debug("Initialized virtual display %dx%d", width, height)

    @property
    def width(self) -> int:
        """Get the width of the rendering context in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Get the height of the rendering context in pixels."""
        return self._height

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
        """No-op: nothing to prepare for a new frame."""
        ...

    def end_frame(self) -> None:
        """No-op: nothing to finalize."""
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


class HeadlessUIRenderer:
    """A UI renderer that discards all draw calls."""

    def draw_rect(
        self, rect: Rect, color: Color, width: int = 0, border_radius: int = 0
    ) -> None:
        """No-op: discard the draw call."""
        ...

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """No-op: discard the draw call."""
        ...

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """No-op: discard the draw call."""
        ...

    def draw_polygon(
        self, points: list[tuple[int, int]], color: Color, width: int = 0
    ) -> None:
        """No-op: discard the draw call."""
        ...

    def draw_text(
        self, text: str, position: Vector2, color: Color, size: int = 16
    ) -> None:
        """No-op: discard the draw call."""
        ...

    def draw_texture(
        self, texture: Any, rect: Rect, color: Color | None = None
    ) -> None:
        """No-op: discard the draw call."""
        ...

    def get_text_size(self, text: str, size: int) -> tuple[int, int]:
        """Return a zero size: no text is ever actually measured/rendered."""
        return (0, 0)

    def present(self) -> None:
        """No-op: nothing to present."""
        ...


class HeadlessTexture(Texture):
    """A texture that stores only its dimensions, no pixel data."""

    def __init__(self, path: str, width: int, height: int) -> None:
        """Initialize the dummy texture."""
        super().__init__(path)
        self._width = width
        self._height = height

    @property
    def native_handle(self) -> Any:
        """Return `None`: there is no backend-specific object."""
        return None

    @property
    def width(self) -> int:
        """Get the width of the texture in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Get the height of the texture in pixels."""
        return self._height


class HeadlessTextureFactory:
    """Factory that creates `HeadlessTexture` instances, discarding pixel data."""

    def create_from_bytes(
        self, path: str, data: bytes, width: int, height: int
    ) -> Texture:
        """Create a `HeadlessTexture` from raw RGBA pixel data.

        The pixel data itself is discarded; only the dimensions are kept.

        Args:
            path: Identifier/name for the texture.
            data: Raw RGBA pixel data (unused).
            width: Width of the image in pixels.
            height: Height of the image in pixels.

        Returns:
            A `HeadlessTexture` with no backing pixel data.
        """
        return HeadlessTexture(path, width, height)
