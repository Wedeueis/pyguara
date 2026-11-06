"""`AudioManager.set_sfx_limit`: how much of one sound plays at once."""

from __future__ import annotations

import math
from typing import Any

import pytest

from pyguara.audio.manager import AudioManager, SfxLimit
from pyguara.audio.types import AudioCapability, SoundHandle, new_sound_handle
from pyguara.resources.types import AudioClip


class _Clip(AudioClip):
    @property
    def duration(self) -> float:
        return 1.0

    @property
    def native_handle(self) -> Any:
        return None


class _Mixer:
    """Plays nothing; remembers what it was asked to start, and what's still on."""

    capabilities = AudioCapability.NONE

    def __init__(self) -> None:
        self.started: list[str] = []
        self.active: set[SoundHandle] = set()

    def play_sfx(self, clip: AudioClip, *args: Any, **kwargs: Any) -> SoundHandle:
        self.started.append(clip.path)
        sound = new_sound_handle()
        self.active.add(sound)
        return sound

    def is_sound_active(self, sound: SoundHandle) -> bool:
        return sound in self.active

    def stop_music(self, fade_ms: int = 0) -> None:
        pass


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def mixer() -> _Mixer:
    return _Mixer()


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def audio(mixer: _Mixer, clock: _Clock) -> AudioManager:
    return AudioManager(mixer, clock=clock)  # type: ignore[arg-type]


HIT = _Clip("hit.wav")
OTHER = _Clip("other.wav")


def test_an_unlimited_sound_plays_every_time(audio: AudioManager, mixer: _Mixer):
    for _ in range(10):
        assert audio.play_sfx_clip(HIT) is not None
    assert len(mixer.started) == 10


def test_max_voices_caps_copies_playing_together(audio: AudioManager, mixer: _Mixer):
    audio.set_sfx_limit("hit.wav", max_voices=3)
    played = [audio.play_sfx_clip(HIT) for _ in range(5)]
    assert [sound is not None for sound in played] == [True] * 3 + [False] * 2
    assert len(mixer.started) == 3


def test_a_voice_frees_when_its_copy_ends(audio: AudioManager, mixer: _Mixer):
    audio.set_sfx_limit("hit.wav", max_voices=1)
    first = audio.play_sfx_clip(HIT)
    assert first is not None
    assert audio.play_sfx_clip(HIT) is None
    mixer.active.discard(first)
    assert audio.play_sfx_clip(HIT) is not None


def test_min_interval_spaces_starts(audio: AudioManager, clock: _Clock):
    audio.set_sfx_limit("hit.wav", min_interval=0.05)
    assert audio.play_sfx_clip(HIT) is not None
    clock.now += 0.049
    assert audio.play_sfx_clip(HIT) is None
    clock.now += 0.001
    assert audio.play_sfx_clip(HIT) is not None


def test_a_dropped_play_does_not_restart_the_interval(
    audio: AudioManager, clock: _Clock
):
    audio.set_sfx_limit("hit.wav", min_interval=0.1)
    audio.play_sfx_clip(HIT)
    clock.now += 0.06
    assert audio.play_sfx_clip(HIT) is None
    clock.now += 0.04
    assert audio.play_sfx_clip(HIT) is not None


def test_both_limits_apply_together(audio: AudioManager, mixer: _Mixer, clock: _Clock):
    audio.set_sfx_limit("hit.wav", max_voices=2, min_interval=0.01)
    assert audio.play_sfx_clip(HIT) is not None
    assert audio.play_sfx_clip(HIT) is None  # too soon
    clock.now += 0.01
    assert audio.play_sfx_clip(HIT) is not None
    clock.now += 0.01
    assert audio.play_sfx_clip(HIT) is None  # both voices busy
    assert len(mixer.started) == 2


def test_a_limit_is_per_sound(audio: AudioManager, mixer: _Mixer):
    audio.set_sfx_limit("hit.wav", max_voices=1)
    audio.play_sfx_clip(HIT)
    assert audio.play_sfx_clip(HIT) is None
    assert audio.play_sfx_clip(OTHER) is not None
    assert audio.play_sfx_clip(OTHER) is not None


def test_play_sfx_by_path_is_limited_too(mixer: _Mixer, clock: _Clock):
    class _Resources:
        def load(self, path: str, kind: Any) -> AudioClip:
            return _Clip(path)

    audio = AudioManager(mixer, _Resources(), clock=clock)  # type: ignore[arg-type]
    audio.set_sfx_limit("hit.wav", max_voices=1)
    assert audio.play_sfx("hit.wav") is not None
    assert audio.play_sfx("hit.wav") is None


def test_a_failed_start_takes_no_voice(audio: AudioManager, mixer: _Mixer):
    audio.set_sfx_limit("hit.wav", max_voices=1, min_interval=1.0)
    real = mixer.play_sfx
    mixer.play_sfx = lambda *a, **k: None  # type: ignore[method-assign]
    assert audio.play_sfx_clip(HIT) is None
    mixer.play_sfx = real  # type: ignore[method-assign]
    assert audio.play_sfx_clip(HIT) is not None


def test_default_arguments_remove_the_limit(audio: AudioManager, mixer: _Mixer):
    audio.set_sfx_limit("hit.wav", max_voices=1)
    assert audio.get_sfx_limit("hit.wav") == SfxLimit(1, 0.0)
    audio.play_sfx_clip(HIT)
    audio.set_sfx_limit("hit.wav")
    assert audio.get_sfx_limit("hit.wav") is None
    assert audio.play_sfx_clip(HIT) is not None
    assert audio.play_sfx_clip(HIT) is not None


def test_setting_a_limit_again_starts_it_fresh(audio: AudioManager, clock: _Clock):
    audio.set_sfx_limit("hit.wav", max_voices=1, min_interval=10.0)
    audio.play_sfx_clip(HIT)
    audio.set_sfx_limit("hit.wav", max_voices=1, min_interval=10.0)
    assert audio.play_sfx_clip(HIT) is not None


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_voices": 0}, "max_voices must be at least 1"),
        ({"min_interval": -0.1}, "min_interval"),
        ({"min_interval": math.nan}, "min_interval"),
        ({"min_interval": math.inf}, "min_interval"),
    ],
)
def test_nonsense_limits_are_refused(
    audio: AudioManager, kwargs: dict[str, Any], message: str
):
    with pytest.raises(ValueError, match=message):
        audio.set_sfx_limit("hit.wav", **kwargs)


def test_cleanup_forgets_what_was_playing_but_keeps_the_limits(
    audio: AudioManager, clock: _Clock
):
    audio.set_sfx_limit("hit.wav", max_voices=1, min_interval=10.0)
    audio.play_sfx_clip(HIT)
    audio.cleanup()
    assert audio.get_sfx_limit("hit.wav") == SfxLimit(1, 10.0)
    assert audio.play_sfx_clip(HIT) is not None
