"""Tests for JSON-based UI theme system."""

import json
import tempfile
from pathlib import Path

import pytest

from pyguara.common.types import Color
from pyguara.ui.theme import UITheme, ThemeValidationError, get_theme, set_theme
from pyguara.ui.theme_presets import Themes
from pyguara.ui.types import (
    ColorScheme,
    SpacingScheme,
    FontScheme,
    BorderScheme,
    ShadowScheme,
)


class TestUIThemeBasics:
    """Test basic UITheme functionality."""

    def test_theme_creation(self):
        """UITheme should be created with default values."""
        theme = UITheme()

        assert theme.name == "default"
        assert isinstance(theme.colors, ColorScheme)
        assert isinstance(theme.spacing, SpacingScheme)
        assert isinstance(theme.fonts, FontScheme)
        assert isinstance(theme.borders, BorderScheme)
        assert isinstance(theme.shadows, ShadowScheme)

    def test_theme_with_custom_name(self):
        """UITheme can be created with custom name."""
        theme = UITheme(name="my_theme")

        assert theme.name == "my_theme"

    def test_theme_clone(self):
        """UITheme.clone() should create deep copy."""
        theme = UITheme(name="original")
        theme.colors.primary = Color(255, 0, 0)

        cloned = theme.clone()

        assert cloned.name == "original"
        assert cloned.colors.primary == Color(255, 0, 0)
        assert cloned is not theme
        assert cloned.colors is not theme.colors

        # Modify clone - should not affect original
        cloned.colors.primary = Color(0, 255, 0)
        assert theme.colors.primary == Color(255, 0, 0)


class TestThemeSchemes:
    """Test individual theme scheme components."""

    def test_color_scheme_defaults(self):
        """ColorScheme should have sensible defaults."""
        colors = ColorScheme()

        assert colors.primary == Color(70, 130, 180)
        assert colors.secondary == Color(100, 149, 237)
        assert colors.background == Color(32, 32, 32)
        assert colors.text == Color(255, 255, 255)
        assert colors.border == Color(96, 96, 96)

    def test_spacing_scheme_defaults(self):
        """SpacingScheme should have sensible defaults."""
        spacing = SpacingScheme()

        assert spacing.padding == 8
        assert spacing.margin == 4
        assert spacing.gap == 8

    def test_font_scheme_defaults(self):
        """FontScheme should have sensible defaults."""
        fonts = FontScheme()

        assert fonts.family == "Arial"
        assert fonts.size_small == 12
        assert fonts.size_normal == 16
        assert fonts.size_large == 24
        assert fonts.size_title == 32

    def test_border_scheme_defaults(self):
        """BorderScheme should have sensible defaults."""
        borders = BorderScheme()

        assert borders.width == 2
        assert borders.radius == 0
        assert borders.color == Color(96, 96, 96)

    def test_shadow_scheme_defaults(self):
        """ShadowScheme should have sensible defaults."""
        shadows = ShadowScheme()

        assert shadows.enabled is False
        assert shadows.offset_x == 2
        assert shadows.offset_y == 2
        assert shadows.blur == 4


class TestThemeJSONSerialization:
    """Test JSON serialization and deserialization."""

    def test_to_dict(self):
        """UITheme.to_dict() should convert to dictionary."""
        theme = UITheme(name="test_theme")
        theme.colors.primary = Color(255, 0, 0)

        data = theme.to_dict()

        assert data["name"] == "test_theme"
        assert "colors" in data
        assert "spacing" in data
        assert "fonts" in data
        assert "borders" in data
        assert "shadows" in data
        assert data["colors"]["primary"] == {"r": 255, "g": 0, "b": 0, "a": 255}

    def test_from_dict(self):
        """UITheme.from_dict() should create theme from dictionary."""
        data = {
            "name": "test_theme",
            "colors": {
                "primary": {"r": 255, "g": 0, "b": 0, "a": 255},
                "secondary": {"r": 0, "g": 255, "b": 0, "a": 255},
                "background": {"r": 32, "g": 32, "b": 32, "a": 255},
                "text": {"r": 255, "g": 255, "b": 255, "a": 255},
                "border": {"r": 96, "g": 96, "b": 96, "a": 255},
                "hover_overlay": {"r": 255, "g": 255, "b": 255, "a": 30},
                "press_overlay": {"r": 0, "g": 0, "b": 0, "a": 60},
            },
            "spacing": {"padding": 10, "margin": 5, "gap": 8},
            "fonts": {
                "family": "Helvetica",
                "size_small": 14,
                "size_normal": 18,
                "size_large": 26,
                "size_title": 34,
            },
            "borders": {
                "width": 3,
                "radius": 5,
                "color": {"r": 100, "g": 100, "b": 100, "a": 255},
            },
            "shadows": {
                "enabled": True,
                "offset_x": 4,
                "offset_y": 4,
                "blur": 8,
                "color": {"r": 0, "g": 0, "b": 0, "a": 200},
            },
        }

        theme = UITheme.from_dict(data)

        assert theme.name == "test_theme"
        assert theme.colors.primary == Color(255, 0, 0)
        assert theme.spacing.padding == 10
        assert theme.fonts.family == "Helvetica"
        assert theme.borders.width == 3
        assert theme.shadows.enabled is True

    def test_from_dict_partial(self):
        """UITheme.from_dict() should handle partial data with defaults."""
        data = {
            "name": "minimal_theme",
            "colors": {"primary": {"r": 255, "g": 0, "b": 0, "a": 255}},
        }

        theme = UITheme.from_dict(data)

        assert theme.name == "minimal_theme"
        assert theme.colors.primary == Color(255, 0, 0)
        # Other fields should use defaults
        assert theme.colors.secondary == Color(100, 149, 237)
        assert theme.spacing.padding == 8

    def test_from_dict_invalid(self):
        """UITheme.from_dict() should raise on invalid data."""
        data = {"name": "bad_theme", "colors": "not_a_dict"}

        with pytest.raises(ThemeValidationError):
            UITheme.from_dict(data)

    def test_to_json(self):
        """UITheme.to_json() should convert to JSON string."""
        theme = UITheme(name="test_theme")

        json_str = theme.to_json()

        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["name"] == "test_theme"

    def test_from_json(self):
        """UITheme.from_json() should create theme from JSON string."""
        json_str = """{
            "name": "json_theme",
            "colors": {
                "primary": {"r": 100, "g": 150, "b": 200, "a": 255},
                "secondary": {"r": 100, "g": 149, "b": 237, "a": 255},
                "background": {"r": 32, "g": 32, "b": 32, "a": 255},
                "text": {"r": 255, "g": 255, "b": 255, "a": 255},
                "border": {"r": 96, "g": 96, "b": 96, "a": 255},
                "hover_overlay": {"r": 255, "g": 255, "b": 255, "a": 30},
                "press_overlay": {"r": 0, "g": 0, "b": 0, "a": 60}
            },
            "spacing": {"padding": 8, "margin": 4, "gap": 8},
            "fonts": {
                "family": "Arial",
                "size_small": 12,
                "size_normal": 16,
                "size_large": 24,
                "size_title": 32
            },
            "borders": {
                "width": 2,
                "radius": 0,
                "color": {"r": 96, "g": 96, "b": 96, "a": 255}
            },
            "shadows": {
                "enabled": false,
                "offset_x": 2,
                "offset_y": 2,
                "blur": 4,
                "color": {"r": 0, "g": 0, "b": 0, "a": 128}
            }
        }"""

        theme = UITheme.from_json(json_str)

        assert theme.name == "json_theme"
        assert theme.colors.primary == Color(100, 150, 200)

    def test_from_json_invalid(self):
        """UITheme.from_json() should raise on invalid JSON."""
        json_str = "{invalid json"

        with pytest.raises(ThemeValidationError):
            UITheme.from_json(json_str)

    def test_roundtrip_serialization(self):
        """Theme should survive to_json -> from_json roundtrip."""
        original = UITheme(name="roundtrip")
        original.colors.primary = Color(123, 45, 67)
        original.spacing.padding = 15
        original.fonts.family = "Courier"
        original.borders.radius = 10
        original.shadows.enabled = True

        json_str = original.to_json()
        restored = UITheme.from_json(json_str)

        assert restored.name == original.name
        assert restored.colors.primary == original.colors.primary
        assert restored.spacing.padding == original.spacing.padding
        assert restored.fonts.family == original.fonts.family
        assert restored.borders.radius == original.borders.radius
        assert restored.shadows.enabled == original.shadows.enabled


class TestThemeFileIO:
    """Test loading and saving themes to files."""

    def test_save_to_file(self):
        """UITheme.save() should save theme to JSON file."""
        theme = UITheme(name="saved_theme")
        theme.colors.primary = Color(255, 100, 50)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "theme.json"

            theme.save(path)

            assert path.exists()
            with open(path, "r") as f:
                data = json.load(f)
                assert data["name"] == "saved_theme"

    def test_save_creates_parent_dirs(self):
        """UITheme.save() should create parent directories."""
        theme = UITheme(name="nested_theme")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subdir" / "nested" / "theme.json"

            theme.save(path)

            assert path.exists()

    def test_load_from_file(self):
        """UITheme.load() should load theme from JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "theme.json"

            # Create test file
            theme_data = {
                "name": "loaded_theme",
                "colors": {
                    "primary": {"r": 50, "g": 100, "b": 150, "a": 255},
                    "secondary": {"r": 100, "g": 149, "b": 237, "a": 255},
                    "background": {"r": 32, "g": 32, "b": 32, "a": 255},
                    "text": {"r": 255, "g": 255, "b": 255, "a": 255},
                    "border": {"r": 96, "g": 96, "b": 96, "a": 255},
                    "hover_overlay": {"r": 255, "g": 255, "b": 255, "a": 30},
                    "press_overlay": {"r": 0, "g": 0, "b": 0, "a": 60},
                },
                "spacing": {"padding": 8, "margin": 4, "gap": 8},
                "fonts": {
                    "family": "Arial",
                    "size_small": 12,
                    "size_normal": 16,
                    "size_large": 24,
                    "size_title": 32,
                },
                "borders": {
                    "width": 2,
                    "radius": 0,
                    "color": {"r": 96, "g": 96, "b": 96, "a": 255},
                },
                "shadows": {
                    "enabled": False,
                    "offset_x": 2,
                    "offset_y": 2,
                    "blur": 4,
                    "color": {"r": 0, "g": 0, "b": 0, "a": 128},
                },
            }

            with open(path, "w") as f:
                json.dump(theme_data, f)

            # Load theme
            theme = UITheme.load(path)

            assert theme.name == "loaded_theme"
            assert theme.colors.primary == Color(50, 100, 150)

    def test_load_file_not_found(self):
        """UITheme.load() should raise FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            UITheme.load("/nonexistent/path/theme.json")

    def test_roundtrip_file_io(self):
        """Theme should survive save -> load roundtrip."""
        original = UITheme(name="file_roundtrip")
        original.colors.primary = Color(111, 222, 333 % 256)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "theme.json"

            original.save(path)
            restored = UITheme.load(path)

            assert restored.name == original.name
            assert restored.colors.primary == original.colors.primary


class TestThemePresets:
    """Test pre-built theme presets."""

    def test_themes_exist(self):
        """Themes object should have all presets."""
        assert hasattr(Themes, "DARK")
        assert hasattr(Themes, "LIGHT")
        assert hasattr(Themes, "HIGH_CONTRAST")
        assert hasattr(Themes, "CYBERPUNK")
        assert hasattr(Themes, "FOREST")
        assert hasattr(Themes, "RETRO")

    def test_dark_theme(self):
        """Dark theme should have dark background."""
        assert Themes.DARK.name == "dark"
        assert Themes.DARK.colors.background.r < 50  # Dark

    def test_light_theme(self):
        """Light theme should have light background."""
        assert Themes.LIGHT.name == "light"
        assert Themes.LIGHT.colors.background.r > 200  # Light

    def test_high_contrast_theme(self):
        """High contrast theme should have black/white colors."""
        assert Themes.HIGH_CONTRAST.name == "high_contrast"
        assert Themes.HIGH_CONTRAST.colors.background == Color(0, 0, 0)
        assert Themes.HIGH_CONTRAST.colors.text == Color(255, 255, 255)

    def test_cyberpunk_theme(self):
        """Cyberpunk theme should have neon colors."""
        assert Themes.CYBERPUNK.name == "cyberpunk"
        # Magenta primary, cyan secondary
        assert Themes.CYBERPUNK.colors.primary.r == 255
        assert Themes.CYBERPUNK.colors.primary.b == 255

    def test_forest_theme(self):
        """Forest theme should have green colors."""
        assert Themes.FOREST.name == "forest"
        assert Themes.FOREST.colors.primary.g > Themes.FOREST.colors.primary.r

    def test_retro_theme(self):
        """Retro theme should have vintage styling."""
        assert Themes.RETRO.name == "retro"
        assert Themes.RETRO.fonts.family == "Courier New"

    def test_preset_cloning(self):
        """Presets can be cloned and customized."""
        custom = Themes.DARK.clone()
        custom.colors.primary = Color(255, 0, 0)

        # Original should be unchanged
        assert Themes.DARK.colors.primary != Color(255, 0, 0)
        # Custom should be modified
        assert custom.colors.primary == Color(255, 0, 0)


class TestThemeGlobalState:
    """Test global theme management."""

    def test_get_theme(self):
        """get_theme() should return current global theme."""
        theme = get_theme()

        assert isinstance(theme, UITheme)

    def test_set_theme(self):
        """set_theme() should update global theme."""
        original = get_theme()

        custom = UITheme(name="custom_global")
        set_theme(custom)

        assert get_theme().name == "custom_global"

        # Restore original
        set_theme(original)

    def test_theme_switching(self):
        """Can switch between preset themes."""
        original = get_theme()

        set_theme(Themes.DARK)
        assert get_theme().name == "dark"

        set_theme(Themes.LIGHT)
        assert get_theme().name == "light"

        # Restore
        set_theme(original)


class TestThemeUsagePatterns:
    """Test common usage patterns."""

    def test_basic_theme_usage(self):
        """Basic theme creation and usage."""
        theme = UITheme(name="my_game_theme")
        theme.colors.primary = Color(255, 0, 0)
        theme.fonts.family = "Comic Sans MS"

        assert theme.colors.primary == Color(255, 0, 0)
        assert theme.fonts.family == "Comic Sans MS"

    def test_preset_customization(self):
        """Customize preset theme."""
        theme = Themes.DARK.clone()
        theme.name = "dark_customized"
        theme.colors.primary = Color(255, 100, 0)

        assert theme.name == "dark_customized"
        assert theme.colors.primary == Color(255, 100, 0)
        # Other properties should remain from dark theme
        assert theme.colors.background == Themes.DARK.colors.background

    def test_theme_persistence(self):
        """Save and load custom theme."""
        theme = UITheme(name="persistent_theme")
        theme.colors.primary = Color(123, 234, 111)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "my_theme.json"

            # Save
            theme.save(path)

            # Later session - load
            loaded = UITheme.load(path)

            assert loaded.name == "persistent_theme"
            assert loaded.colors.primary == Color(123, 234, 111)
