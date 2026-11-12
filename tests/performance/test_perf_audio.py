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

import pytest

from pyguara.audio.backends.native.loaders import NativeSoundLoader
from pyguara.audio.backends.native.native_audio import NativeAudioSystem
from tests.performance.conftest import measure

pytest.importorskip("pyguara.pyguara_core_rs")


@pytest.fixture
def system() -> Iterator[NativeAudioSystem]:
    audio = NativeAudioSystem(output="offline")
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
def test_a_pitched_play_costs_no_render(
    system: NativeAudioSystem, tmp_path: Path
) -> None:
    """Pitch is a step size in the mixer: starting a voice copies nothing.

    The old backend rendered a buffer per new pitch, 0.40 ms. Bounded at
    0.2 ms, where a render of half a second would be well over.
    """
    clip = NativeSoundLoader(system.mixer).load(
        str(_half_second_clip(tmp_path / "t.wav"))
    )

    def play_and_stop() -> None:
        handle = system.play_sfx(clip, pitch=1.2345)
        assert handle is not None
        system.stop_sfx(handle)

    assert measure(play_and_stop) < 0.0002


@pytest.mark.performance
def test_mixing_a_frame_of_32_voices_fits_easily(
    system: NativeAudioSystem, tmp_path: Path
) -> None:
    """What the audio thread does per 60 Hz frame, at the voice limit.

    A sixtieth of a second at 44.1 kHz is 735 frames; bounded at 1 ms, a
    sixteenth of the frame, though the audio thread is not the game's.
    """
    clip = NativeSoundLoader(system.mixer).load(
        str(_half_second_clip(tmp_path / "t.wav"))
    )
    for index in range(32):
        system.play_sfx(clip, loops=-1, pitch=0.5 + index / 32)

    assert measure(lambda: system.mixer.render(735)) < 0.001
