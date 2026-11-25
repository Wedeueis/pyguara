"""The music dips under a chosen sound and comes back after it, measured offline.

The music is a low tone and the sound a high one, so how loud each is in a
window of the mix says what the duck did to the music and not to the sound.
"""

from __future__ import annotations

import math
import struct
import time
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from pyguara import native
from pyguara.audio import SfxDucking, UnsupportedAudioCapability
from pyguara.audio.backends.native.loaders import NativeSoundLoader
from pyguara.audio.backends.native.native_audio import NativeAudioSystem
from pyguara.audio.manager import AudioManager
from pyguara.audio.types import AudioCapability
from pyguara.resources.manager import ResourceManager

pytestmark = pytest.mark.skipif(
    native.native_module() is None, reason="extension not built"
)

RATE = 44100
AMPLITUDE = 12000 / 32768
MUSIC, ROAR = 441.0, 882.0


def _tone(path: Path, freq: float, seconds: float) -> str:
    count = int(seconds * RATE)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(
            b"".join(
                struct.pack(
                    "<h", round(12000 * math.sin(2 * math.pi * freq * i / RATE))
                )
                for i in range(count)
            )
        )
    return str(path)


def _level(window: np.ndarray, freq: float) -> float:
    """The amplitude of one frequency in a window, over whole periods."""
    window = window[: len(window) // 100 * 100]
    t = np.arange(len(window)) / RATE
    sin = np.dot(window, np.sin(2 * math.pi * freq * t))
    cos = np.dot(window, np.cos(2 * math.pi * freq * t))
    return float(2 * math.hypot(sin, cos) / len(window))


@pytest.fixture
def system(tmp_path: Path) -> Iterator[NativeAudioSystem]:
    audio = NativeAudioSystem(frequency=RATE, output="offline")
    audio.play_music(_tone(tmp_path / "music.wav", MUSIC, 1.0), fade_ms=0)
    for _ in range(500):
        if not audio.mixer.music_decoding:
            break
        time.sleep(0.01)
    yield audio
    audio.shutdown()


@pytest.fixture
def roar(system: NativeAudioSystem, tmp_path: Path) -> Any:
    return NativeSoundLoader(system.mixer).load(_tone(tmp_path / "roar.wav", ROAR, 0.2))


def _render(system: NativeAudioSystem, seconds: float) -> np.ndarray:
    raw = system.mixer.render(round(seconds * RATE))
    return np.frombuffer(raw, dtype="<f4").reshape(-1, 2)[:, 0].astype(float)


def test_the_music_dips_under_the_sound_and_comes_back(
    system: NativeAudioSystem, roar: Any
) -> None:
    system.play_sfx(roar)
    unducked = _level(_render(system, 0.1), ROAR)
    _render(system, 0.15)

    sound = system.play_sfx(roar)
    system.duck_music(sound, 0.75, attack_ms=20, release_ms=100)

    attack = _render(system, 0.02)
    during = _render(system, 0.1)
    _render(system, 0.08)  # the rest of the roar
    _render(system, 0.1)  # the release
    after = _render(system, 0.1)

    assert _level(attack[:400], MUSIC) > 0.8 * AMPLITUDE, "a ramp, not a step"
    assert _level(during, MUSIC) == pytest.approx(0.25 * AMPLITUDE, rel=0.03)
    assert _level(during, ROAR) == pytest.approx(unducked, rel=0.01), "not ducked"
    assert _level(after, MUSIC) == pytest.approx(AMPLITUDE, rel=0.03)
    assert system.mixer.music_duck == 0.0


def test_the_deepest_duck_wins(system: NativeAudioSystem, roar: Any) -> None:
    system.duck_music(system.play_sfx(roar), 0.25, attack_ms=0)
    system.duck_music(system.play_sfx(roar), 0.5, attack_ms=0)
    _render(system, 0.01)
    assert system.mixer.music_duck == pytest.approx(0.5)


def test_a_sound_that_has_ended_ducks_nothing(
    system: NativeAudioSystem, roar: Any
) -> None:
    sound = system.play_sfx(roar)
    _render(system, 0.25)
    system.duck_music(sound, 1.0, attack_ms=0)
    assert _level(_render(system, 0.05), MUSIC) > 0.95 * AMPLITUDE


def test_a_depth_outside_0_to_1_is_refused(
    system: NativeAudioSystem, roar: Any
) -> None:
    sound = system.play_sfx(roar)
    for depth in (-0.1, 1.5, math.nan):
        with pytest.raises(ValueError, match="0 to 1"):
            system.duck_music(sound, depth)


def test_the_native_backend_offers_ducking(system: NativeAudioSystem) -> None:
    assert AudioCapability.DUCKING in system.capabilities


# --------------------------------------------------------------------------- #
# Through AudioManager                                                         #
# --------------------------------------------------------------------------- #


def test_a_sound_set_to_duck_dips_the_music_each_time_it_plays(
    system: NativeAudioSystem, tmp_path: Path
) -> None:
    resources = ResourceManager()
    resources.register_loader(NativeSoundLoader(system.mixer))
    audio = AudioManager(system, resources)
    path = _tone(tmp_path / "boss.wav", ROAR, 0.2)
    audio.set_sfx_ducking(path, 0.5, attack_ms=0, release_ms=0)
    assert audio.get_sfx_ducking(path) == SfxDucking(0.5, 0, 0)

    audio.play_sfx(path)
    assert _level(_render(system, 0.1), MUSIC) == pytest.approx(
        0.5 * AMPLITUDE, rel=0.03
    )

    audio.set_sfx_ducking(path, None)
    _render(system, 0.2)
    audio.play_sfx(path)
    assert _level(_render(system, 0.1), MUSIC) > 0.95 * AMPLITUDE


def test_the_manager_refuses_bad_settings(system: NativeAudioSystem) -> None:
    audio = AudioManager(system)
    with pytest.raises(ValueError, match="0 to 1"):
        audio.set_sfx_ducking("boss.wav", 1.2)
    with pytest.raises(ValueError, match="at least 0"):
        audio.set_sfx_ducking("boss.wav", 0.5, release_ms=-1)


def test_ducking_on_a_backend_without_it_is_refused_when_set() -> None:
    class _Plain:
        capabilities = AudioCapability.NONE

    audio = AudioManager(_Plain())  # type: ignore[arg-type]
    with pytest.raises(UnsupportedAudioCapability):
        audio.set_sfx_ducking("boss.wav", 0.5)
