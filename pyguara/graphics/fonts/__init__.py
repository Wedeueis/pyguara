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

from pathlib import Path

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
