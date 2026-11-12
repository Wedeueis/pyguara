"""A machine with no audio output must still be able to start a game.

Each case runs in its own process with a driver that can't open, so the real mixer really
fails, and nothing here disturbs the mixer other tests are using.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pygame
import pytest

from pyguara.audio.backends.pygame import pygame_audio

NO_SUCH_DRIVER = "no-such-audio-driver"


def run(code: str, driver: str = NO_SUCH_DRIVER) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "SDL_AUDIODRIVER": driver,
        "SDL_VIDEODRIVER": "dummy",
    }
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
    )


def test_the_engine_starts_and_plays_with_no_audio_output() -> None:
    result = run(
        """
        import os
        import pygame
        from pyguara.application.bootstrap import create_headless_application

        app = create_headless_application()
        assert pygame.mixer.get_init() is not None
        assert pygame.mixer.get_num_channels() == 32
        pygame.mixer.Sound(buffer=bytes(4096)).play()
        assert os.environ["SDL_AUDIODRIVER"] == "no-such-audio-driver"
        app.shutdown()
        print("started")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "started" in result.stdout
    assert "No audio output" in result.stdout + result.stderr


def test_the_native_backend_starts_with_no_audio_output() -> None:
    pytest.importorskip("pyguara.pyguara_core_rs")
    result = run(
        """
        import sys
        from pyguara.audio.backends.native.native_audio import NativeAudioSystem

        system = NativeAudioSystem()
        # The device, or the silent clock when there is none: never an error.
        assert system.output.startswith(("device:", "silent:")), system.output
        assert "pygame" not in sys.modules, "the native backend loaded pygame"
        print("started")
        """
    )
    assert result.returncode == 0, result.stderr
    assert "started" in result.stdout


def test_a_working_output_says_nothing_about_being_silent() -> None:
    result = run(
        """
        from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem

        PygameAudioSystem()
        print("started")
        """,
        driver="dummy",
    )
    assert result.returncode == 0, result.stderr
    assert "No audio output" not in result.stdout + result.stderr


@pytest.mark.parametrize("configured", [None, "alsa"], ids=["unset", "set"])
def test_the_driver_setting_is_put_back_even_if_the_fallback_fails(
    monkeypatch: pytest.MonkeyPatch, configured: str | None
) -> None:
    """Otherwise a later mixer in this process would silently use the dummy driver."""
    if configured is None:
        monkeypatch.delenv("SDL_AUDIODRIVER", raising=False)
    else:
        monkeypatch.setenv("SDL_AUDIODRIVER", configured)
    seen: list[str | None] = []

    def fail(*_: object) -> None:
        seen.append(os.environ.get("SDL_AUDIODRIVER"))
        raise pygame.error("nothing here")

    monkeypatch.setattr(pygame.mixer, "init", fail)
    with pytest.raises(pygame.error):
        pygame_audio._open_mixer(44100, -16, 2, 512)
    assert seen == [configured, "dummy"]
    assert os.environ.get("SDL_AUDIODRIVER") == configured
