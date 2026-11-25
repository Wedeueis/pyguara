"""Does a sample actually come out? -- the audio path, measured.

`test_audio_backend.py` asserts the audio API under the dummy driver,
which discards every sample. These tests use SDL's `disk` driver,
which writes the mixed output to a file, and assert on the samples.

The seam test pins SDL behaviour that loop points on the pygame path
depend on: `Channel.queue` starts the queued sound on the next sample,
not the next buffer boundary. An SDL or pygame-ce upgrade that changed
it would put a gap in every loop.
"""

from __future__ import annotations

import math
import os
import struct
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tools.audio_capture import (
    IDLE_POLLS,
    RATE,
    SEAM_AMPLITUDE,
    SEAM_FREQ,
    SEAM_PERIODS,
    SeamCheck,
    _left_channel,
    capture_asset,
    capture_native,
    capture_tone_loop,
    compare_with_sine,
    read_capture,
    wait_until_idle,
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


def test_gap_evidence_tells_dropped_from_inserted(tmp_path: Path) -> None:
    """The control for `_gap_evidence`: both kinds of gap, told apart."""
    tone = (
        SEAM_AMPLITUDE * np.sin(2 * math.pi * SEAM_FREQ * np.arange(4000) / RATE)
    ).astype(np.int16)
    silence = np.zeros(512, dtype=np.int16)
    seam = SeamCheck(3, 0, 0, 0, [])
    cases = {
        "dropped": np.concatenate([tone[:53], silence, tone[565:]]),
        "inserted": np.concatenate([tone[:53], silence, tone[53:]]),
    }
    reports = {}
    for name, mono in cases.items():
        path = tmp_path / f"{name}.raw"
        path.write_bytes(np.column_stack([mono, mono]).tobytes())
        gaps = read_capture(path).interior_silence
        assert [length for _, length in gaps] == [512]
        reports[name] = _gap_evidence(path, gaps, seam)

    assert "shifted by [0] frames" in reports["dropped"]
    assert "shifted by [12] frames" in reports["inserted"]
    assert "52 sounding frames before it" in reports["dropped"]


@pytest.mark.parametrize("stray_bytes", [1, 2, 3])
def test_a_capture_cut_inside_a_frame_reads_its_whole_frames(
    tmp_path: Path, stray_bytes: int
) -> None:
    """The disk driver can be closed partway through a frame.

    The file then is not a whole number of frames, and its tail is not a
    sample. Reading it must give every whole frame and nothing else.
    """
    frames = np.full(2048, 1200, dtype=np.int16)
    cut = tmp_path / "cut.raw"
    cut.write_bytes(frames.tobytes() + b"\x7f" * stray_bytes)

    capture = read_capture(cut)

    assert capture.samples == 1024
    assert capture.peak == 1200


def _gap_evidence(path: Path, gaps: list[tuple[int, int]], seam: SeamCheck) -> str:
    """Describe a gap well enough to tell a dropped buffer from a late one.

    The tone has a 100-frame period. If it resumes after the gap in the
    phase an unbroken sine would have, samples were replaced by silence;
    shifted by the gap's length, silence was inserted. Also prints what
    came before the gap, which may not be the tone at all.
    """
    mono = _left_channel(path)
    lines = [f"seam: offset {seam.phase_offset}, max |delta| {seam.max_delta}"]
    first = int(np.flatnonzero(mono != 0)[0])
    for start, length in gaps[:3]:
        before = mono[first:start]
        lines.append(
            f"gap {start}+{length}: {len(before)} sounding frames before it, "
            f"peak {int(np.abs(before).max()) if len(before) else 0}, "
            f"head {mono[first : min(start, first + 16)].tolist()}"
        )
        end = start + length
        after = mono[end : end + 300]
        phases = [
            shift
            for shift in range(100)
            if np.abs(
                after
                - SEAM_AMPLITUDE
                * np.sin(
                    2
                    * math.pi
                    * SEAM_FREQ
                    * (np.arange(len(after)) + end - shift)
                    / RATE
                )
            ).max()
            <= 2
        ]
        lines.append(f"  resumes at sine phase shifted by {phases} frames (mod 100)")
    return "\n".join(lines)


def test_queued_loop_is_sample_contiguous(audio_env: None, tmp_path: Path) -> None:
    """`Channel.queue` joins segments with no gap and no dropped sample."""
    capture, seam = capture_tone_loop(tmp_path / "seam.raw", laps=3)

    assert not capture.is_silent
    assert capture.interior_silence == [], (
        f"silence inside a continuous loop: {capture.interior_silence}\n"
        + _gap_evidence(tmp_path / "seam.raw", capture.interior_silence, seam)
    )
    assert seam.contiguous, (
        f"loop seam is not sample-exact: max |delta| {seam.max_delta} "
        f"of amplitude {SEAM_AMPLITUDE}, per seam {seam.seam_deltas}"
    )


class _FlickeringChannel:
    """A channel that reads idle for one poll between two sounds."""

    def __init__(self, readings: list[bool]) -> None:
        self._readings = readings
        self.polls = 0

    def get_busy(self) -> bool:
        busy = self._readings[self.polls] if self.polls < len(self._readings) else False
        self.polls += 1
        return busy


def test_one_idle_reading_between_laps_does_not_end_the_wait() -> None:
    """A channel reads idle until the mixer thread starts the queued sound.

    A wait that believed the first idle reading ended the capture a lap
    early, with no silence in it to show for it.
    """
    channel = _FlickeringChannel([True, False, True, True, False, True])

    wait_until_idle(channel)

    assert channel.polls == 6 + IDLE_POLLS


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


@pytest.mark.skipif(not _has_extension(), reason="extension not built")
class TestTheNativeBackendReachesTheOutput:
    """Decode to mix with no device, against the same detector as above.

    Through the mixer's offline render (`capture_native`): the native
    backend owns its device, so SDL's `disk` driver never sees it.
    """

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

        def play(system: Any) -> Any:
            clip = NativeSoundLoader(system.mixer).load(str(source))
            return system.play_sfx(
                clip,
                loops=laps,
                loop_start=start_periods / SEAM_FREQ,
                loop_end=duration,
            )

        capture_native(output, play)

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

        def play(system: Any) -> Any:
            clip = NativeSoundLoader(system.mixer).load(str(source))
            return system.play_sfx(clip, pitch=2.0)

        capture_native(output, play)

        mono = np.frombuffer(output.read_bytes(), dtype="<i2")[::2].astype(float)
        sounding = mono[np.flatnonzero(mono)[0] : np.flatnonzero(mono)[-1] + 1]
        spectrum = np.abs(np.fft.rfft(sounding * np.hanning(len(sounding))))
        peak = float(np.fft.rfftfreq(len(sounding), 1 / RATE)[int(np.argmax(spectrum))])
        assert peak == pytest.approx(SEAM_FREQ * 2, abs=6)
        assert len(sounding) == pytest.approx(
            RATE / SEAM_FREQ * SEAM_PERIODS / 2, abs=4
        )
