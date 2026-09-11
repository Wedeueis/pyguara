"""Pygame implementation of the Rendering Protocol."""

import pygame

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.backends.pygame.conversions import (
    to_pygame_color,
    to_pygame_rect,
)
from pyguara.graphics.types import RenderBatch
from pyguara.resources.types import Texture


class PygameBackend:
    """Renderer backend that uses the Pygame library."""

    def __init__(self, window_surface: pygame.Surface):
        """Initialize the backend with a target surface."""
        self._screen = window_surface
        self._font_cache: dict[int, pygame.font.Font] = {}
        if not pygame.font.get_init():
            pygame.font.init()

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
        self._screen.fill(to_pygame_color(color))

    def set_viewport(self, viewport: Rect) -> None:
        """Set the clipping region."""
        self._screen.set_clip(to_pygame_rect(viewport))

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

        Supports two modes:
        - Fast path: No transforms or tint, uses pygame.Surface.blits for
          C-level performance
        - Per-instance path: Rotation/scale and/or tint enabled, each
          sprite is transformed/tinted individually
        """
        texture = batch.texture.native_handle

        if not batch.transforms_enabled and not batch.colors_enabled:
            # FAST PATH: Simple blits without transforms or tint
            blit_sequence = ((texture, dest) for dest in batch.destinations)
            self._screen.blits(blit_sequence, doreturn=0)
            return

        for i, dest in enumerate(batch.destinations):
            surf = texture

            if batch.transforms_enabled:
                # Apply rotation if needed
                if i < len(batch.rotations) and batch.rotations[i] != 0.0:
                    surf = pygame.transform.rotate(surf, -batch.rotations[i])

                # Apply scale if needed
                if i < len(batch.scales):
                    scale_x, scale_y = batch.scales[i]
                    if scale_x != 1.0 or scale_y != 1.0:
                        new_width = int(surf.get_width() * scale_x)
                        new_height = int(surf.get_height() * scale_y)
                        surf = pygame.transform.scale(surf, (new_width, new_height))

            if batch.colors_enabled and i < len(batch.colors):
                rgba = batch.colors[i]
                if rgba != (255, 255, 255, 255):
                    # Copy first: `surf` may still be the cached original
                    # texture surface here (no transform ran above), and
                    # `.fill()` mutates in place -- tinting it directly
                    # would permanently discolor every future draw of this
                    # texture. Uses the full RGBA tuple, not RGB-only like
                    # ui_renderer.py's tint: a sprite/particle tint's alpha
                    # (e.g. a particle fading to alpha=0) is meant to fade
                    # the sprite out, where the UI helper's tint never did.
                    tinted = surf.copy()
                    tinted.fill(rgba, special_flags=pygame.BLEND_RGBA_MULT)
                    surf = tinted

            # Draw the transformed/tinted sprite
            self._screen.blit(surf, dest)

    def draw_rect(self, rect: Rect, color: Color, width: int = 0) -> None:
        """Draw a rectangle primitive."""
        pygame.draw.rect(
            self._screen, to_pygame_color(color), to_pygame_rect(rect), width
        )

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Draw a circle primitive."""
        pygame.draw.circle(
            self._screen,
            to_pygame_color(color),
            (int(center.x), int(center.y)),
            int(radius),
            width,
        )

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Draw a line primitive."""
        pygame.draw.line(
            self._screen,
            to_pygame_color(color),
            (start.x, start.y),
            (end.x, end.y),
            width,
        )

    def _get_font(self, size: int) -> pygame.font.Font:
        """Retrieve or create a font of the given size."""
        if size not in self._font_cache:
            self._font_cache[size] = pygame.font.SysFont("arial", size)
        return self._font_cache[size]

    def draw_text(
        self, text: str, position: Vector2, color: Color, size: int = 16
    ) -> None:
        """Draw a text string, in screen space (see `IRenderer.draw_text`)."""
        if not text:
            return
        font = self._get_font(size)
        surf = font.render(text, True, to_pygame_color(color))
        self._screen.blit(surf, (int(position.x), int(position.y)))

    def present(self) -> None:
        """Swap display buffers."""
        pygame.display.flip()
