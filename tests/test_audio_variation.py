"""`AudioManager.set_sfx_variation`: several takes of a sound, each play different."""

from __future__ import annotations

import math
from typing import Any

import pytest

from pyguara.audio import (
    VARIATION_STREAM,
    AudioManager,
    SoundVariation,
    UnsupportedAudioCapability,
)
from pyguara.audio.types import AudioCapability, SoundHandle, new_sound_handle
from pyguara.random.service import RandomService
from pyguara.resources.manager import ResourceManager
from pyguara.resources.types import AudioClip, Resource

STEPS = ("step1.wav", "step2.wav", "step3.wav")


class _Clip(AudioClip):
    @property
    def duration(self) -> float:
        return 1.0

    @property
    def native_handle(self) -> Any:
        return None


class _WavLoader:
    supported_extensions = [".wav"]

    def load(self, path: str) -> Resource:
        return _Clip(path)


class _Mixer:
    """Plays nothing; remembers each start's clip, volume and pitch."""

    def __init__(self, capabilities: AudioCapability = AudioCapability.PITCH) -> None:
        self.capabilities = capabilities
        self.started: list[tuple[str, float, float]] = []

    def play_sfx(
        self, clip: AudioClip, volume: float, loops: int, pitch: float = 1.0, **_: Any
    ) -> SoundHandle:
        self.started.append((clip.path, volume, pitch))
        return new_sound_handle()

    def is_sound_active(self, sound: SoundHandle) -> bool:
        return True

    def stop_music(self, fade_ms: int = 0) -> None:
        pass


def _audio(mixer: _Mixer, random: RandomService | None = None) -> AudioManager:
    resources = ResourceManager()
    resources.register_loader(_WavLoader())
    return AudioManager(mixer, resources, random=random)  # type: ignore[arg-type]


@pytest.fixture
def mixer() -> _Mixer:
    return _Mixer()


def test_each_play_is_one_of_the_takes_within_the_ranges(mixer: _Mixer) -> None:
    audio = _audio(mixer)
    audio.set_sfx_variation(
        "step", SoundVariation(STEPS, pitch=(0.9, 1.1), volume=(0.5, 0.8))
    )
    for _ in range(200):
        assert audio.play_sfx_variation("step", volume=0.5) is not None

    assert {path for path, _, _ in mixer.started} == set(STEPS)
    assert all(0.25 <= volume <= 0.4 for _, volume, _ in mixer.started)
    assert all(0.9 <= pitch <= 1.1 for _, _, pitch in mixer.started)
    assert len({pitch for _, _, pitch in mixer.started}) > 100, "pitch is not fixed"


def test_no_take_plays_twice_in_a_row(mixer: _Mixer) -> None:
    audio = _audio(mixer)
    audio.set_sfx_variation("step", SoundVariation(STEPS))
    for _ in range(300):
        audio.play_sfx_variation("step")
    paths = [path for path, _, _ in mixer.started]
    assert all(a != b for a, b in zip(paths, paths[1:], strict=False))
    assert set(paths) == set(STEPS)


def test_repeats_are_allowed_when_asked_for(mixer: _Mixer) -> None:
    audio = _audio(mixer)
    audio.set_sfx_variation("step", SoundVariation(STEPS, avoid_repeat=False))
    for _ in range(300):
        audio.play_sfx_variation("step")
    paths = [path for path, _, _ in mixer.started]
    assert any(a == b for a, b in zip(paths, paths[1:], strict=False))


def test_one_take_plays_every_time(mixer: _Mixer) -> None:
    audio = _audio(mixer)
    audio.set_sfx_variation("hit", SoundVariation(("hit.wav",)))
    for _ in range(3):
        audio.play_sfx_variation("hit")
    assert mixer.started == [("hit.wav", 1.0, 1.0)] * 3


def test_picks_come_from_their_own_stream_and_repeat_with_the_seed() -> None:
    def run(seed: int) -> tuple[list[tuple[str, float, float]], float]:
        random = RandomService(root_seed=seed)
        gameplay = random.stream("gameplay")
        mixer = _Mixer()
        audio = _audio(mixer, random)
        audio.set_sfx_variation("step", SoundVariation(STEPS, pitch=(0.8, 1.2)))
        for _ in range(20):
            audio.play_sfx_variation("step")
        return mixer.started, gameplay.random()

    first, gameplay_draw = run(7)
    assert run(7) == (first, gameplay_draw)
    assert run(8)[0] != first
    # The gameplay stream draws what it would have with no sound played.
    assert gameplay_draw == RandomService(root_seed=7).stream("gameplay").random()


def test_picks_are_drawn_from_the_variation_stream(mixer: _Mixer) -> None:
    random = RandomService(root_seed=3)
    audio = _audio(mixer, random)
    audio.set_sfx_variation("step", SoundVariation(STEPS))
    audio.play_sfx_variation("step")
    assert set(random.get_state()["streams"]) == {VARIATION_STREAM}


def test_an_unknown_name_is_refused(mixer: _Mixer) -> None:
    with pytest.raises(KeyError, match="footstep"):
        _audio(mixer).play_sfx_variation("footstep")


def test_a_variation_can_be_removed(mixer: _Mixer) -> None:
    audio = _audio(mixer)
    audio.set_sfx_variation("step", SoundVariation(STEPS))
    assert audio.get_sfx_variation("step") == SoundVariation(STEPS)
    audio.set_sfx_variation("step", None)
    assert audio.get_sfx_variation("step") is None


def test_varying_pitch_on_a_backend_that_cannot_is_refused_when_set() -> None:
    audio = _audio(_Mixer(AudioCapability.NONE))
    with pytest.raises(UnsupportedAudioCapability):
        audio.set_sfx_variation("step", SoundVariation(STEPS, pitch=(0.9, 1.1)))
    audio.set_sfx_variation("step", SoundVariation(STEPS, volume=(0.5, 1.0)))


def test_a_limit_on_a_take_holds_back_only_that_take(mixer: _Mixer) -> None:
    audio = _audio(mixer)
    audio.set_sfx_variation("step", SoundVariation(STEPS[:2], avoid_repeat=False))
    audio.set_sfx_limit(STEPS[0], max_voices=1)
    for _ in range(50):
        audio.play_sfx_variation("step")
    paths = [path for path, _, _ in mixer.started]
    assert paths.count(STEPS[0]) == 1
    assert paths.count(STEPS[1]) > 10


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"paths": ()}, "at least one path"),
        ({"paths": "step.wav"}, "tuple"),
        ({"paths": STEPS, "pitch": (1.2, 0.8)}, "pitch"),
        ({"paths": STEPS, "pitch": (0.0, 1.0)}, "above 0"),
        ({"paths": STEPS, "volume": (0.5, 1.5)}, "0 to 1"),
        ({"paths": STEPS, "volume": (-0.1, 1.0)}, "0 to 1"),
        ({"paths": STEPS, "pitch": (math.nan, 1.0)}, "finite"),
    ],
)
def test_a_bad_variation_is_refused(kwargs: dict[str, Any], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        SoundVariation(**kwargs)


def test_the_application_draws_variations_from_its_random_service() -> None:
    from pyguara.application.bootstrap import create_headless_application

    container = create_headless_application().container
    random = container.get(RandomService)
    audio = container.get(AudioManager)
    assert audio._variation_random is random.stream(VARIATION_STREAM)
