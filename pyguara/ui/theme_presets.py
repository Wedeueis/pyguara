"""Pre-built UI theme presets.

This module provides ready-to-use theme configurations for common use cases.
All themes can be customized by cloning and modifying specific properties.

Example:
    >>> from pyguara.ui.theme_presets import Themes
    >>> from pyguara.ui.theme import set_theme
    >>>
    >>> # Use dark theme
    >>> set_theme(Themes.DARK)
    >>>
    >>> # Customize a preset
    >>> my_theme = Themes.LIGHT.clone()
    >>> my_theme.colors.primary = Color(255, 0, 0)
    >>> set_theme(my_theme)
"""

from dataclasses import dataclass

from pyguara.common.types import Color
from pyguara.ui.theme import UITheme
from pyguara.ui.types import (
    ColorScheme,
    SpacingScheme,
    FontScheme,
    BorderScheme,
    ShadowScheme,
)


def _create_dark_theme() -> UITheme:
    """Create dark theme preset."""
    return UITheme(
        name="dark",
        colors=ColorScheme(
            primary=Color(70, 130, 180),  # Steel blue
            secondary=Color(100, 149, 237),  # Cornflower blue
            background=Color(32, 32, 32),  # Dark gray
            text=Color(255, 255, 255),  # White
            border=Color(96, 96, 96),  # Medium gray
            hover_overlay=Color(255, 255, 255, 30),
            press_overlay=Color(0, 0, 0, 60),
        ),
        spacing=SpacingScheme(padding=8, margin=4, gap=8),
        fonts=FontScheme(
            family="Arial", size_small=12, size_normal=16, size_large=24, size_title=32
        ),
        borders=BorderScheme(width=2, radius=0, color=Color(96, 96, 96)),
        shadows=ShadowScheme(
            enabled=True,
            offset_x=2,
            offset_y=2,
            blur=4,
            color=Color(0, 0, 0, 128),
        ),
    )


def _create_light_theme() -> UITheme:
    """Create light theme preset."""
    return UITheme(
        name="light",
        colors=ColorScheme(
            primary=Color(41, 128, 185),  # Peter River blue
            secondary=Color(52, 152, 219),  # Bright blue
            background=Color(236, 240, 241),  # Light gray
            text=Color(44, 62, 80),  # Dark blue-gray
            border=Color(189, 195, 199),  # Silver
            hover_overlay=Color(0, 0, 0, 20),
            press_overlay=Color(0, 0, 0, 40),
        ),
        spacing=SpacingScheme(padding=8, margin=4, gap=8),
        fonts=FontScheme(
            family="Arial", size_small=12, size_normal=16, size_large=24, size_title=32
        ),
        borders=BorderScheme(width=1, radius=4, color=Color(189, 195, 199)),
        shadows=ShadowScheme(
            enabled=True,
            offset_x=1,
            offset_y=1,
            blur=3,
            color=Color(0, 0, 0, 50),
        ),
    )


def _create_high_contrast_theme() -> UITheme:
    """Create high contrast theme for accessibility."""
    return UITheme(
        name="high_contrast",
        colors=ColorScheme(
            primary=Color(255, 255, 255),  # White
            secondary=Color(255, 255, 0),  # Yellow
            background=Color(0, 0, 0),  # Black
            text=Color(255, 255, 255),  # White
            border=Color(255, 255, 255),  # White
            hover_overlay=Color(255, 255, 0, 80),
            press_overlay=Color(255, 255, 255, 100),
        ),
        spacing=SpacingScheme(padding=12, margin=8, gap=12),
        fonts=FontScheme(
            family="Arial", size_small=14, size_normal=18, size_large=28, size_title=36
        ),
        borders=BorderScheme(width=3, radius=0, color=Color(255, 255, 255)),
        shadows=ShadowScheme(enabled=False),
    )


def _create_cyberpunk_theme() -> UITheme:
    """Create cyberpunk/neon theme."""
    return UITheme(
        name="cyberpunk",
        colors=ColorScheme(
            primary=Color(255, 0, 255),  # Magenta
            secondary=Color(0, 255, 255),  # Cyan
            background=Color(10, 10, 20),  # Very dark blue-black
            text=Color(0, 255, 255),  # Cyan
            border=Color(255, 0, 255),  # Magenta
            hover_overlay=Color(255, 0, 255, 60),
            press_overlay=Color(0, 255, 255, 80),
        ),
        spacing=SpacingScheme(padding=10, margin=6, gap=10),
        fonts=FontScheme(
            family="Courier New",
            size_small=12,
            size_normal=16,
            size_large=24,
            size_title=32,
        ),
        borders=BorderScheme(width=2, radius=0, color=Color(255, 0, 255)),
        shadows=ShadowScheme(
            enabled=True,
            offset_x=0,
            offset_y=0,
            blur=8,
            color=Color(255, 0, 255, 200),
        ),
    )


def _create_forest_theme() -> UITheme:
    """Create nature/forest theme."""
    return UITheme(
        name="forest",
        colors=ColorScheme(
            primary=Color(46, 125, 50),  # Green
            secondary=Color(76, 175, 80),  # Light green
            background=Color(33, 43, 33),  # Dark green-gray
            text=Color(232, 245, 233),  # Very light green
            border=Color(102, 187, 106),  # Medium green
            hover_overlay=Color(139, 195, 74, 50),
            press_overlay=Color(27, 94, 32, 80),
        ),
        spacing=SpacingScheme(padding=10, margin=5, gap=10),
        fonts=FontScheme(
            family="Arial", size_small=12, size_normal=16, size_large=24, size_title=32
        ),
        borders=BorderScheme(width=2, radius=8, color=Color(102, 187, 106)),
        shadows=ShadowScheme(
            enabled=True,
            offset_x=2,
            offset_y=2,
            blur=6,
            color=Color(0, 0, 0, 100),
        ),
    )


def _create_retro_theme() -> UITheme:
    """Create retro/vintage theme."""
    return UITheme(
        name="retro",
        colors=ColorScheme(
            primary=Color(255, 152, 0),  # Orange
            secondary=Color(255, 193, 7),  # Amber
            background=Color(66, 66, 66),  # Dark gray
            text=Color(255, 235, 205),  # Blanched almond
            border=Color(158, 158, 158),  # Gray
            hover_overlay=Color(255, 193, 7, 60),
            press_overlay=Color(255, 87, 34, 80),
        ),
        spacing=SpacingScheme(padding=12, margin=6, gap=12),
        fonts=FontScheme(
            family="Courier New",
            size_small=12,
            size_normal=16,
            size_large=24,
            size_title=32,
        ),
        borders=BorderScheme(width=3, radius=0, color=Color(158, 158, 158)),
        shadows=ShadowScheme(
            enabled=True,
            offset_x=4,
            offset_y=4,
            blur=0,
            color=Color(0, 0, 0, 150),
        ),
    )


@dataclass(frozen=True)
class ThemeConstants:
    """Container for pre-built theme presets.

    All themes are immutable. To customize, clone and modify:
        >>> my_theme = Themes.DARK.clone()
        >>> my_theme.colors.primary = Color(255, 0, 0)
    """

    DARK = _create_dark_theme()
    LIGHT = _create_light_theme()
    HIGH_CONTRAST = _create_high_contrast_theme()
    CYBERPUNK = _create_cyberpunk_theme()
    FOREST = _create_forest_theme()
    RETRO = _create_retro_theme()


# Singleton instance
Themes = ThemeConstants()
