"""A font file as a resource, which every renderer draws text in.

The resource is the file's bytes, checked to be a font when loaded. It
holds no backend object: each renderer builds its own at each size it is
asked for and caches it against this resource, so one `Font` works on
every renderer and none of them needs a factory.
"""

from __future__ import annotations

from typing import Any

from pyguara import assets, native
from pyguara.resources.types import Resource

FONT_EXTENSIONS = (".ttf", ".otf")


class Font(Resource):
    """One face of a typeface, loaded from a `.ttf` or `.otf`.

    One face in one style: a family's bold face is its own file, loaded as
    its own `Font`. Passing `bold=` or `italic=` with a font raises rather
    than faking the style, because the two renderers would fake it
    differently. Characters the face lacks are drawn from the engine's
    fallback faces (`pyguara.graphics.fonts.set_fallback_fonts`).

    Attributes:
        data: The file's contents.
        native_face: The face as the native extension reads it.
    """

    def __init__(self, path: str, data: bytes) -> None:
        """Wrap a font file's bytes.

        Args:
            path: Where it came from, used in errors.
            data: The contents of a single-face `.ttf` or `.otf`.

        Raises:
            OSError: If the bytes are not a font.
        """
        super().__init__(path)
        extension = native.require_extension("Fonts")
        try:
            self.native_face = extension.NativeFace(data)
        except OSError as error:
            raise OSError(f"font {path}: {error}") from error
        self.data = data

    @property
    def native_handle(self) -> Any:
        """The font itself: each renderer builds its own sizes from it."""
        return self

    @property
    def size_bytes(self) -> int:
        """The length of the file, which the font holds whole.

        Returns:
            Bytes.
        """
        return len(self.data)

    def __repr__(self) -> str:
        """Name the file, not the bytes."""
        return f"Font({self.path!r})"


class FontLoader:
    """Loads `.ttf` and `.otf` files as `Font`s."""

    @property
    def supported_extensions(self) -> list[str]:
        """The extensions this loader claims."""
        return list(FONT_EXTENSIONS)

    def load(self, path: str) -> Resource:
        """Read a font file.

        Args:
            path: The full path to the file.

        Returns:
            The font.

        Raises:
            FileNotFoundError: If the path does not exist.
            OSError: If the file is unreadable or not a font.
        """
        return Font(path, assets.read_bytes(path))


def check_style(font: Font | None, bold: bool, italic: bool) -> None:
    """Refuse a style asked of a font, which has only the face it was loaded from.

    Args:
        font: The font asked for, or None for the engine's default face.
        bold: Whether bold was asked for.
        italic: Whether italic was asked for.

    Raises:
        ValueError: If `font` is given with `bold` or `italic`.
    """
    if font is not None and (bold or italic):
        raise ValueError(
            f"{font.path} is one face and cannot be drawn bold or italic; "
            f"load that style's own file as a Font and pass it instead"
        )
