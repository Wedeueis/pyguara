"""Holds, taps and the input buffer land on the same frames when replayed.

Input time is moved by the frame's duration live and by the recorded
duration in a replay, so a gesture fires on the frame it fired on.
"""

from __future__ import annotations

import os

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

from pathlib import Path

import pygame
import pytest

from pyguara.application.application import Application
from pyguara.application.bootstrap import create_headless_application
from pyguara.events.input import KeyDownEvent, KeyUpEvent
from pyguara.input import Hold, Tap
from pyguara.input import keys as key_codes
from pyguara.input.events import OnActionEvent
from pyguara.input.types import ActionType, InputDevice
from tests.integration._scenes import ClearScene

FRAMES = 60
ATTACK = key_codes.D
# A long press, then a short one.
EDGES = {5: True, 40: False, 45: True, 47: False}


@pytest.fixture(autouse=True)
def _quit_pygame():
    yield
    pygame.quit()


class _Game:
    """Records the frame each gesture fired on, and buffered checks per frame."""

    def __init__(self, app: Application) -> None:
        self.app = app
        self.frame = 0
        self.fired: list[tuple[str, int]] = []
        self.buffered: list[bool] = []
        app.begin(ClearScene(app._event_dispatcher))
        manager = app._input_manager
        manager.register_action("attack", ActionType.PRESS)
        manager.bind_input(InputDevice.KEYBOARD, ATTACK, "attack")
        manager.add_gesture(Hold("charge", "attack", seconds=0.3))
        manager.add_gesture(Tap("jab", "attack", max_seconds=0.1))
        app._event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        if event.action_name in ("charge", "jab"):
            self.fired.append((event.action_name, self.frame))

    def step(self) -> None:
        self.app.step()
        self.buffered.append(self.app._input_manager.was_pressed_within("attack", 0.05))
        self.frame += 1


def _frames() -> list[list[object]]:
    frames: list[list[object]] = [[] for _ in range(FRAMES + 1)]
    for frame, down in EDGES.items():
        event = KeyDownEvent if down else KeyUpEvent
        frames[frame].append(event(key_code=ATTACK))
    return frames


def test_gestures_and_the_buffer_replay_on_the_same_frames(tmp_path: Path) -> None:
    app = create_headless_application()
    app.start_recording(seed=7)
    live = _Game(app)
    app._window.poll_events = iter(_frames()).__next__  # type: ignore[method-assign]
    for _ in range(FRAMES):
        live.step()
    data = app.stop_recording()
    assert data is not None
    path = tmp_path / "timing.replay.gz"
    assert app.save_recording(data, str(path))
    app.shutdown()
    pygame.quit()

    assert [name for name, _ in live.fired] == ["charge", "jab"]
    assert app._input_manager.time == pytest.approx(FRAMES / 60, rel=0.01)

    replay = create_headless_application()
    assert replay.load_replay(str(path))
    played = _Game(replay)
    replay._window.poll_events = lambda: []  # type: ignore[method-assign]
    for _ in range(FRAMES):
        played.step()
    replay.shutdown()

    assert played.fired == live.fired
    assert played.buffered == live.buffered
