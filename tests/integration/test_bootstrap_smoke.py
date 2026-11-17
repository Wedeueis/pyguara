"""Bootstrap smoke test.

Runs the real `create_application()` and
`create_sandbox_application()` through a real scene for about 30
frames and asserts a clean shutdown. A test that hand-builds its
container does not execute `_setup_container()`, and the entry point
has been broken before with the rest of the suite green.

Left unmarked on purpose, so it runs in `make test-unit` and
`make ci`, not only under `-m integration`.
"""

import os

import pygame
import pytest

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

from games.boot_process.scenes import BootScene
from pyguara.application.application import Application
from pyguara.application.bootstrap import create_application, create_sandbox_application


def _run_for_n_frames(app: Application, frames: int) -> int:
    """Run `app` for exactly `frames` fixed updates, then stop cleanly."""
    ticks = 0
    original_update = app._update

    def patched_update(dt: float) -> None:
        nonlocal ticks
        ticks += 1
        if ticks >= frames:
            app._is_running = False
        original_update(dt)

    app._update = patched_update

    scene = BootScene(app._event_dispatcher)
    app.run(scene)

    return ticks


@pytest.fixture(autouse=True)
def _quit_pygame():
    yield
    pygame.quit()


def test_create_application_boots_runs_and_shuts_down_cleanly():
    app = create_application()

    ticks = _run_for_n_frames(app, frames=30)

    assert ticks == 30
    assert app._is_running is False
    assert app._window.is_open is False
    assert app._log_manager._loggers == {}


def test_create_sandbox_application_boots_runs_and_shuts_down_cleanly():
    app = create_sandbox_application()

    ticks = _run_for_n_frames(app, frames=30)

    assert ticks == 30
    assert app._is_running is False
    assert app._window.is_open is False
    assert app._log_manager._loggers == {}


def test_bootstrap_requires_the_native_extension(monkeypatch):
    """A missing extension stops the engine at bootstrap, naming what is missing.

    Not later, from whichever service is built first: every backend
    subsystem needs it, and an error from the middle of the container
    setup would name the wrong thing.
    """
    import sys

    from pyguara import native

    monkeypatch.setitem(sys.modules, native._MODULE_NAME, None)
    monkeypatch.setattr(native, "_candidate_paths", list)
    native.reset_lookup()
    try:
        with pytest.raises(RuntimeError, match="PyGuara needs the native extension"):
            create_application()
    finally:
        monkeypatch.undo()
        native.reset_lookup()
