"""Pygame implementation of the UI Renderer."""

from typing import Any

import pygame

from pyguara.common.types import Color, Rect, Vector2


class PygameUIRenderer:
    """Concrete implementation of UIRenderer using Pygame.

    Handles primitive drawing, text rendering, and texture blitting.
    """

    def __init__(self, target_surface: pygame.Surface) -> None:
        """Initialize the renderer."""
        self._surface = target_surface
        self._font_cache: dict[int, pygame.font.Font] = {}

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

    def _to_pygame_color(self, color: Color) -> tuple[int, int, int, int]:
        """Convert engine Color to Pygame tuple."""
        return (color.r, color.g, color.b, getattr(color, "a", 255))

    def draw_rect(
        self, rect: Rect, color: Color, width: int = 0, border_radius: int = 0
    ) -> None:
        """Draw a filled or outlined rectangle.

        A translucent colour is blended through a scratch surface rather
        than drawn directly. `pygame.draw` *replaces* the destination pixel
        including its alpha, so a scrim drawn straight onto the display --
        which is opaque -- would land solid black instead of dimming the
        frame behind it. Blitting is what blends.
        """
        pygame_rect = pygame.Rect(rect.x, rect.y, rect.width, rect.height)
        rgba = self._to_pygame_color(color)

        if rgba[3] < 255 and rect.width > 0 and rect.height > 0:
            self._blit_blended(pygame_rect, rgba, width, border_radius)
            return

        pygame.draw.rect(
            self._surface, rgba, pygame_rect, width, border_radius=border_radius
        )

    def _blit_blended(
        self,
        pygame_rect: pygame.Rect,
        rgba: tuple[int, int, int, int],
        width: int,
        border_radius: int,
    ) -> None:
        """Draw `rgba` into a scratch surface and blit it, so alpha blends.

        Args:
            pygame_rect: Destination rectangle, in screen coordinates.
            rgba: The colour, with an alpha below 255.
            width: Outline width; 0 fills.
            border_radius: Corner radius.
        """
        scratch = pygame.Surface(pygame_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            scratch,
            rgba,
            pygame.Rect(0, 0, pygame_rect.width, pygame_rect.height),
            width,
            border_radius=border_radius,
        )
        self._surface.blit(scratch, pygame_rect.topleft)

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Draw a filled or outlined circle."""
        rgba = self._to_pygame_color(color)
        pygame.draw.circle(
            self._surface, rgba, (int(center.x), int(center.y)), int(radius), width
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

    def draw_polygon(
        self, points: list[tuple[int, int]], color: Color, width: int = 0
    ) -> None:
        """Draw a filled or outlined polygon."""
        rgba = self._to_pygame_color(color)
        pygame.draw.polygon(self._surface, rgba, points, width)

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
        self, texture: Any, rect: Rect, color: Color | None = None
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

    def get_text_size(self, text: str, size: int) -> tuple[int, int]:
        """Calculate the width/height of a string."""
        font = self._get_font(size)
        txt_size = font.size(text)
        return (txt_size[0], txt_size[1])

    def set_target(self, surface: pygame.Surface) -> None:
        """Switch render targets."""
        self._surface = surface

    def present(self) -> None:
        """Finalize UI rendering.

        No-op for pygame since it draws directly to the surface.
        """
        pass
