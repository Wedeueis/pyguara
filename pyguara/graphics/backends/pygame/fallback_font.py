"""A pygame font that draws characters its face lacks from fallback faces.

SDL_ttf opens one file and draws a box for any character it lacks, and
pygame does not say which those are. So the text is split into runs by the
face that has each character -- the native extension reads the character
maps, the same answer the wgpu renderer uses -- each run is rendered with
its own `pygame.font.Font`, and the runs are set side by side on the
first face's baseline.

With no fallbacks set, every call goes straight to the first face, so
text that needs none renders exactly as before.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import pygame

from pyguara.graphics import fonts
from pyguara.graphics.fonts import default_font_path

if TYPE_CHECKING:
    from pyguara.resources.font import Font

__all__ = ["FallbackFont"]

Rgb = tuple[int, int, int] | tuple[int, int, int, int] | pygame.Color


class FallbackFont:
    """A face at a size and style, with the engine's fallbacks.

    The face is a game's `Font`, or the default face in the style asked
    for. Answers the parts of `pygame.font.Font` the renderers use:
    `render`, `size`, `get_height`, `get_linesize`, `get_ascent` and
    `get_descent`. Metrics are that face's.
    """

    def __init__(
        self,
        size: int,
        bold: bool = False,
        italic: bool = False,
        face: Font | None = None,
    ) -> None:
        """Open a face for a size and style.

        Args:
            size: Pixels per em.
            bold: The bold face. Not with `face`.
            italic: The italic face. Not with `face`.
            face: A game's font, in place of the default face.

        Raises:
            ValueError: If `face` is given with `bold` or `italic`.
        """
        from pyguara.resources.font import check_style

        check_style(face, bold, italic)
        self._size, self._bold, self._italic = size, bold, italic
        self._face = face
        self.primary = (
            pygame.font.Font(default_font_path(bold, italic), size)
            if face is None
            else pygame.font.Font(io.BytesIO(face.data), size)
        )
        self._generation = -1
        self._fallbacks: list[pygame.font.Font] = []

    def _faces(self) -> list[pygame.font.Font]:
        generation = fonts.fallback_generation()
        if generation != self._generation:
            self._generation = generation
            self._fallbacks = []
            for path in fonts.fallback_fonts():
                # From the bytes, not the path: the face may be in a pack.
                font = pygame.font.Font(
                    io.BytesIO(fonts.fallback_font_data(path)), self._size
                )
                # The fallback has one style; pygame synthesises the rest.
                font.bold, font.italic = self._bold, self._italic
                self._fallbacks.append(font)
        return [self.primary, *self._fallbacks]

    def runs(self, text: str) -> list[tuple[pygame.font.Font, str]]:
        """Split `text` into consecutive runs drawn by one face each."""
        faces = self._faces()
        if len(faces) == 1 or not text:
            return [(self.primary, text)]
        runs: list[tuple[pygame.font.Font, str]] = []
        current, start = -1, 0
        for position, face in enumerate(
            fonts.faces_for(
                text,
                self._bold,
                self._italic,
                None if self._face is None else self._face.native_face,
            )
        ):
            if face != current:
                if current >= 0:
                    runs.append((faces[current], text[start:position]))
                current, start = face, position
        runs.append((faces[current], text[start:]))
        return runs

    def size(self, text: str) -> tuple[int, int]:
        """Measure `text`, as `pygame.font.Font.size` does."""
        runs = self.runs(text)
        if len(runs) == 1 and runs[0][0] is self.primary:
            return self.primary.size(text)
        width = sum(font.size(run)[0] for font, run in runs)
        return width, self.primary.get_height()

    def render(
        self, text: str, antialias: bool, color: Rgb, background: Rgb | None = None
    ) -> pygame.Surface:
        """Render `text`, as `pygame.font.Font.render`."""
        runs = self.runs(text)
        if len(runs) == 1 and runs[0][0] is self.primary:
            return self.primary.render(text, antialias, color, background)
        width, height = self.size(text)
        surface = pygame.Surface((max(width, 1), height), pygame.SRCALPHA)
        if background is not None:
            surface.fill(background)
        x = 0
        ascent = self.primary.get_ascent()
        for font, run in runs:
            drawn = font.render(run, antialias, color)
            surface.blit(drawn, (x, ascent - font.get_ascent()))
            x += font.size(run)[0]
        return surface

    def get_height(self) -> int:
        """Return the face's height."""
        return self.primary.get_height()

    def get_linesize(self) -> int:
        """Return the face's line advance."""
        return self.primary.get_linesize()

    def get_ascent(self) -> int:
        """Return the face's ascent."""
        return self.primary.get_ascent()

    def get_descent(self) -> int:
        """Return the face's descent."""
        return self.primary.get_descent()

    def __getattr__(self, name: str) -> Any:
        """Anything else is the face's."""
        return getattr(self.primary, name)
