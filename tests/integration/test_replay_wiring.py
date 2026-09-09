"""Regression test for replay recording/playback wiring (wayfinder ticket 18).

Builds two independent Application instances from the real
`create_application()` bootstrap, records a short deterministic session
against the first (fixed seed, scripted key presses), saves it via
`ReplaySerializer`, then feeds the saved replay into the second and asserts
the resulting entity state matches what recording produced. Both runs are
seeded from the same template `Entity` via `Entity.clone()` (not
`copy.deepcopy`, which `Entity` rejects outright).

Deliberately left unmarked, like `test_bootstrap_smoke.py`, so it runs under
`make test-unit`/`make ci` rather than only the opt-in `-m integration` gate.
"""

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
import pytest

from games.boot_process.scenes import BootScene
from pyguara.application.application import Application
from pyguara.application.bootstrap import create_application
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.events.input import KeyDownEvent, KeyUpEvent
from pyguara.input import keys as key_codes
from pyguara.input.events import OnActionEvent
from pyguara.input.types import ActionType, InputContext, InputDevice

MOVE_KEY = key_codes.D
MOVE_STEP = 10.0
FIXED_DT = 1.0 / 60.0
NUM_FRAMES = 10

# Frame index -> keys newly pressed that frame; each press is released the
# following frame, giving three discrete PRESS-triggered moves.
SCRIPTED_PRESSES = {0: [MOVE_KEY], 4: [MOVE_KEY], 7: [MOVE_KEY]}


def _key_event(key: int, down: bool) -> KeyDownEvent | KeyUpEvent:
    return KeyDownEvent(key_code=key) if down else KeyUpEvent(key_code=key)


def _scripted_frames() -> list[list[object]]:
    """Build a fixed schedule of engine key events, one list per frame."""
    frames: list[list[object]] = [[] for _ in range(NUM_FRAMES)]
    for frame_id, codes in SCRIPTED_PRESSES.items():
        for key in codes:
            frames[frame_id].append(_key_event(key, down=True))
            frames[frame_id + 1].append(_key_event(key, down=False))
    return frames


def _make_poll_events(frames: list[list[object]]):
    iterator = iter(frames)
    return lambda: next(iterator, [])


def _wire_move_right(app: Application, entity: Entity) -> None:
    """Bind MOVE_KEY to a 'MoveRight' action that steps `entity`'s Transform."""

    def on_action(event: OnActionEvent) -> None:
        if event.action_name == "MoveRight":
            transform = entity.get_component(Transform)
            transform.position = transform.position + Vector2(MOVE_STEP, 0.0)

    app._event_dispatcher.subscribe(OnActionEvent, on_action)
    app._input_manager.register_action("MoveRight", ActionType.PRESS)
    app._input_manager.bind_input(
        InputDevice.KEYBOARD, MOVE_KEY, "MoveRight", InputContext.GAMEPLAY
    )


def _boot(app: Application) -> BootScene:
    scene = BootScene(app._event_dispatcher)
    app._scene_manager.register(scene)
    app._scene_manager.switch_to(scene.name)
    return scene


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


def test_playback_steps_the_loop_by_recorded_dt_not_wall_clock(tmp_path):
    # Record at a lumpy, machine-specific frame cadence...
    record_ms = [33, 33, 10, 25, 16, 16, 16, 20, 8, 20]
    # ...then play back on a "machine" running at a steady, different one.
    playback_ms = [16] * 40

    record_app = create_application()
    scene = _boot(record_app)
    record_app._window.poll_events = _make_poll_events(_scripted_frames())
    record_app._clock = _FakeClock(record_ms)  # type: ignore[assignment]
    record_app.start_recording(seed=7)
    _run_frames(record_app, scene, len(record_ms))
    replay_data = record_app.stop_recording()
    assert replay_data is not None
    recorded_dts = [round(f.delta_time, 6) for f in replay_data.frames]
    assert recorded_dts == [round(ms / 1000.0, 6) for ms in record_ms]
    replay_path = str(tmp_path / "cadence.replay.gz")
    assert record_app.save_recording(replay_data, replay_path)
    record_app.shutdown()

    playback_app = create_application()
    scene = _boot(playback_app)
    seen_dts: list[float] = []
    real_update = playback_app._update

    def capture_update(dt: float) -> None:
        seen_dts.append(round(dt, 6))
        real_update(dt)

    playback_app._update = capture_update  # type: ignore[method-assign]
    playback_app._window.poll_events = _make_poll_events([[] for _ in playback_ms])
    playback_app._clock = _FakeClock(playback_ms)  # type: ignore[assignment]
    assert playback_app.load_replay(replay_path)
    _run_frames(playback_app, scene, len(record_ms) + 5)
    playback_app.shutdown()

    # The first N _update() calls ran on the recorded deltas, not the 16 ms
    # wall-clock cadence this "machine" was ticking at.
    assert seen_dts[: len(recorded_dts)] == recorded_dts
    assert playback_app._replay_player is None  # finished on schedule


def test_recorded_session_replays_to_the_same_entity_state(tmp_path):
    template = Entity("template")
    template.add_component(Transform(position=Vector2(0.0, 0.0)))

    # --- Record ---
    record_app = create_application()
    _boot(record_app)

    recorded_entity = template.clone("recorded")
    scene = record_app._scene_manager.current_scene
    assert scene is not None
    scene.entity_manager.add_entity(recorded_entity)
    _wire_move_right(record_app, recorded_entity)

    record_app._window.poll_events = _make_poll_events(_scripted_frames())
    seed = record_app.start_recording(seed=42)
    assert seed == 42

    for _ in range(NUM_FRAMES):
        record_app._process_input(FIXED_DT)

    replay_data = record_app.stop_recording()
    assert replay_data is not None
    assert replay_data.metadata.frame_count == NUM_FRAMES
    assert replay_data.metadata.seed == 42

    replay_path = str(tmp_path / "session.replay.gz")
    assert record_app.save_recording(replay_data, replay_path)
    record_app.shutdown()

    recorded_position = recorded_entity.get_component(Transform).position
    # Sanity check: movement actually happened, so a trivial "nothing moved"
    # state can't accidentally satisfy the final assertion.
    assert recorded_position == Vector2(MOVE_STEP * len(SCRIPTED_PRESSES), 0.0)

    # --- Playback ---
    playback_app = create_application()
    _boot(playback_app)

    playback_entity = template.clone("playback")
    scene = playback_app._scene_manager.current_scene
    assert scene is not None
    scene.entity_manager.add_entity(playback_entity)
    _wire_move_right(playback_app, playback_entity)

    # No real input during playback; the replay drives the game instead.
    playback_app._window.poll_events = _make_poll_events(
        [[] for _ in range(NUM_FRAMES)]
    )
    assert playback_app.load_replay(replay_path)

    for _ in range(NUM_FRAMES):
        playback_app._process_input(FIXED_DT)

    assert playback_app._replay_player is None  # finished exactly on schedule
    playback_app.shutdown()

    playback_position = playback_entity.get_component(Transform).position
    assert playback_position == recorded_position
