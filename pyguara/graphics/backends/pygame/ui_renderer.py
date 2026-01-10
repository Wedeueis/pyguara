"""Pygame implementation of the UI Renderer."""

from typing import Tuple, Dict, Optional, Any
import pygame

from pyguara.common.types import Rect, Color, Vector2
from pyguara.graphics.protocols import UIRenderer


class PygameUIRenderer(UIRenderer):
    """Concrete implementation of UIRenderer using Pygame.

    Handles primitive drawing, text rendering, and texture blitting.
    """

    def __init__(self, target_surface: pygame.Surface) -> None:
        """Initialize the renderer."""
        self._surface = target_surface
        self._font_cache: Dict[int, pygame.font.Font] = {}

        if not pygame.font.get_init():
            pygame.font.init()

    # ... (rest of the file remains the same, assuming other methods are correct)
    # The previous turn's implementation was largely correct except for D205
    # I will reprint the full file to be safe and ensure consistency.

    def _get_font(self, size: int) -> pygame.font.Font:
        """Retrieve or create a font of the specific size."""
        if size not in self._font_cache:
            self._font_cache[size] = pygame.font.SysFont("arial", size)
        return self._font_cache[size]

    def _to_pygame_color(self, color: Color) -> Tuple[int, int, int, int]:
        """Convert engine Color to Pygame tuple."""
        return (color.r, color.g, color.b, getattr(color, "a", 255))

    def draw_rect(
        self, rect: Rect, color: Color, width: int = 0, border_radius: int = 0
    ) -> None:
        """Draw a filled or outlined rectangle."""
        pygame_rect = pygame.Rect(rect.x, rect.y, rect.width, rect.height)
        rgba = self._to_pygame_color(color)

        pygame.draw.rect(
            self._surface, rgba, pygame_rect, width, border_radius=border_radius
        )

    def draw_circle(self, center: Vector2, radius: float, color: Color) -> None:
        """Draw a circle."""
        rgba = self._to_pygame_color(color)
        pygame.draw.circle(
            self._surface, rgba, (int(center.x), int(center.y)), int(radius)
        )

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Draw a line."""
        rgba = self._to_pygame_color(color)
        pygame.draw.line(
            self._surface,
            rgba,
            (int(start.x), int(start.y)),
            (int(end.x), int(end.y)),
            width,
        )

    def draw_text(
        self, text: str, position: Vector2, color: Color, size: int = 16
    ) -> None:
        """Render text to the screen."""
        if not text:
            return

        font = self._get_font(size)
        rgba = self._to_pygame_color(color)

        texture = font.render(text, True, rgba)

        self._surface.blit(texture, (int(position.x), int(position.y)))

    def draw_texture(
        self, texture: Any, rect: Rect, color: Optional[Color] = None
    ) -> None:
        """Draw an image texture."""
        if not isinstance(texture, pygame.Surface):
            return

        target_rect = pygame.Rect(rect.x, rect.y, rect.width, rect.height)

        if texture.get_width() != rect.width or texture.get_height() != rect.height:
            scaled_tex = pygame.transform.scale(
                texture, (int(rect.width), int(rect.height))
            )
        else:
            scaled_tex = texture

        if color:
            rgba = self._to_pygame_color(color)
            tinted_tex = scaled_tex.copy()
            tinted_tex.fill(rgba[0:3], special_flags=pygame.BLEND_RGBA_MULT)
            self._surface.blit(tinted_tex, target_rect)
        else:
            self._surface.blit(scaled_tex, target_rect)

    def get_text_size(self, text: str, size: int) -> Tuple[int, int]:
        """Calculate the width/height of a string."""
        font = self._get_font(size)
        txt_size = font.size(text)
        return (txt_size[0], txt_size[1])

    def set_target(self, surface: pygame.Surface) -> None:
        """Switch render targets."""
        self._surface = surface
