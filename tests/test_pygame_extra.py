"""pygame is an extra: what runs without it, and what says it is missing.

`sys.modules["pygame"] = None` makes every `import pygame` raise, which
is what an install without the extra looks like from the inside.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pyguara.application.bootstrap import (
    create_application,
    create_headless_application,
)
from pyguara.cli.build import _build_pyinstaller_args
from pyguara.common.extras import MissingExtraError, require_pygame
from pyguara.config.types import AudioBackend, GameConfig, RenderingBackend
from pyguara.input.backends.null_backend import NullInputBackend
from pyguara.input.protocols import IInputBackend


@pytest.fixture
def no_pygame(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Make pygame unimportable, in a directory the engine may write to."""
    monkeypatch.setitem(sys.modules, "pygame", None)
    monkeypatch.chdir(tmp_path)


class TestRequirePygame:
    """The check a pygame backend makes before importing it."""

    def test_it_passes_where_pygame_is_installed(self) -> None:
        require_pygame("this test")

    def test_it_names_the_feature_and_the_install(self, no_pygame: None) -> None:
        with pytest.raises(MissingExtraError) as raised:
            require_pygame('display.backend = "pygame"')
        message = str(raised.value)
        assert message.startswith('display.backend = "pygame" needs pygame')
        assert "pip install 'pyguara[pygame]'" in message

    def test_the_error_is_an_import_error(self) -> None:
        """So code that already catches a missing library still does."""
        assert issubclass(MissingExtraError, ImportError)


class TestBootstrapWithoutPygame:
    """Choosing a pygame backend without pygame stops at startup."""

    def test_the_software_renderer_is_refused_by_name(self, no_pygame: None) -> None:
        def configure(config: GameConfig) -> None:
            config.display.backend = RenderingBackend.PYGAME

        with pytest.raises(MissingExtraError, match="display.backend"):
            create_application(configure=configure)

    def test_the_headless_application_needs_no_pygame(self, no_pygame: None) -> None:
        app = create_headless_application()
        try:
            backend = app.container.get(IInputBackend)  # type: ignore[type-abstract]
            assert isinstance(backend, NullInputBackend)
        finally:
            app.shutdown()

    def test_pygame_audio_is_refused_by_name(
        self, no_pygame: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PYGUARA_AUDIO_BACKEND", "pygame")
        with pytest.raises(MissingExtraError, match="audio.backend"):
            create_headless_application()

    def test_the_default_audio_backend_is_not_pygame(self) -> None:
        assert GameConfig().audio.backend is AudioBackend.NATIVE


class TestNullInputBackend:
    """The headless application's input backend."""

    def test_it_satisfies_the_protocol(self) -> None:
        assert isinstance(NullInputBackend(), IInputBackend)

    def test_it_tracks_initialisation(self) -> None:
        backend = NullInputBackend()
        assert backend.is_initialized() is False
        backend.init_joysticks()
        assert backend.is_initialized() is True
        backend.quit_joysticks()
        assert backend.is_initialized() is False

    def test_it_has_no_devices(self) -> None:
        backend = NullInputBackend()
        assert backend.get_joystick_count() == 0
        with pytest.raises(IndexError):
            backend.get_joystick(0)


class TestBuildHiddenImports:
    """A frozen game names pygame only when its environment has it."""

    def _hidden(self, tmp_path: Path) -> list[str]:
        args = _build_pyinstaller_args(
            entry_point=tmp_path / "main.py",
            output_dir=tmp_path / "dist",
            name="game",
            onefile=False,
            windowed=False,
            icon=None,
            assets_dirs=[],
            extra_data=[],
            hidden_imports=[],
            clean=False,
            debug=False,
        )
        return [args[i + 1] for i, arg in enumerate(args) if arg == "--hidden-import"]

    def test_pygame_is_named_when_installed(self, tmp_path: Path) -> None:
        assert "pygame" in self._hidden(tmp_path)

    def test_pygame_is_left_out_when_it_is_not(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import importlib.util

        real = importlib.util.find_spec
        monkeypatch.setattr(
            importlib.util,
            "find_spec",
            lambda name, *a: None if name == "pygame" else real(name, *a),
        )
        hidden = self._hidden(tmp_path)
        assert "pygame" not in hidden
        assert "pymunk" in hidden
