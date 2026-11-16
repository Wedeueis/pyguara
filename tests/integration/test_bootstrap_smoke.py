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


def test_bootstrap_resolves_the_native_store_from_config():
    """The engine-wide switch is wired, and wired *before* anything reads it.

    `pyguara.native` holds process-wide state that pools consult at
    construction, so "the config value reaches it" is the whole contract --
    and nothing else in the suite runs the real bootstrap, which is the
    gap this file exists for in the first place.

    Asserted through `configure`, the hook that runs after the config
    loads and before the window, because that is where a game sets this.
    """
    from pyguara import native
    from pyguara.config.types import GameConfig
    from pyguara.native import NativeAcceleration

    def pick_python(config: GameConfig) -> None:
        config.performance.native_acceleration = NativeAcceleration.OFF

    try:
        app = create_application(configure=pick_python)

        assert native.resolved() is NativeAcceleration.OFF
        assert native.in_use() is False

        app._window.close()
    finally:
        # Process-wide state: leaving it OFF would decide the store for
        # every test that runs after this one.
        native.reset_for_tests()
