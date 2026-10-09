"""Playback speed, the playback modes beyond a loop bool, and clip slicing."""

import pytest
from PIL import Image

from pyguara.graphics.components.animation import (
    AnimationClip,
    Animator,
    PlaybackMode,
    add_clip,
    advance_animator,
    play_clip,
)
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.spritesheet import SpriteSheet
from pyguara.resources.types import Texture


class FakeTexture(Texture):
    """A texture that never touches a backend."""

    def __init__(self, index: int = 0) -> None:
        super().__init__(f"frame_{index}")
        self.index = index

    @property
    def width(self) -> int:
        return 1

    @property
    def height(self) -> int:
        return 1

    @property
    def native_handle(self) -> None:
        return None


class RecordingFactory:
    """A `TextureFactory` that hands back countable fakes."""

    def __init__(self) -> None:
        self.created = 0

    def create_from_bytes(
        self, name: str, data: bytes, width: int, height: int
    ) -> Texture:
        self.created += 1
        return FakeTexture(self.created)


def _animator(clip: AnimationClip) -> Animator:
    sprite = Sprite(texture=clip.frames[0])
    animator = Animator(sprite)
    add_clip(animator, clip)
    play_clip(animator, clip.name)
    return animator


def _clip(frames: int = 4, **kwargs) -> AnimationClip:
    return AnimationClip(
        name="test",
        frames=[FakeTexture(i) for i in range(frames)],
        frame_rate=10.0,
        **kwargs,
    )


def _indices(animator: Animator, ticks: int, dt: float = 0.1) -> list[int]:
    seen = [animator._current_frame_index]
    for _ in range(ticks):
        advance_animator(animator, dt)
        seen.append(animator._current_frame_index)
    return seen


# -- playback_speed --


def test_playback_speed_doubles_the_frame_rate():
    """A haste buff is one field, not a faster copy of every clip."""
    animator = _animator(_clip())
    animator.playback_speed = 2.0

    advance_animator(animator, 0.1)

    assert animator._current_frame_index == 2


def test_playback_speed_can_slow_a_clip_down():
    animator = _animator(_clip())
    animator.playback_speed = 0.5

    advance_animator(animator, 0.1)
    assert animator._current_frame_index == 0

    advance_animator(animator, 0.1)
    assert animator._current_frame_index == 1


def test_a_speed_of_zero_holds_the_cursor_without_stopping_playback():
    """What a hitstop wants: the animation resumes where it was rather than
    restarting."""
    animator = _animator(_clip())
    advance_animator(animator, 0.1)
    animator.playback_speed = 0.0

    for _ in range(10):
        advance_animator(animator, 0.1)

    assert animator._current_frame_index == 1
    assert animator.is_playing

    animator.playback_speed = 1.0
    advance_animator(animator, 0.1)
    assert animator._current_frame_index == 2


def test_a_negative_speed_holds_rather_than_running_backwards():
    """Running a clip backwards is `PING_PONG`'s business; a negative speed
    is far more likely a sign flip in a buff calculation."""
    animator = _animator(_clip())

    advance_animator(animator, 0.1)
    animator.playback_speed = -1.0
    advance_animator(animator, 0.1)

    assert animator._current_frame_index == 1


# -- Playback modes --


def test_loop_is_still_the_default_and_still_wraps():
    animator = _animator(_clip())

    assert _indices(animator, 5) == [0, 1, 2, 3, 0, 1]


def test_a_loop_bool_of_false_still_means_once():
    """`loop` predates `mode` and every prefab file still sets it."""
    clip = _clip(loop=False)

    assert clip.playback_mode is PlaybackMode.ONCE

    animator = _animator(clip)
    assert _indices(animator, 5) == [0, 1, 2, 3, 3, 3]
    assert not animator.is_playing


def test_mode_wins_over_loop_when_both_are_set():
    """It is the more specific statement."""
    clip = _clip(loop=True, mode=PlaybackMode.ONCE)

    assert clip.playback_mode is PlaybackMode.ONCE
    assert clip.loop is False


def test_ping_pong_walks_back_down_instead_of_cutting_to_frame_zero():
    """An idle bob or a breathing loop: the hard cut is visible as a hitch."""
    animator = _animator(_clip(mode=PlaybackMode.PING_PONG))

    assert _indices(animator, 8) == [0, 1, 2, 3, 2, 1, 0, 1, 2]


def test_ping_pong_never_stops():
    animator = _animator(_clip(mode=PlaybackMode.PING_PONG))

    for _ in range(50):
        advance_animator(animator, 0.1)

    assert animator.is_playing


def test_loop_times_stops_after_its_count():
    clip = _clip(mode=PlaybackMode.LOOP_TIMES, loop_count=2)
    animator = _animator(clip)

    indices = _indices(animator, 10)

    assert indices[:8] == [0, 1, 2, 3, 0, 1, 2, 3]
    assert indices[-1] == 3
    assert not animator.is_playing


def test_loop_times_needs_a_positive_count():
    """Zero would stop on the first frame and look like a missing animation."""
    with pytest.raises(ValueError, match="at least 1"):
        _clip(mode=PlaybackMode.LOOP_TIMES, loop_count=0)


def test_replaying_a_clip_resets_the_ping_pong_direction():
    animator = _animator(_clip(mode=PlaybackMode.PING_PONG))
    _indices(animator, 5)  # now travelling backwards

    play_clip(animator, "test", force_reset=True)
    advance_animator(animator, 0.1)

    assert animator._current_frame_index == 1


def test_a_single_frame_once_clip_still_finishes():
    """Otherwise `is_finished` never becomes true and an FSM waiting on
    ANIMATION_END hangs."""
    animator = _animator(_clip(frames=1, mode=PlaybackMode.ONCE))

    advance_animator(animator, 0.2)

    assert not animator.is_playing
    assert animator.is_finished


def test_a_single_frame_looping_clip_keeps_playing():
    animator = _animator(_clip(frames=1, mode=PlaybackMode.LOOP))

    advance_animator(animator, 1.0)

    assert animator.is_playing


def test_a_lag_spike_still_fires_every_frame_event_it_crossed():
    """Which is why PING_PONG walks frame by frame rather than computing
    the destination with modular arithmetic."""
    clip = _clip(
        mode=PlaybackMode.PING_PONG,
        frame_events={1: ("step",), 2: ("hit",), 3: ("end",)},
    )
    animator = _animator(clip)

    # Six frames owed: 1, 2, 3, then back down 2, 1, 0. Frame 0 carries no
    # event, so five fire -- including the turn at the far end.
    fired = advance_animator(animator, 0.6)

    assert fired == ["step", "hit", "end", "hit", "step"]


# -- SpriteSheet.clip --


def _sheet() -> SpriteSheet:
    image = Image.new("RGBA", (64, 32))
    return SpriteSheet.from_image(image, RecordingFactory(), "sheet")


def test_clip_takes_one_row_of_the_grid():
    """`frames[8:16]` by hand was the one place a sheet's layout leaked
    into game code."""
    clip = _sheet().clip("walk", 16, 16, row=1, fps=12.0)

    assert clip.name == "walk"
    assert len(clip.frames) == 4
    assert clip.frame_rate == 12.0


def test_clip_can_take_fewer_frames_than_the_row_holds():
    clip = _sheet().clip("walk", 16, 16, row=0, count=2)

    assert len(clip.frames) == 2


def test_clip_carries_the_playback_mode_through():
    clip = _sheet().clip("idle", 16, 16, mode=PlaybackMode.PING_PONG)

    assert clip.playback_mode is PlaybackMode.PING_PONG


def test_clip_frame_events_are_relative_to_the_clip_not_the_sheet():
    clip = _sheet().clip("attack", 16, 16, row=1, frame_events={0: ("swing",)})

    assert clip.frame_events == {0: ("swing",)}


def test_a_row_past_the_end_of_the_sheet_is_refused():
    """A clip quietly short of frames animates wrongly rather than visibly
    failing."""
    with pytest.raises(ValueError, match="outside the sheet"):
        _sheet().clip("walk", 16, 16, row=9)


def test_asking_for_more_frames_than_the_row_holds_is_refused():
    with pytest.raises(ValueError, match="4 column"):
        _sheet().clip("walk", 16, 16, count=99)


def test_margin_and_spacing_reach_the_slicer():
    image = Image.new("RGBA", (70, 38))
    sheet = SpriteSheet.from_image(image, RecordingFactory(), "sheet")

    clip = sheet.clip("walk", 16, 16, margin=2, spacing=2)

    assert len(clip.frames) == 3
