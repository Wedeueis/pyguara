"""Crossfades and layered music on the native mixer, measured offline.

The mixer is driven offline, so nothing advances until `render`. Each
track is a pure tone at its own frequency, and how loud each tone is in a
window of the mix is what the tests read.
"""

from __future__ import annotations

import math
import struct
import time
import wave
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from pyguara import native
from pyguara.audio.backends.native.native_audio import NativeAudioSystem
from pyguara.audio.manager import AudioManager
from pyguara.audio.types import AudioCapability

pytestmark = pytest.mark.skipif(
    native.native_module() is None, reason="extension not built"
)

RATE = 44100
AMPLITUDE = 12000 / 32768
LOW, HIGH = 441.0, 882.0


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


@pytest.fixture
def system() -> Iterator[NativeAudioSystem]:
    audio = NativeAudioSystem(frequency=RATE, output="offline")
    yield audio
    audio.shutdown()


@pytest.fixture
def low(tmp_path: Path) -> str:
    return _tone(tmp_path / "low.wav", LOW, 1.0)


@pytest.fixture
def high(tmp_path: Path) -> str:
    return _tone(tmp_path / "high.wav", HIGH, 0.5)


def _render(system: NativeAudioSystem, frames: int) -> np.ndarray:
    raw = system.mixer.render(frames)
    return np.frombuffer(raw, dtype="<f4").reshape(-1, 2)[:, 0].astype(float)


def _level(window: np.ndarray, freq: float) -> float:
    """The amplitude of one frequency in a window, 1 for a full-scale sine."""
    # Whole periods of both tones (100 and 50 samples), so neither leaks
    # into the other's measure.
    window = window[: len(window) // 100 * 100]
    t = np.arange(len(window)) / RATE
    sin = np.dot(window, np.sin(2 * math.pi * freq * t))
    cos = np.dot(window, np.cos(2 * math.pi * freq * t))
    return float(2 * math.hypot(sin, cos) / len(window))


def _decoded(system: NativeAudioSystem) -> None:
    """Wait, without rendering, for every track asked for to finish decoding."""
    for _ in range(500):
        if not system.mixer.music_decoding:
            return
        time.sleep(0.01)
    raise AssertionError("the music never finished decoding")


def _playing(system: NativeAudioSystem, path: str) -> None:
    system.play_music(path, fade_ms=0)
    _decoded(system)


# --------------------------------------------------------------------------- #
# Crossfades                                                                   #
# --------------------------------------------------------------------------- #


def test_a_crossfade_fades_one_track_out_as_the_next_fades_in(
    system: NativeAudioSystem, low: str, high: str
) -> None:
    _playing(system, low)
    _render(system, 4410)

    system.play_music(high, fade_ms=200, crossfade=True)
    _decoded(system)
    start = _render(system, 441)
    _render(system, round(0.19 * RATE))
    end = _render(system, 882)

    assert _level(start, LOW) > 0.9 * AMPLITUDE
    assert _level(start, HIGH) < 0.1 * AMPLITUDE
    assert _level(end, LOW) < 0.02 * AMPLITUDE
    assert _level(end, HIGH) > 0.9 * AMPLITUDE


def test_the_old_track_plays_on_while_the_next_decodes(
    system: NativeAudioSystem, low: str, high: str
) -> None:
    _playing(system, low)
    system.play_music(high, fade_ms=200, crossfade=True)
    # Whether or not the decode has finished, the old track is still heard.
    assert _level(_render(system, 441), LOW) > 0.9 * AMPLITUDE


def test_a_crossfade_to_a_file_that_will_not_decode_keeps_the_old_track(
    system: NativeAudioSystem, low: str, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.ogg"
    bad.write_bytes(b"nope")
    _playing(system, low)
    system.play_music(str(bad), fade_ms=100, crossfade=True)
    _decoded(system)
    _render(system, RATE // 5)
    assert _level(_render(system, 4410), LOW) > 0.9 * AMPLITUDE


def test_without_a_crossfade_the_old_track_stops_at_once(
    system: NativeAudioSystem, low: str, high: str
) -> None:
    _playing(system, low)
    system.play_music(high, fade_ms=0)
    _decoded(system)
    window = _render(system, 882)
    assert _level(window, LOW) < 0.01 * AMPLITUDE
    assert _level(window, HIGH) > 0.9 * AMPLITUDE


# --------------------------------------------------------------------------- #
# Layers                                                                       #
# --------------------------------------------------------------------------- #


def test_layers_start_on_the_same_sample(
    system: NativeAudioSystem, low: str, high: str
) -> None:
    system.play_music_layers([low, high], [1.0, 1.0], fade_ms=0)
    _decoded(system)
    heard = _render(system, 2000)
    t = np.arange(2000) / RATE
    expected = AMPLITUDE * (
        np.sin(2 * math.pi * LOW * t) + np.sin(2 * math.pi * HIGH * t)
    )
    assert np.max(np.abs(heard - expected)) < 1e-3


def test_a_short_layer_is_padded_so_the_loop_stays_in_step(
    system: NativeAudioSystem, low: str, high: str
) -> None:
    system.play_music_layers([low, high], [1.0, 1.0], fade_ms=0)
    _decoded(system)
    first_half = _render(system, RATE // 2)
    second_half = _render(system, RATE // 2)
    after_the_loop = _render(system, 4410)

    assert _level(first_half, HIGH) > 0.9 * AMPLITUDE
    assert _level(second_half, HIGH) < 0.01 * AMPLITUDE, "padded with silence"
    assert _level(second_half, LOW) > 0.9 * AMPLITUDE
    assert _level(after_the_loop, HIGH) > 0.9 * AMPLITUDE, "both wrapped together"


def test_a_layer_starts_at_its_level_and_moves_when_asked(
    system: NativeAudioSystem, low: str, high: str
) -> None:
    system.play_music_layers([low, high], [1.0, 0.0], fade_ms=0)
    _decoded(system)
    assert _level(_render(system, 4410), HIGH) < 0.01 * AMPLITUDE

    system.set_music_layer(1, 0.5, fade_ms=100)
    ramp = _render(system, round(0.1 * RATE))
    settled = _render(system, 4410)

    assert _level(ramp[:441], HIGH) < 0.1 * AMPLITUDE, "it ramps, it does not jump"
    assert _level(settled, HIGH) == pytest.approx(0.5 * AMPLITUDE, rel=0.02)
    assert _level(settled, LOW) == pytest.approx(AMPLITUDE, rel=0.02)


def test_a_level_set_while_decoding_is_where_the_layer_starts(
    system: NativeAudioSystem, low: str, high: str
) -> None:
    system.play_music_layers([low, high], [1.0, 1.0], fade_ms=0)
    system.set_music_layer(1, 0.0, fade_ms=0)
    _decoded(system)
    assert _level(_render(system, 4410), HIGH) < 0.01 * AMPLITUDE


def test_a_layer_the_music_does_not_have_is_refused(
    system: NativeAudioSystem, low: str
) -> None:
    system.play_music_layers([low], [1.0], fade_ms=0)
    with pytest.raises(IndexError, match="no layer 1"):
        system.set_music_layer(1, 0.5)


def test_layers_and_levels_must_match(system: NativeAudioSystem, low: str) -> None:
    with pytest.raises(ValueError, match="as many"):
        system.mixer.play_music_layers_bytes([b"x"], ["a.wav"], [1.0, 1.0])


def test_stopping_fades_every_layer(
    system: NativeAudioSystem, low: str, high: str
) -> None:
    system.play_music_layers([low, high], [1.0, 1.0], fade_ms=0)
    _decoded(system)
    system.stop_music(fade_ms=50)
    _render(system, round(0.06 * RATE))
    assert not system.is_music_playing()
    assert system.mixer.music_layer_count == 0


# --------------------------------------------------------------------------- #
# Through AudioManager                                                         #
# --------------------------------------------------------------------------- #


def test_the_native_backend_offers_interactive_music(system: NativeAudioSystem) -> None:
    assert AudioCapability.INTERACTIVE_MUSIC in system.capabilities


def test_the_manager_plays_layers_and_moves_them(
    system: NativeAudioSystem, low: str, high: str
) -> None:
    audio = AudioManager(system)
    audio.play_music_layers([low, high], [1.0, 0.0], fade_ms=0)
    assert audio.get_music_layers() == (low, high)
    assert audio.get_current_music() == low
    _decoded(system)
    audio.set_music_layer(1, 1.0, fade_ms=0)
    assert _level(_render(system, 4410), HIGH) > 0.9 * AMPLITUDE

    audio.stop_music(fade_ms=0)
    assert audio.get_music_layers() == ()


@pytest.mark.parametrize(
    ("levels", "match"),
    [([1.0], "2 layers"), ([1.0, 1.5], "0 to 1"), ([1.0, math.nan], "0 to 1")],
)
def test_the_manager_refuses_bad_levels(
    system: NativeAudioSystem, low: str, high: str, levels: list[float], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        AudioManager(system).play_music_layers([low, high], levels)


def test_the_manager_refuses_a_layer_out_of_range(
    system: NativeAudioSystem, low: str
) -> None:
    audio = AudioManager(system)
    audio.play_music(low)
    with pytest.raises(IndexError, match="1 layer"):
        audio.set_music_layer(1, 0.5)
    with pytest.raises(ValueError, match="0 to 1"):
        audio.set_music_layer(0, 2.0)
