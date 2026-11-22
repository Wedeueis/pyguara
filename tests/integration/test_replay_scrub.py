"""Pausing, stepping, speeding and seeking a replay keeps it reproducing.

A recorded flock is the measure: wherever the controls take the playback,
the agents must be where the recording had them at that frame.
"""

from __future__ import annotations

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pygame
import pytest

from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem
from pyguara.application.application import Application
from pyguara.application.bootstrap import create_headless_application
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.events.input import KeyDownEvent, KeyUpEvent
from pyguara.input import keys as key_codes
from pyguara.input.events import OnActionEvent
from pyguara.input.types import ActionType, InputContext, InputDevice
from pyguara.random.service import RandomService
from pyguara.replay.controls import ReplayControls
from tests.integration._scenes import ClearScene

FRAMES = 90
SPAWN = key_codes.D
PRESSES = (5, 30, 31, 60)
Positions = list[tuple[float, float]]


@pytest.fixture(autouse=True)
def _quit_pygame():
    yield
    pygame.quit()


class _Flock:
    """A flock of agents scattered from the seeded stream; a press adds three."""

    def __init__(self, app: Application) -> None:
        self.app = app
        self.scene = ClearScene(app._event_dispatcher)
        app.begin(self.scene)
        self._populate()
        app._event_dispatcher.subscribe(OnActionEvent, self._on_action)
        app._input_manager.register_action("Spawn", ActionType.PRESS)
        app._input_manager.bind_input(
            InputDevice.KEYBOARD, SPAWN, "Spawn", InputContext.GAMEPLAY
        )

    def _populate(self) -> None:
        self._rng = self.app.container.get(RandomService).stream("flock")
        self._spawn(40)
        self.scene.system_manager.register(FlockingSystem(self.scene.entity_manager))

    def _spawn(self, count: int) -> None:
        for _ in range(count):
            entity = self.scene.entity_manager.create_entity()
            entity.add_component(
                Transform(
                    position=Vector2(
                        self._rng.uniform(0, 300), self._rng.uniform(0, 300)
                    )
                )
            )
            entity.add_component(
                FlockingAgent(
                    velocity=Vector2(
                        self._rng.uniform(-40, 40), self._rng.uniform(-40, 40)
                    )
                )
            )

    def _on_action(self, event: OnActionEvent) -> None:
        if event.action_name == "Spawn":
            self._spawn(3)

    def restart(self) -> None:
        """Back to the world the recording began in: a fresh scene."""
        self.scene = ClearScene(self.app._event_dispatcher)
        self.app._scene_manager.register(self.scene)
        self.app._scene_manager.switch_to(self.scene.name)
        self._populate()

    def positions(self) -> Positions:
        return sorted(
            (t.position.x, t.position.y)
            for t in (
                e.get_component(Transform)
                for e in self.scene.entity_manager.get_entities_with(Transform)
            )
        )


def _frames(presses: tuple[int, ...]) -> list[list[object]]:
    frames: list[list[object]] = [[] for _ in range(FRAMES + 1)]
    for frame in presses:
        frames[frame].append(KeyDownEvent(key_code=SPAWN))
        frames[frame + 1].append(KeyUpEvent(key_code=SPAWN))
    return frames


@pytest.fixture(scope="module")
def recording(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[Positions]]:
    """The replay, and where the flock was after each recorded frame."""
    path = tmp_path_factory.mktemp("scrub") / "flock.replay.gz"
    app = create_headless_application()
    app.start_recording(seed=2024)
    flock = _Flock(app)
    app._window.poll_events = iter(_frames(PRESSES)).__next__  # type: ignore[method-assign]
    after: list[Positions] = [flock.positions()]
    for _ in range(FRAMES):
        app.step()
        after.append(flock.positions())
    data = app.stop_recording()
    assert data is not None
    assert app.save_recording(data, str(path))
    app.shutdown()
    pygame.quit()
    return path, after


class _Playback:
    def __init__(self, path: Path, *, rewind: bool = True) -> None:
        self.app = create_headless_application()
        self._flock: _Flock | None = None
        restart: Callable[[], None] | None = (
            (lambda: self.flock.restart()) if rewind else None
        )
        assert self.app.load_replay(str(path), restart=restart)
        self._flock = _Flock(self.app)
        self.keys: list[list[object]] = []
        self.app._window.poll_events = self._poll  # type: ignore[method-assign]

    @property
    def flock(self) -> _Flock:
        assert self._flock is not None
        return self._flock

    @property
    def controls(self) -> ReplayControls:
        controls = self.app.replay_controls
        assert controls is not None
        return controls

    def _poll(self) -> list[object]:
        return self.keys.pop(0) if self.keys else []

    def steps(self, count: int) -> None:
        for _ in range(count):
            self.app.step()

    def until_seeked(self) -> None:
        while self.controls.seeking:
            self.app.step()


def test_paused_the_world_holds_still(recording: Any) -> None:
    path, after = recording
    play = _Playback(path)
    play.steps(10)
    play.controls.pause()

    play.steps(20)

    assert play.controls.frame == 10
    assert play.flock.positions() == after[10]


def test_a_step_plays_exactly_one_frame(recording: Any) -> None:
    path, after = recording
    play = _Playback(path)
    play.steps(4)

    play.controls.step()
    play.steps(3)

    assert play.controls.paused
    assert play.controls.frame == 5
    assert play.flock.positions() == after[5]


def test_double_speed_plays_two_frames_a_step_and_still_reproduces(
    recording: Any,
) -> None:
    path, after = recording
    play = _Playback(path)
    play.controls.visible = True  # hold at the end rather than play on live
    play.controls.faster()
    assert play.controls.speed == 2.0

    play.steps(10)
    assert play.controls.frame == 20
    play.steps(FRAMES)

    assert play.controls.frame == FRAMES
    assert play.flock.positions() == after[FRAMES]


def test_quarter_speed_plays_every_fourth_step(recording: Any) -> None:
    path, after = recording
    play = _Playback(path)
    play.controls.slower()
    play.controls.slower()
    assert play.controls.speed == 0.25

    play.steps(8)

    assert play.controls.frame == 2
    assert play.flock.positions() == after[2]


def test_seeking_forward_arrives_where_playing_would(recording: Any) -> None:
    path, after = recording
    play = _Playback(path)

    play.controls.seek(70)
    play.until_seeked()

    assert play.controls.frame == 70
    assert play.controls.paused
    assert play.flock.positions() == after[70]


def test_seeking_back_replays_from_the_start(recording: Any) -> None:
    path, after = recording
    play = _Playback(path)
    play.controls.visible = True  # hold at the end rather than play on live
    play.steps(80)

    play.controls.seek(30)
    play.until_seeked()
    assert play.controls.frame == 30
    assert play.flock.positions() == after[30]

    play.controls.resume()
    play.steps(FRAMES)
    assert play.flock.positions() == after[FRAMES]


def test_without_restart_seeking_back_is_refused(recording: Any) -> None:
    path, _ = recording
    play = _Playback(path, rewind=False)
    play.steps(20)

    with pytest.raises(RuntimeError, match="restart"):
        play.controls.seek(5)
    assert play.controls.frame == 20


def test_hidden_controls_hand_input_back_at_the_end(recording: Any) -> None:
    path, _ = recording
    play = _Playback(path)

    play.steps(FRAMES)

    assert play.app.replay_controls is None


def test_shown_controls_hold_at_the_end_and_can_go_again(recording: Any) -> None:
    path, after = recording
    play = _Playback(path)
    play.controls.visible = True
    play.steps(FRAMES + 10)

    assert play.controls.finished
    assert play.flock.positions() == after[FRAMES]

    play.controls.seek(0)
    play.until_seeked()
    play.controls.resume()
    play.steps(45)
    assert play.flock.positions() == after[45]


def test_the_keys_drive_it_only_while_shown(recording: Any) -> None:
    path, _ = recording
    play = _Playback(path)

    play.keys = [[KeyDownEvent(key_code=key_codes.SPACE)]]
    play.steps(2)
    assert not play.controls.paused

    play.controls.visible = True
    play.keys = [[KeyDownEvent(key_code=key_codes.SPACE)]]
    play.steps(5)
    assert play.controls.paused
    frame = play.controls.frame

    play.keys = [[KeyDownEvent(key_code=key_codes.PERIOD)]]
    play.steps(3)
    assert play.controls.frame == frame + 1


def test_a_live_key_does_not_reach_the_game_while_a_replay_plays(
    recording: Any,
) -> None:
    """The recording pressed spawn four times; a fifth press must not count."""
    path, after = recording
    play = _Playback(path)
    play.controls.visible = True
    play.keys = [[KeyDownEvent(key_code=SPAWN)], [KeyUpEvent(key_code=SPAWN)]]

    play.steps(FRAMES)

    assert play.flock.positions() == after[FRAMES]


def test_a_long_seek_is_spread_over_frames(
    recording: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """So the window keeps drawing, and the bar shows the seek moving."""
    import pyguara.application.application as application

    monkeypatch.setattr(application, "SEEK_FRAMES_PER_STEP", 25)
    path, after = recording
    play = _Playback(path)

    play.controls.seek(60)
    play.steps(1)
    assert play.controls.frame == 25
    assert play.controls.seeking

    play.steps(2)
    assert play.controls.frame == 60
    assert not play.controls.seeking
    assert play.flock.positions() == after[60]


def test_pausing_the_player_itself_freezes_the_world_too(recording: Any) -> None:
    """Rather than run on the wall clock with every input swallowed."""
    path, after = recording
    play = _Playback(path)
    play.steps(10)
    assert play.app._replay_player is not None
    play.app._replay_player.pause_playback()

    play.steps(20)

    assert play.flock.positions() == after[10]
