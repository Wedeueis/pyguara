"""The engine's default font: Liberation Sans 2.1.5, in four styles.

Bundled so text looks the same on every platform and both renderers. Before,
each renderer asked the system for "arial" and got Arial on Windows, Ubuntu
on Ubuntu, and whatever fontconfig preferred elsewhere -- the same HUD
measured differently per machine. Liberation Sans has Arial's metrics, so a
label laid out against Arial on Windows still fits.

SIL Open Font License 1.1 (`OFL.txt` beside the files), from
https://github.com/liberationfonts/liberation-fonts, release 2.1.5. The
native extension embeds these same files (`rust/src/text.rs`), so the two
cannot drift apart.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

FONTS = Path(__file__).resolve().parent

_STYLES = {
    (False, False): "LiberationSans-Regular.ttf",
    (True, False): "LiberationSans-Bold.ttf",
    (False, True): "LiberationSans-Italic.ttf",
    (True, True): "LiberationSans-BoldItalic.ttf",
}


def default_font_path(bold: bool = False, italic: bool = False) -> Path:
    """Return the default font file for a style.

    Args:
        bold: The bold face.
        italic: The italic face.

    Returns:
        The path to the `.ttf`.
    """
    return FONTS / _STYLES[(bold, italic)]


# -- Fallback faces ---------------------------------------------------------
#
# Liberation Sans covers Latin, Greek and Cyrillic. A character it lacks --
# Chinese, Japanese, Korean -- is drawn from the first fallback face that has
# it, by both renderers. Fallbacks are the game's to ship (a CJK face is tens
# of megabytes) and set here, engine-wide, in the order to try them. Han
# characters look different in Japanese and Chinese, so a game puts the face
# for the player's language first.

_fallbacks: tuple[Path, ...] = ()
_generation = 0
_native_faces: list[Any] | None = None
_warned_without_extension = False


def set_fallback_fonts(paths: Iterable[str | Path]) -> None:
    """Choose the faces a character the default face lacks is drawn from.

    Tried in order: the first with a glyph for a character draws it. Line
    height stays the default face's. Single-face files only (`.ttf` or
    `.otf`, not a `.ttc` collection), because the pygame renderer opens
    them by path. Replaces the previous list; an empty list clears it.

    Args:
        paths: The font files, in the order to try them.

    Raises:
        FileNotFoundError: If a file does not exist.
        OSError: If the native extension finds a file is not a font.
    """
    global _fallbacks, _generation, _native_faces
    chosen = tuple(Path(path) for path in paths)
    for path in chosen:
        if not path.is_file():
            raise FileNotFoundError(f"fallback font {path} does not exist")
    faces = _load_native(chosen)
    _fallbacks = chosen
    _native_faces = faces
    _generation += 1


def fallback_fonts() -> tuple[Path, ...]:
    """Return the fallback faces, in the order they are tried."""
    return _fallbacks


def fallback_generation() -> int:
    """Return a number that changes whenever the fallbacks do.

    Renderers compare it to the one their font cache was built under, and
    rebuild when it differs.
    """
    return _generation


def native_fallback_faces() -> list[Any]:
    """Return the fallbacks as `NativeFace`s, read once; none without the extension."""
    global _native_faces
    if _native_faces is None:
        _native_faces = _load_native(_fallbacks)
    return list(_native_faces)


def faces_for(text: str, bold: bool = False, italic: bool = False) -> list[int]:
    """For each character, which face draws it: 0 the default, then each fallback.

    A character no face has gets 0, the default face's missing-glyph box.
    Without the native extension, which reads the faces' character maps,
    every character gets 0 and a warning is logged once.
    """
    if not _fallbacks:
        return [0] * len(text)
    extension = _extension()
    if extension is None:
        _warn_without_extension()
        return [0] * len(text)
    coverage = [extension.NativeFace.default(bold, italic).covers(text)]
    coverage += [face.covers(text) for face in native_fallback_faces()]
    chosen = []
    for position in range(len(text)):
        chosen.append(
            next((i for i, covers in enumerate(coverage) if covers[position]), 0)
        )
    return chosen


def _extension() -> Any | None:
    # A backend's need, not a store's: `PYGUARA_NO_NATIVE` does not apply.
    from pyguara import native

    try:
        return native.require_extension("Fallback fonts")
    except RuntimeError:
        return None


def _load_native(paths: tuple[Path, ...]) -> list[Any]:
    extension = _extension()
    if extension is None:
        return []
    faces = []
    for path in paths:
        try:
            faces.append(extension.NativeFace(path.read_bytes()))
        except OSError as error:
            raise OSError(f"fallback font {path}: {error}") from error
    return faces


def _warn_without_extension() -> None:
    global _warned_without_extension
    if not _warned_without_extension:
        _warned_without_extension = True
        import logging

        logging.getLogger(__name__).warning(
            "Fallback fonts need the native extension to read their "
            "character maps; characters the default face lacks will show "
            "as boxes."
        )
