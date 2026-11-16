"""Headless backend smoke test.

`create_headless_application()` and
`create_headless_sandbox_application()` swap the window, renderer, UI
renderer and texture factory for the no-op ones in
`pyguara.graphics.backends.headless_renderer`, which make no SDL video
call. No SDL video driver is set anywhere in this module.

Separate from `test_bootstrap_smoke.py`, which must keep exercising
the real backend-selection branch. Left unmarked, so it runs under
`make test-unit` and `make ci`.
"""

from games.boot_process.scenes import BootScene
from pyguara.application.application import Application
from pyguara.application.bootstrap import (
    create_headless_application,
    create_headless_sandbox_application,
)
from pyguara.common.types import Color, Vector2
from pyguara.graphics.backends.headless_renderer import HeadlessBackend


def test_draw_text_is_a_noop_that_does_not_raise() -> None:
    """#71's world-space text primitive, added to IRenderer, must not break
    the headless backend's no-op contract."""
    backend = HeadlessBackend(width=800, height=600)

    backend.draw_text("Hi", Vector2(10, 10), Color(255, 255, 255))


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


def test_create_headless_application_boots_runs_and_shuts_down_cleanly():
    app = create_headless_application()

    ticks = _run_for_n_frames(app, frames=30)

    assert ticks == 30
    assert app._is_running is False
    assert app._window.is_open is False
    assert app._log_manager._loggers == {}


def test_create_headless_sandbox_application_boots_runs_and_shuts_down_cleanly():
    app = create_headless_sandbox_application()

    ticks = _run_for_n_frames(app, frames=30)

    assert ticks == 30
    assert app._is_running is False
    assert app._window.is_open is False
    assert app._log_manager._loggers == {}
