"""What a pitched sound costs: the acceptance numbers for the native backend.

Pitch variation runs on the most frequently played sounds in a game, so the
first play of a pitch has to fit inside a frame without anyone budgeting for it.
"""

from __future__ import annotations

import math
import struct
import wave
from collections.abc import Iterator
from pathlib import Path

import pygame
import pytest

from pyguara.audio.backends.native.loaders import NativeSoundLoader
from pyguara.audio.backends.native.native_audio import NativeAudioSystem
from tests.performance.conftest import measure

pytest.importorskip("pyguara.pyguara_core_rs")


@pytest.fixture
def system() -> Iterator[NativeAudioSystem]:
    if pygame.mixer.get_init() is not None:
        pygame.mixer.quit()
    audio = NativeAudioSystem()
    yield audio
    audio.shutdown()


def _half_second_clip(path: Path) -> Path:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(44100)
        out.writeframes(
            b"".join(
                struct.pack("<h", round(9000 * math.sin(i / 20))) for i in range(22050)
            )
        )
    return path


@pytest.mark.performance
def test_a_first_play_at_a_new_pitch_fits_in_a_frame(
    system: NativeAudioSystem, tmp_path: Path
) -> None:
    """Measured at 0.40 ms; the bound is a quarter of a frame at 60 Hz."""
    clip = NativeSoundLoader().load(str(_half_second_clip(tmp_path / "t.wav")))

    def first_play() -> None:
        system._cache.clear()
        system._cached_bytes = 0
        system._pitched(clip, 1.2)

    assert measure(first_play) < 0.004


@pytest.mark.performance
def test_a_cached_pitch_is_two_orders_cheaper(
    system: NativeAudioSystem, tmp_path: Path
) -> None:
    """A ratio, so it holds on any machine: this is what the 1% step buys."""
    clip = NativeSoundLoader().load(str(_half_second_clip(tmp_path / "t.wav")))

    def first_play() -> None:
        system._cache.clear()
        system._cached_bytes = 0
        system._pitched(clip, 1.2)

    miss = measure(first_play)
    hit = measure(lambda: system._pitched(clip, 1.2))

    assert hit < miss / 100
