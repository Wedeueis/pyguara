"""Bootstrap smoke test.

The audit's central finding wasn't any single bug: 1,022 passing tests, clean
ruff and clean mypy coexisted with an engine whose public entry point could
not run, because nothing in the suite executed the real `_setup_container()`
(`tests/integration/test_app_flow.py` hand-builds a container that omits
`RenderGraph`, so it silently takes the working render path and passes).

This test runs the real `create_application()` / `create_sandbox_application()`
through a real scene for ~30 frames and asserts clean shutdown. It is
deliberately left unmarked so it runs in `make test-unit` and `make ci`, not
only under the opt-in `-m integration` gate that already missed six critical
bugs once (LOG-1, BOOT-1, BOOT-2, BOOT-3) before this ticket existed.

This is the seed of the integration suite that demo migration will grow into.
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
