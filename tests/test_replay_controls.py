"""`ReplayControls` and the scrub bar, without an application."""

from __future__ import annotations

from typing import Any

import pytest

from pyguara.input import keys
from pyguara.replay.controls import (
    SPEEDS,
    ReplayControls,
    draw_replay_controls,
    status_text,
)
from pyguara.replay.player import ReplayPlayer
from pyguara.replay.types import InputFrame, ReplayData, ReplayMetadata


def _player(frames: int = 120, dt: float = 0.05) -> ReplayPlayer:
    data = ReplayData(
        metadata=ReplayMetadata(frame_count=frames, duration=frames * dt),
        frames=[
            InputFrame(frame_id=i, timestamp=i * dt, delta_time=dt)
            for i in range(frames)
        ],
    )
    player = ReplayPlayer(data)
    player.start_playback()
    return player


def _controls(*, can_rewind: bool = True, **kwargs: Any) -> ReplayControls:
    return ReplayControls(_player(**kwargs), can_rewind=can_rewind)


def _due(controls: ReplayControls, frames: int) -> list[int]:
    return [controls.frames_due() for _ in range(frames)]


def test_normal_speed_is_one_frame_a_frame() -> None:
    assert _due(_controls(), 4) == [1, 1, 1, 1]


@pytest.mark.parametrize(
    ("index", "expected"),
    [(0, [0, 0, 0, 1, 0, 0, 0, 1]), (1, [0, 1, 0, 1, 0, 1, 0, 1]), (5, [8] * 8)],
)
def test_each_speed_owes_its_frames(index: int, expected: list[int]) -> None:
    controls = _controls()
    for _ in range(len(SPEEDS)):
        controls.slower()
    for _ in range(index):
        controls.faster()

    assert controls.speed == SPEEDS[index]
    assert _due(controls, 8) == expected


def test_speed_stops_at_either_end() -> None:
    controls = _controls()
    for _ in range(20):
        controls.faster()
    assert controls.speed == SPEEDS[-1]
    for _ in range(20):
        controls.slower()
    assert controls.speed == SPEEDS[0]


def test_paused_owes_nothing_and_a_step_owes_one() -> None:
    controls = _controls()
    controls.pause()
    assert _due(controls, 3) == [0, 0, 0]

    controls.step()
    assert _due(controls, 3) == [1, 0, 0]


def test_a_step_while_playing_pauses() -> None:
    controls = _controls()
    controls.step()
    assert controls.paused
    assert _due(controls, 2) == [1, 0]


def test_resuming_slow_motion_does_not_pay_out_what_was_owed() -> None:
    controls = _controls()
    controls.slower()  # 0.5
    controls.frames_due()  # owes half a frame
    controls.pause()
    controls.resume()
    assert _due(controls, 2) == [0, 1]


def test_time_and_frame_convert_both_ways() -> None:
    controls = _controls(frames=100, dt=0.1)
    assert controls.time_at(0) == 0.0
    assert controls.time_at(30) == pytest.approx(3.0)
    assert controls.time_at(100) == pytest.approx(10.0)
    assert controls.frame_at(3.04) == 30
    assert controls.frame_at(-5.0) == 0
    assert controls.frame_at(99.0) == 99


def test_seek_is_clamped_to_the_replay_and_pauses() -> None:
    controls = _controls(frames=50)
    controls.seek(500)
    assert controls.take_seek() == 50
    assert controls.paused
    controls.seek(-3)
    assert controls.take_seek() == 0


def test_seek_back_without_rewind_is_refused_but_forward_is_not() -> None:
    player = _player()
    player.seek_to_frame(40)
    controls = ReplayControls(player, can_rewind=False)

    with pytest.raises(RuntimeError, match="restart"):
        controls.seek(10)
    assert controls.take_seek() is None

    controls.seek(60)
    assert controls.take_seek() == 60


def test_skip_moves_by_seconds() -> None:
    player = _player(frames=400, dt=0.05)
    player.seek_to_frame(200)
    controls = ReplayControls(player, can_rewind=True)

    controls.skip(5.0)
    assert controls.take_seek() == 300
    controls.skip(-5.0)
    assert controls.take_seek() == 100


def test_keys_do_nothing_while_hidden() -> None:
    controls = _controls()
    assert not controls.handle_key(keys.SPACE)
    assert not controls.paused


@pytest.mark.parametrize(
    ("key", "check"),
    [
        (keys.SPACE, lambda c: c.paused),
        (keys.PERIOD, lambda c: c.paused and c.frames_due() == 1),
        (keys.R_BRACKET, lambda c: c.speed == 2.0),
        (keys.L_BRACKET, lambda c: c.speed == 0.5),
        (keys.RIGHT, lambda c: c.take_seek() == 100),
        (keys.HOME, lambda c: c.take_seek() == 0),
    ],
)
def test_each_key_does_its_job(key: int, check: Any) -> None:
    controls = _controls(frames=400, dt=0.05)
    controls.visible = True
    assert controls.handle_key(key)
    assert check(controls)


def test_without_rewind_the_back_keys_are_not_taken() -> None:
    controls = _controls(can_rewind=False)
    controls.visible = True
    assert not controls.handle_key(keys.LEFT)
    assert not controls.handle_key(keys.HOME)
    assert controls.take_seek() is None


def test_another_key_is_not_taken() -> None:
    controls = _controls()
    controls.visible = True
    assert not controls.handle_key(keys.A)


def test_the_status_line_names_the_state() -> None:
    player = _player(frames=1200, dt=0.05)
    controls = ReplayControls(player, can_rewind=True)
    assert status_text(controls) == "playing  1x  frame 0/1200  0:00.0 / 1:00.0"

    controls.pause()
    assert status_text(controls).startswith("paused")
    controls.seek(10)
    assert status_text(controls).startswith("seeking")
    controls.seek_done()
    player.seek_to_frame(1199)
    player.advance_frame()
    assert status_text(controls).startswith("ended")


class _Renderer:
    def __init__(self) -> None:
        self.rects: list[Any] = []
        self.texts: list[str] = []

    def draw_rect(self, rect: Any, color: Any, width: int = 0) -> None:
        self.rects.append(rect)

    def draw_text(self, text: str, position: Any, color: Any, size: int = 0) -> None:
        self.texts.append(text)


def test_the_bar_is_drawn_only_while_shown_and_fills_with_progress() -> None:
    player = _player(frames=100)
    controls = ReplayControls(player, can_rewind=True)
    renderer = _Renderer()

    draw_replay_controls(controls, renderer, 800, 600)  # type: ignore[arg-type]
    assert renderer.rects == []

    controls.visible = True
    player.seek_to_frame(25)
    draw_replay_controls(controls, renderer, 800, 600)  # type: ignore[arg-type]

    panel, track, played = renderer.rects
    assert panel.y + panel.height == 600
    assert played.width == round(track.width / 4)
    assert renderer.texts[0] == status_text(controls)
    assert "home start" in renderer.texts[1]
