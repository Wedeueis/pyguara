"""Pygame implementation of the Rendering Protocol."""

import pygame
from pyguara.graphics.protocols import IRenderer
from pyguara.common.types import Vector2, Color, Rect
from pyguara.resources.types import Texture
from pyguara.graphics.types import RenderBatch


class PygameBackend(IRenderer):
    """Renderer backend that uses the Pygame library."""

    def __init__(self, window_surface: pygame.Surface):
        """Initialize the backend with a target surface."""
        self._screen = window_surface

    @property
    def width(self) -> int:
        """Get the width of the render target."""
        return int(self._screen.get_width())

    @property
    def height(self) -> int:
        """Get the height of the render target."""
        return int(self._screen.get_height())

    def begin_frame(self) -> None:
        """Prepare the backend for a new frame."""
        pass

    def end_frame(self) -> None:
        """Finalize the frame rendering."""
        pass

    def clear(self, color: Color) -> None:
        """Clear the entire screen with a color."""
        self._screen.fill(color)

    def set_viewport(self, viewport: Rect) -> None:
        """Set the clipping region."""
        self._screen.set_clip(viewport)

    def reset_viewport(self) -> None:
        """Reset the clip to None, allowing drawing on the entire window surface again."""
        self._screen.set_clip(None)

    def draw_texture(
        self,
        texture: Texture,
        position: Vector2,
        rotation: float = 0.0,
        scale: Vector2 = Vector2(1, 1),
    ) -> None:
        """Draw a single texture immediately (Unbatched)."""
        surf = texture.native_handle
        # Note: If you need rotation/scale here, you'd use pygame.transform
        # For raw speed, we assume pre-transformed or handle it elsewhere
        self._screen.blit(surf, (position.x, position.y))

    def render_batch(self, batch: RenderBatch) -> None:
        """Optimized method to draw many instances of the same texture.

        Uses pygame.Surface.blits for C-level looping performance.
        """
        texture = batch.texture.native_handle

        # Generator for blits
        blit_sequence = ((texture, dest) for dest in batch.destinations)

        self._screen.blits(blit_sequence, doreturn=0)

    def draw_rect(self, rect: Rect, color: Color, width: int = 0) -> None:
        """Draw a rectangle primitive."""
        pygame.draw.rect(self._screen, color, rect, width)

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Draw a circle primitive."""
        pygame.draw.circle(
            self._screen, color, (int(center.x), int(center.y)), int(radius), width
        )

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Draw a line primitive."""
        pygame.draw.line(self._screen, color, (start.x, start.y), (end.x, end.y), width)

    def present(self) -> None:
        """Swap display buffers."""
        pygame.display.flip()
