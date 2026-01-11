"""Theme management system with JSON support."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, Dict, Any
from copy import deepcopy
from dataclasses import asdict, fields

from pyguara.common.types import Color
from pyguara.ui.types import (
    ColorScheme,
    SpacingScheme,
    FontScheme,
    BorderScheme,
    ShadowScheme,
)


class ThemeValidationError(Exception):
    """Raised when theme data is invalid."""

    pass


class UITheme:
    """Central styling configuration with JSON serialization support.

    Attributes:
        name: Theme name for identification
        colors: Color scheme configuration
        spacing: Layout spacing configuration
        fonts: Font configuration
        borders: Border styling configuration
        shadows: Shadow effects configuration
    """

    def __init__(
        self,
        name: str = "default",
        colors: Optional[ColorScheme] = None,
        spacing: Optional[SpacingScheme] = None,
        fonts: Optional[FontScheme] = None,
        borders: Optional[BorderScheme] = None,
        shadows: Optional[ShadowScheme] = None,
    ) -> None:
        """Initialize the theme with optional overrides."""
        self.name = name
        self.colors = colors or ColorScheme()
        self.spacing = spacing or SpacingScheme()
        self.fonts = fonts or FontScheme()
        self.borders = borders or BorderScheme()
        self.shadows = shadows or ShadowScheme()

    def clone(self) -> UITheme:
        """Create a deep copy of the theme.

        Note: Color objects are copied manually since pygame.Color
        cannot be deepcopied.
        """

        def copy_color(color: Color) -> Color:
            """Manually copy a Color object."""
            return Color(color.r, color.g, color.b, color.a)

        def copy_scheme_with_colors(scheme: Any) -> Any:
            """Copy a scheme dataclass, manually copying Color fields."""
            kwargs = {}
            for field in fields(scheme):
                value = getattr(scheme, field.name)
                if isinstance(value, Color):
                    kwargs[field.name] = copy_color(value)
                else:
                    kwargs[field.name] = value
            return type(scheme)(**kwargs)

        return UITheme(
            name=self.name,
            colors=copy_scheme_with_colors(self.colors),
            spacing=deepcopy(self.spacing),
            fonts=deepcopy(self.fonts),
            borders=copy_scheme_with_colors(self.borders),
            shadows=copy_scheme_with_colors(self.shadows),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert theme to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the theme.
        """

        def color_to_dict(color: Color) -> Dict[str, int]:
            """Convert Color to dict."""
            return {"r": color.r, "g": color.g, "b": color.b, "a": color.a}

        def scheme_to_dict(scheme: Any) -> Dict[str, Any]:
            """Convert a scheme dataclass to dict, handling Color fields."""
            result = {}
            for field in fields(scheme):
                value = getattr(scheme, field.name)
                if isinstance(value, Color):
                    result[field.name] = color_to_dict(value)
                else:
                    result[field.name] = value
            return result

        return {
            "name": self.name,
            "colors": scheme_to_dict(self.colors),
            "spacing": asdict(self.spacing),
            "fonts": asdict(self.fonts),
            "borders": scheme_to_dict(self.borders),
            "shadows": scheme_to_dict(self.shadows),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> UITheme:
        """Create theme from dictionary.

        Args:
            data: Theme configuration dictionary.

        Returns:
            UITheme instance.

        Raises:
            ThemeValidationError: If data is invalid.
        """
        if not isinstance(data, dict):
            raise ThemeValidationError("Theme data must be a dictionary")

        def dict_to_color(color_dict: Dict[str, int]) -> Color:
            """Convert dict to Color."""
            if not isinstance(color_dict, dict):
                raise ThemeValidationError("Color data must be a dictionary")
            return Color(
                color_dict.get("r", 0),
                color_dict.get("g", 0),
                color_dict.get("b", 0),
                color_dict.get("a", 255),
            )

        def dict_to_scheme(scheme_class: type, scheme_dict: Dict[str, Any]) -> Any:
            """Convert dict to scheme dataclass, handling Color fields."""
            if not isinstance(scheme_dict, dict):
                raise ThemeValidationError(
                    f"Scheme data for {scheme_class.__name__} must be a dictionary"
                )

            kwargs = {}
            for field in fields(scheme_class):
                if field.name in scheme_dict:
                    value = scheme_dict[field.name]
                    if field.type == Color or "Color" in str(field.type):
                        kwargs[field.name] = dict_to_color(value)
                    else:
                        kwargs[field.name] = value
            return scheme_class(**kwargs)

        try:
            return cls(
                name=data.get("name", "unnamed"),
                colors=dict_to_scheme(ColorScheme, data.get("colors", {})),
                spacing=SpacingScheme(**data.get("spacing", {})),
                fonts=FontScheme(**data.get("fonts", {})),
                borders=dict_to_scheme(BorderScheme, data.get("borders", {})),
                shadows=dict_to_scheme(ShadowScheme, data.get("shadows", {})),
            )
        except (TypeError, KeyError) as e:
            raise ThemeValidationError(f"Invalid theme data: {e}") from e

    def to_json(self, indent: int = 2) -> str:
        """Convert theme to JSON string.

        Args:
            indent: JSON indentation level.

        Returns:
            JSON string representation.
        """
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> UITheme:
        """Create theme from JSON string.

        Args:
            json_str: JSON string containing theme data.

        Returns:
            UITheme instance.

        Raises:
            ThemeValidationError: If JSON is invalid.
        """
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except json.JSONDecodeError as e:
            raise ThemeValidationError(f"Invalid JSON: {e}") from e

    def save(self, path: Path | str) -> None:
        """Save theme to JSON file.

        Args:
            path: File path to save to.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: Path | str) -> UITheme:
        """Load theme from JSON file.

        Args:
            path: File path to load from.

        Returns:
            UITheme instance.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ThemeValidationError: If file content is invalid.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Theme file not found: {path}")

        with open(path, "r") as f:
            return cls.from_json(f.read())


# Global default (can be swapped at runtime)
_current_theme = UITheme()


def get_theme() -> UITheme:
    """Retrieve the current active theme."""
    return _current_theme


def set_theme(theme: UITheme) -> None:
    """Set the active theme globally."""
    global _current_theme
    _current_theme = theme
