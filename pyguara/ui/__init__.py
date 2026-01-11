"""Standard UI Components and Theming."""

from pyguara.ui.components.widget import Widget
from pyguara.ui.components.text import Label
from pyguara.ui.components.panel import Panel
from pyguara.ui.components.button import Button
from pyguara.ui.components.image import Image
from pyguara.ui.components.progress_bar import ProgressBar
from pyguara.ui.components.checkbox import Checkbox
from pyguara.ui.components.slider import Slider
from pyguara.ui.components.text_input import TextInput
from pyguara.ui.components.canvas import Canvas
from pyguara.ui.components.navbar import NavBar
from pyguara.ui.theme import UITheme, get_theme, set_theme, ThemeValidationError
from pyguara.ui.theme_presets import Themes
from pyguara.ui.types import (
    ColorScheme,
    SpacingScheme,
    FontScheme,
    BorderScheme,
    ShadowScheme,
)

__all__ = [
    # Components
    "Widget",
    "Label",
    "Panel",
    "Button",
    "Image",
    "ProgressBar",
    "Checkbox",
    "Slider",
    "TextInput",
    "Canvas",
    "NavBar",
    # Theme
    "UITheme",
    "get_theme",
    "set_theme",
    "ThemeValidationError",
    "Themes",
    # Theme Types
    "ColorScheme",
    "SpacingScheme",
    "FontScheme",
    "BorderScheme",
    "ShadowScheme",
]
