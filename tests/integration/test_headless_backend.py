"""Headless backend smoke test (wayfinder ticket 19).

`create_headless_application()`/`create_headless_sandbox_application()` swap
the window/renderer/UI-renderer/texture-factory quartet for the no-op
`pyguara.graphics.backends.headless_renderer` implementations, which never
touch `pygame.display` (or any other SDL video call) -- unlike the real
Pygame backend under `SDL_VIDEODRIVER=dummy`. No SDL video driver, dummy or
otherwise, is set anywhere in this module.

This is deliberately a separate file from `test_bootstrap_smoke.py`: that
test's whole point is exercising the *real* pygame/ModernGL backend-selection
branch in `_setup_container()` (the exact code path BOOT-1/2/3 broke), so it
keeps using the real Pygame backend rather than switching to headless -- doing
so would bypass that branch entirely and reopen the coverage gap those bugs
exploited. This file proves the headless path itself works, standalone.

Deliberately left unmarked, like `test_bootstrap_smoke.py`, so it runs under
`make test-unit`/`make ci`.
"""

from games.boot_process.scenes import BootScene
from pyguara.application.application import Application
from pyguara.application.bootstrap import (
    create_headless_application,
    create_headless_sandbox_application,
)


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
