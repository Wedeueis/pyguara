"""Does a sample actually come out? -- the audio path, measured.

`test_audio_backend.py` next door asserts the audio *API*: a handle comes
back, volumes clamp, the mixer reports itself initialised. None of it would
notice a backend that returned a handle and played nothing, because the
dummy audio driver discards every sample it is given.

These tests use SDL's `disk` driver instead, which writes the mixed output
to a file, and assert on the samples. They are the audio half of what
`tests/integration/test_demos_render.py` does for frames: a rendered frame
that is a single flat colour and an audio capture that is pure silence are
the same failure, and both pass every API-level assertion.

The seam test pins an assumption a design decision rests on. W28b's staging
(issue #72) puts `LOOP_POINTS` on the existing pygame output path because
`Channel.queue` starts the queued sound on the next *sample*, not the next
buffer boundary. That is SDL's behaviour, not a documented pyguara contract,
so a pygame-ce or SDL upgrade could take it away -- and would do so
silently, as an 11-23 ms hole in every loop. This test is the alarm.
"""

from __future__ import annotations

import math
import os
import struct
import wave
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tools.audio_capture import (
    RATE,
    SEAM_AMPLITUDE,
    SEAM_FREQ,
    SEAM_PERIODS,
    capture_asset,
    capture_tone_loop,
    compare_with_sine,
    read_capture,
    use_disk_driver,
)

pytestmark = pytest.mark.integration


def _has_extension() -> bool:
    from pyguara import native

    try:
        native.require_extension("this test")
    except RuntimeError:
        return False
    return True


@pytest.fixture
def audio_env() -> Iterator[None]:
    """Keep the disk driver inside one test.

    `use_disk_driver` writes to `os.environ` directly, so `monkeypatch`
    cannot undo it -- the variables are snapshotted and restored here
    instead. Without that, a later module initialising the mixer would open
    the disk driver and scatter raw captures through the working directory.
    """
    import pygame

    saved = {
        name: os.environ.get(name)
        for name in ("SDL_AUDIODRIVER", "SDL_DISKAUDIOFILE", "SDL_VIDEODRIVER")
    }
    if pygame.mixer.get_init() is not None:
        pygame.mixer.quit()
    try:
        yield
    finally:
        if pygame.mixer.get_init() is not None:
            pygame.mixer.quit()
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _write_wav(path: Path, seconds: float = 0.25, freq: float = 440.0) -> Path:
    """Write a real WAV file of a plain tone, for the loader to open."""
    frames = int(RATE * seconds)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(
            b"".join(
                struct.pack("<hh", sample, sample)
                for sample in (
                    int(12000 * math.sin(2 * math.pi * freq * i / RATE))
                    for i in range(frames)
                )
            )
        )
    return path


def test_engine_audio_path_emits_sound(audio_env: None, tmp_path: Path) -> None:
    """A clip played through the engine reaches the output as signal."""
    asset = _write_wav(tmp_path / "tone.wav")
    capture = capture_asset(asset, tmp_path / "tone.raw")

    assert not capture.is_silent, "the audio path produced nothing but silence"
    assert capture.peak > 1000, f"peak {capture.peak} is too quiet to be the tone"
    assert capture.rms > 100, f"rms {capture.rms} suggests near-silence"
    assert capture.duration > 0.2, "capture is shorter than the clip"


def test_a_silent_capture_is_reported_as_silent(tmp_path: Path) -> None:
    """The control: the check above can fail.

    A capture of nothing must come back `is_silent`, or
    `test_engine_audio_path_emits_sound` is an assertion that cannot fire.
    """
    silent = tmp_path / "silence.raw"
    silent.write_bytes(np.zeros(4096, dtype=np.int16).tobytes())

    capture = read_capture(silent)

    assert capture.is_silent
    assert capture.peak == 0


def test_queued_loop_is_sample_contiguous(audio_env: None, tmp_path: Path) -> None:
    """`Channel.queue` joins segments with no gap and no dropped sample."""
    capture, seam = capture_tone_loop(tmp_path / "seam.raw", laps=3)

    assert not capture.is_silent
    assert capture.interior_silence == [], (
        f"silence inside a continuous loop: {capture.interior_silence}"
    )
    assert seam.contiguous, (
        f"loop seam is not sample-exact: max |delta| {seam.max_delta} "
        f"of amplitude {SEAM_AMPLITUDE}, per seam {seam.seam_deltas}"
    )


def test_the_seam_check_catches_a_dropped_sample(tmp_path: Path) -> None:
    """The control: a phase jump with no silence must still be caught.

    Deleting frames from the middle of the tone leaves no zeros behind, so
    `interior_silence` stays empty and only the comparison against an
    unbroken sine can see it. Without this, a seam test that always passes
    looks exactly like a seam that always works.
    """
    segment_frames = int(RATE / SEAM_FREQ * SEAM_PERIODS)
    laps = 3
    t = np.arange(segment_frames * laps + 50) / RATE
    tone = (SEAM_AMPLITUDE * np.sin(2 * math.pi * SEAM_FREQ * t)).astype(np.int16)
    spliced = np.delete(tone, slice(segment_frames, segment_frames + 50))
    stereo = np.column_stack([spliced, spliced]).copy()

    path = tmp_path / "dropped.raw"
    path.write_bytes(stereo.tobytes())

    assert read_capture(path).interior_silence == [], "the splice left silence"
    assert not compare_with_sine(path, laps, segment_frames).contiguous


def _write_seam_tone(path: Path, periods: int) -> Path:
    """Write the phase-aligned tone, mono, for the engine's loader to read."""
    frames = round(RATE / SEAM_FREQ * periods)
    t = np.arange(frames) / RATE
    tone = (SEAM_AMPLITUDE * np.sin(2 * math.pi * SEAM_FREQ * t)).astype(np.int16)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(tone.tobytes())
    return path


def _capture_native(output: Path, play: Callable[[Any, Any], Any]) -> None:
    """Run `play(system, clip)` on the native backend until it falls silent."""
    use_disk_driver(output)
    import pygame

    from pyguara.audio.backends.native.native_audio import NativeAudioSystem

    if pygame.mixer.get_init() is not None:
        pygame.mixer.quit()
    system = NativeAudioSystem(frequency=RATE)
    handle = play(system, None)
    while system.is_sound_active(handle):
        system.update()
        pygame.time.wait(5)
    pygame.time.wait(60)
    system.shutdown()


@pytest.mark.skipif(not _has_extension(), reason="extension not built")
class TestTheNativeBackendReachesTheOutput:
    """Decode to speaker with no device, against the same detector as above."""

    def test_a_loop_between_two_points_has_no_seam(
        self, audio_env: None, tmp_path: Path
    ) -> None:
        """The region starts inside the clip, so one frame out is a jump."""
        from pyguara.audio.backends.native.loaders import NativeSoundLoader

        source = _write_seam_tone(tmp_path / "tone.wav", SEAM_PERIODS)
        output = tmp_path / "loop.raw"
        start_periods = SEAM_PERIODS // 4
        lap_frames = round(RATE / SEAM_FREQ * (SEAM_PERIODS - start_periods))
        duration = SEAM_PERIODS / SEAM_FREQ
        laps = 3

        def play(system: Any, _clip: Any) -> Any:
            clip = NativeSoundLoader().load(str(source))
            return system.play_sfx(
                clip,
                loops=laps,
                loop_start=start_periods / SEAM_FREQ,
                loop_end=duration,
            )

        _capture_native(output, play)

        total_frames = round(RATE * duration) + lap_frames * laps
        check = compare_with_sine(output, 1, total_frames)
        capture = read_capture(output)
        assert capture.interior_silence == []
        assert check.max_delta <= 1, check.report()

    def test_a_pitched_sound_comes_out_at_the_new_frequency(
        self, audio_env: None, tmp_path: Path
    ) -> None:
        from pyguara.audio.backends.native.loaders import NativeSoundLoader

        source = _write_seam_tone(tmp_path / "tone.wav", SEAM_PERIODS)
        output = tmp_path / "pitched.raw"

        def play(system: Any, _clip: Any) -> Any:
            clip = NativeSoundLoader().load(str(source))
            return system.play_sfx(clip, pitch=2.0)

        _capture_native(output, play)

        mono = np.frombuffer(output.read_bytes(), dtype="<i2")[::2].astype(float)
        sounding = mono[np.flatnonzero(mono)[0] : np.flatnonzero(mono)[-1] + 1]
        spectrum = np.abs(np.fft.rfft(sounding * np.hanning(len(sounding))))
        peak = float(np.fft.rfftfreq(len(sounding), 1 / RATE)[int(np.argmax(spectrum))])
        assert peak == pytest.approx(SEAM_FREQ * 2, abs=6)
        assert len(sounding) == pytest.approx(
            RATE / SEAM_FREQ * SEAM_PERIODS / 2, abs=4
        )
