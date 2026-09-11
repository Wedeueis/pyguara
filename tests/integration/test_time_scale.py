"""Regression tests for Application.time_scale/paused (#68's P1 item).

Uses the real `create_application()` bootstrap and a scripted fake clock,
the same approach `test_replay_wiring.py` uses to drive `run()` for an
exact number of frames.
"""

import os
import tempfile

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
import pytest

from games.boot_process.scenes import BootScene
from pyguara.application.application import Application
from pyguara.application.bootstrap import create_application


@pytest.fixture(autouse=True)
def _quit_pygame():
    yield
    pygame.quit()


class _FakeClock:
    """Stand-in for `pygame.time.Clock` whose `tick()` returns a scripted ms."""

    def __init__(self, ms_sequence: list[int]) -> None:
        self._it = iter(ms_sequence)

    def tick(self, _fps: float = 0.0) -> int:
        return next(self._it, 16)


def _boot(app: Application) -> BootScene:
    scene = BootScene(app._event_dispatcher)
    app._scene_manager.register(scene)
    app._scene_manager.switch_to(scene.name)
    return scene


def _run_frames(app: Application, scene: BootScene, n: int) -> None:
    """Drive `app.run()` for exactly `n` frames by stopping it from `_render`."""
    remaining = n
    real_render = app._render

    def render_then_maybe_stop() -> None:
        nonlocal remaining
        real_render()
        remaining -= 1
        if remaining <= 0:
            app._is_running = False

    app._render = render_then_maybe_stop  # type: ignore[method-assign]
    app.run(scene)


def _no_events():
    return []


def _capture_updates(app: Application) -> list[float]:
    """Patch `app._update` to record every dt it's called with."""
    seen: list[float] = []
    real_update = app._update

    def capture(dt: float) -> None:
        seen.append(dt)
        real_update(dt)

    app._update = capture  # type: ignore[method-assign]
    return seen


def _count_fixed_updates(app: Application) -> list[int]:
    """Patch `app._fixed_update` to count calls; returns a single-item list
    (a mutable box, so the count is visible after `run_frames` returns)."""
    count = [0]
    real_fixed_update = app._fixed_update

    def counting(fixed_dt: float) -> None:
        count[0] += 1
        real_fixed_update(fixed_dt)

    app._fixed_update = counting  # type: ignore[method-assign]
    return count


def test_default_time_scale_is_unscaled():
    app = create_application()
    scene = _boot(app)
    app._window.poll_events = _no_events
    app._clock = _FakeClock([16] * 5)  # type: ignore[assignment]
    seen = _capture_updates(app)

    _run_frames(app, scene, 5)
    app.shutdown()

    assert seen == pytest.approx([0.016] * 5)


def test_time_scale_halves_the_dt_update_receives():
    app = create_application()
    scene = _boot(app)
    app.time_scale = 0.5
    app._window.poll_events = _no_events
    app._clock = _FakeClock([16] * 5)  # type: ignore[assignment]
    seen = _capture_updates(app)

    _run_frames(app, scene, 5)
    app.shutdown()

    assert seen == pytest.approx([0.008] * 5)


def test_time_scale_reduces_fixed_step_count_not_fixed_dt():
    """Half-speed time buys half as many fixed steps over the same real
    time -- the step size itself (fixed_dt) never changes."""
    app = create_application()
    scene = _boot(app)
    app._window.poll_events = _no_events
    # 60 frames of 16ms is a bit under 1 real second; at 60Hz physics that's
    # ~59-60 fixed steps at full speed, ~29-30 at half speed.
    full_speed_count = _count_fixed_updates(app)
    app._clock = _FakeClock([16] * 60)  # type: ignore[assignment]
    _run_frames(app, scene, 60)
    app.shutdown()

    app2 = create_application()
    scene2 = _boot(app2)
    app2.time_scale = 0.5
    app2._window.poll_events = _no_events
    half_speed_count = _count_fixed_updates(app2)
    app2._clock = _FakeClock([16] * 60)  # type: ignore[assignment]
    _run_frames(app2, scene2, 60)
    app2.shutdown()

    assert half_speed_count[0] < full_speed_count[0]
    assert half_speed_count[0] == pytest.approx(full_speed_count[0] / 2, abs=1)


def test_paused_stops_both_fixed_and_variable_update():
    app = create_application()
    scene = _boot(app)
    app.paused = True
    app._window.poll_events = _no_events
    app._clock = _FakeClock([16] * 5)  # type: ignore[assignment]
    seen = _capture_updates(app)
    fixed_count = _count_fixed_updates(app)

    _run_frames(app, scene, 5)
    app.shutdown()

    assert seen == pytest.approx([0.0] * 5)
    assert fixed_count[0] == 0


def test_unpausing_restores_the_time_scale_that_was_set_before_pausing():
    app = create_application()
    scene = _boot(app)
    app.time_scale = 0.25
    app.paused = True
    app._window.poll_events = _no_events
    app._clock = _FakeClock([16, 16])  # type: ignore[assignment]
    seen = _capture_updates(app)

    # Unpause mid-run via a scripted render hook instead of two separate
    # `run()` calls -- `run()` only returns once the loop stops.
    calls = [0]
    real_render = app._render

    def render_hook() -> None:
        real_render()
        calls[0] += 1
        if calls[0] == 1:
            app.paused = False
        else:
            app._is_running = False

    app._render = render_hook  # type: ignore[method-assign]
    app.run(scene)
    app.shutdown()

    assert seen[0] == pytest.approx(0.0)  # still paused
    assert seen[1] == pytest.approx(0.016 * 0.25)  # unpaused, scale restored


def test_replay_playback_ignores_time_scale_and_pause():
    record_app = create_application()
    scene = _boot(record_app)
    record_app._window.poll_events = _no_events
    record_app._clock = _FakeClock([16] * 5)  # type: ignore[assignment]
    record_app.start_recording(seed=1)
    _run_frames(record_app, scene, 5)
    replay_data = record_app.stop_recording()
    assert replay_data is not None
    recorded_dts = [round(f.delta_time, 6) for f in replay_data.frames]
    record_app.shutdown()

    with tempfile.TemporaryDirectory() as tmp_dir:
        replay_path = os.path.join(tmp_dir, "cadence.replay.gz")
        assert record_app.save_recording(replay_data, replay_path)

        playback_app = create_application()
        scene = _boot(playback_app)
        playback_app.time_scale = 0.1
        playback_app.paused = True
        playback_app._window.poll_events = _no_events
        playback_app._clock = _FakeClock([16] * 5)  # type: ignore[assignment]
        seen = _capture_updates(playback_app)
        assert playback_app.load_replay(replay_path)
        _run_frames(playback_app, scene, 5)
        playback_app.shutdown()

    assert [round(dt, 6) for dt in seen] == recorded_dts
