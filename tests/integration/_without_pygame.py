"""Run a wgpu demo with pygame made unimportable, for `test_wgpu_without_pygame`.

    python _without_pygame.py <demo> <frames> [--stand-in-pending]

Prints `RAN <n>` on success. Any `import pygame` raises, so a failure names
the module that tried. `--stand-in-pending` replaces the two pieces that
still use pygame on every backend -- SDL's joysticks and the audio system --
so the rest of the path can be checked before those are replaced.
"""

from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path

sys.modules["pygame"] = None  # type: ignore[assignment]
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYGUARA_WINDOW", "offscreen")


def _stand_in_pending() -> None:
    joysticks = types.ModuleType("pyguara.input.backends.pygame_backend")

    class NoJoysticks:
        def init_joysticks(self) -> None: ...
        def quit_joysticks(self) -> None: ...
        def is_initialized(self) -> bool:
            return True

        def get_joystick_count(self) -> int:
            return 0

        def get_joystick(self, index: int) -> None:
            raise IndexError(index)

    joysticks.PygameInputBackend = NoJoysticks  # type: ignore[attr-defined]
    sys.modules[joysticks.__name__] = joysticks

    from pyguara.audio.audio_system import IAudioSystem
    from pyguara.audio.types import AudioCapability

    quiet = {
        n: (lambda self, *a, **k: None)
        for n in dir(IAudioSystem)
        if not n.startswith("_")
    }
    quiet.update(
        capabilities=AudioCapability.NONE,
        get_master_volume=lambda self: 1.0,
        get_sfx_volume=lambda self: 1.0,
        get_music_volume=lambda self: 1.0,
        get_bus_volume=lambda self, bus: 1.0,
        is_bus_muted=lambda self, bus: False,
        is_music_playing=lambda self: False,
        is_sound_active=lambda self, handle: False,
        get_bus_effects=lambda self, bus: (),
    )

    class NoSoundLoader:
        supported_extensions = [".wav", ".ogg", ".mp3", ".flac"]

        def load(self, path: str) -> None:
            raise OSError(f"{path}: no audio in this check")

        def load_with_meta(self, path: str, meta: object) -> None:
            raise OSError(f"{path}: no audio in this check")

    for name, attribute, value in (
        ("pygame_audio", "PygameAudioSystem", type("Quiet", (), quiet)),
        ("loaders", "PygameSoundLoader", NoSoundLoader),
    ):
        module = types.ModuleType(f"pyguara.audio.backends.pygame.{name}")
        setattr(module, attribute, value)
        sys.modules[module.__name__] = module


def main() -> None:
    demo, frames = sys.argv[1], int(sys.argv[2])
    if "--stand-in-pending" in sys.argv:
        _stand_in_pending()

    from pyguara.application.application import Application
    from pyguara.events.dispatcher import EventDispatcher
    from tools.demo_list import DEMOS

    bootstrap_module, scenes_module, scene_name = DEMOS[demo]
    container = importlib.import_module(bootstrap_module).configure_game_container()
    app = container.get(Application)
    scene = getattr(importlib.import_module(scenes_module), scene_name)
    ran = 0
    original = app._render

    def render() -> None:
        nonlocal ran
        original()
        ran += 1
        if ran >= frames:
            app._is_running = False

    app._render = render  # type: ignore[method-assign]
    dispatcher = (
        container.get(EventDispatcher)
        if EventDispatcher in container._services
        else app._event_dispatcher
    )
    app.run(starting_scene=scene(dispatcher))
    print(f"RAN {ran}")


if __name__ == "__main__":
    main()
