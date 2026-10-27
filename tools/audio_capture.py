#!/usr/bin/env python
"""Capture what the engine plays, so an agent can check the audio path.

An agent working on this engine cannot listen to a speaker. SDL's `disk`
audio driver writes the mixed output stream to a file instead of handing it
to a device, so what the mixer produced can be measured the way
`tools/agent_view.py` measures frames.

    uv run python tools/audio_capture.py --asset games/quintal_cerrado/assets/audio/seed.wav
    uv run python tools/audio_capture.py --asset <path> --wav
    uv run python tools/audio_capture.py --seam --laps 5

What this proves, and what it does not:

    It reads the samples the mixer wrote. That proves the *output path*
    works -- the clip decoded, the bus volumes applied, the channel mixed,
    and something other than silence came out the far end.

    It does NOT prove a sound is audible on a real device. A capture cannot
    hear an ALSA underrun, a muted system mixer, or a device opened at a
    sample rate the hardware resamples badly. The same split as
    `agent_view.py`: the path is verifiable headlessly, the hardware is not.

Captures are checked for being wholly silent and flagged, because a silent
capture is the most common way this tells you nothing -- the exact analogue
of `agent_view.py`'s flat-colour check.

`--seam` is the loop-continuity measurement that settled W28b's staging (see
the decision record on issue #72). It loops a phase-aligned tone through
`Channel.queue` and compares the capture against one unbroken sine, so a
dropped or duplicated sample shows up as a phase jump even though no silence
was inserted.
"""

from __future__ import annotations

import argparse
import os
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RATE = 44100
"""Capture sample rate. The mixer is opened at this rate, so it is also the
rate of the file the disk driver writes."""

BUFFER = 512
"""Mixer buffer size, in samples. `--seam` reports per buffer size because a
seam landing on a buffer boundary is the failure it looks for."""

SEAM_FREQ = 441.0
"""Exactly 100 samples per period at 44.1 kHz, so a whole number of periods
is also a whole number of samples."""

SEAM_PERIODS = 220
"""Periods per looped segment: 22000 samples, just under half a second. The
segment ends on a period boundary, so a perfect loop is one unbroken sine."""

SEAM_AMPLITUDE = 12000
"""Tone amplitude, well short of int16 clipping so a discontinuity cannot be
hidden by saturation."""

SILENCE_RUN = 32
"""Shortest run of exact zeros reported as a gap. A tone crosses zero every
period, so a handful of zero samples is signal, not silence."""


def use_disk_driver(output: Path) -> None:
    """Point SDL's audio output at a file instead of a device.

    Must be called before the mixer is initialised -- SDL reads the driver
    name when the audio subsystem starts, so setting it afterwards silently
    has no effect and the capture comes back empty.

    Args:
        output: Path the raw interleaved stream is written to.
    """
    os.environ["SDL_AUDIODRIVER"] = "disk"
    os.environ["SDL_DISKAUDIOFILE"] = str(output)
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")


@dataclass(frozen=True, slots=True)
class Capture:
    """One captured output stream, summarised.

    Attributes:
        samples: Frames captured, per channel.
        rate: Sample rate the mixer was opened at.
        peak: Largest absolute sample value, of 32767.
        rms: Root mean square of the whole capture, in the same units.
        leading_silence: Silent frames before the first sample, which is the
            device being open before anything plays and is expected.
        trailing_silence: Silent frames after the last sample.
        interior_silence: `(start, length)` for every silent run of at least
            `SILENCE_RUN` frames between the two, which is where a dropped
            buffer or a late re-queue shows up.
    """

    samples: int
    rate: int
    peak: int
    rms: float
    leading_silence: int
    trailing_silence: int
    interior_silence: list[tuple[int, int]]

    @property
    def duration(self) -> float:
        """Capture length in seconds."""
        return self.samples / self.rate

    @property
    def is_silent(self) -> bool:
        """Whether nothing at all was written. Treat as a failed capture."""
        return self.peak == 0

    def report(self) -> str:
        """Render the summary as the lines the CLI prints."""
        lines = [
            f"{self.samples} frames ({self.duration:.2f}s at {self.rate} Hz)",
            f"peak {self.peak} of 32767, rms {self.rms:.1f}",
        ]
        if self.is_silent:
            lines.append("SILENT -- the capture carries no signal at all")
        lines.append(
            f"silence: {self.leading_silence} frames leading, "
            f"{self.trailing_silence} trailing"
        )
        if self.interior_silence:
            for start, length in self.interior_silence[:8]:
                lines.append(
                    f"  interior gap at frame {start} ({start / self.rate:.3f}s): "
                    f"{length} frames = {1000 * length / self.rate:.2f} ms"
                )
            lines.append(f"  {len(self.interior_silence)} interior gaps")
        else:
            lines.append("no interior silence")
        return "\n".join(lines)


def _left_channel(path: Path) -> np.ndarray:
    """Read the raw stereo capture and return its left channel."""
    raw = np.frombuffer(path.read_bytes(), dtype=np.int16)
    return np.asarray(raw[::2], dtype=np.int64)


def _silent_runs(mono: np.ndarray, min_length: int) -> list[tuple[int, int]]:
    """Return `(start, length)` for every run of exact zeros."""
    is_zero = mono == 0
    if not bool(is_zero.any()):
        return []
    edges = np.diff(is_zero.astype(np.int8))
    starts = [int(i) + 1 for i in np.flatnonzero(edges == 1)]
    ends = [int(i) + 1 for i in np.flatnonzero(edges == -1)]
    if bool(is_zero[0]):
        starts.insert(0, 0)
    if bool(is_zero[-1]):
        ends.append(len(mono))
    # The two boundary fixups above are what make these the same length,
    # so `strict` is an assertion rather than a formality.
    return [
        (s, e - s) for s, e in zip(starts, ends, strict=True) if e - s >= min_length
    ]


def read_capture(path: Path, rate: int = RATE) -> Capture:
    """Summarise a raw capture written by the disk driver.

    Args:
        path: The file `use_disk_driver` was pointed at.
        rate: Sample rate the mixer was opened at.

    Returns:
        The capture's summary. A `Capture` whose `is_silent` is true means
        the mixer wrote nothing but zeros, which is a failure however the
        calling code looked.
    """
    mono = _left_channel(path)
    if len(mono) == 0:
        return Capture(0, rate, 0, 0.0, 0, 0, [])

    sounding = np.flatnonzero(mono != 0)
    if len(sounding) == 0:
        return Capture(len(mono), rate, 0, 0.0, len(mono), 0, [])

    first, last = int(sounding[0]), int(sounding[-1])
    runs = _silent_runs(mono, SILENCE_RUN)
    interior = [(s, n) for s, n in runs if s > first and s + n <= last]
    return Capture(
        samples=len(mono),
        rate=rate,
        peak=int(np.abs(mono).max()),
        rms=float(np.sqrt(np.mean(mono.astype(np.float64) ** 2))),
        leading_silence=first,
        trailing_silence=len(mono) - 1 - last,
        interior_silence=interior,
    )


def write_wav(raw: Path, destination: Path, rate: int = RATE) -> None:
    """Wrap a raw capture in a WAV header, so it can be played back.

    Args:
        raw: The raw interleaved stereo capture.
        destination: Path to write the WAV file to.
        rate: Sample rate the mixer was opened at.
    """
    with wave.open(str(destination), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(raw.read_bytes())


def capture_asset(asset: Path, output: Path, *, buffer: int = BUFFER) -> Capture:
    """Play one audio asset through the engine's audio system and capture it.

    Goes through `PygameSoundLoader` and `PygameAudioSystem` rather than
    pygame directly, so what is measured is the engine's path -- the loader,
    the bus volumes and the channel allocation included.

    Args:
        asset: Path to a `.wav`, `.ogg` or `.mp3` file.
        output: Path the raw capture is written to.
        buffer: Mixer buffer size, in samples.

    Returns:
        The capture's summary.

    Raises:
        FileNotFoundError: If `asset` does not exist.
    """
    if not asset.is_file():
        raise FileNotFoundError(asset)

    use_disk_driver(output)
    import pygame

    from pyguara.audio.backends.pygame.loaders import PygameSoundLoader
    from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem
    from pyguara.audio.backends.pygame.types import PygameAudioClip

    if pygame.mixer.get_init() is not None:
        pygame.mixer.quit()
    system = PygameAudioSystem(frequency=RATE, buffer=buffer)
    # The loader's return type is the wider `Resource`; narrowing it here
    # beats an ignore, and a loader that stopped returning a clip would be
    # worth hearing about rather than suppressing.
    clip = PygameSoundLoader().load(str(asset))
    assert isinstance(clip, PygameAudioClip), f"not an audio clip: {type(clip)}"
    system.play_sfx(clip)

    # The disk driver writes a buffer per callback and sleeps a buffer's
    # worth between them, so the file fills at roughly real time. Draining
    # the channel is what decides the capture's length.
    while pygame.mixer.get_busy():
        pygame.time.wait(5)
    pygame.mixer.quit()
    return read_capture(output, RATE)


@dataclass(frozen=True, slots=True)
class SeamCheck:
    """How closely a queued loop matched one unbroken sine.

    Attributes:
        laps: Segments played back to back.
        compared: Frames compared against the ideal sine.
        phase_offset: Frames the capture had to be shifted to align. Searched
            rather than assumed -- a sine starts at zero, so taking the first
            non-zero sample as the start lands a sample or two late and
            reports a constant error everywhere.
        max_delta: Largest absolute difference from the ideal, of
            `SEAM_AMPLITUDE`. Zero means every sample landed where an
            unbroken sine would have put it.
        seam_deltas: `max_delta` within 64 frames of each segment boundary.
    """

    laps: int
    compared: int
    phase_offset: int
    max_delta: int
    seam_deltas: list[int]

    @property
    def contiguous(self) -> bool:
        """Whether the loop played with no gap and no dropped sample."""
        return self.max_delta == 0

    def report(self) -> str:
        """Render the comparison as the lines the CLI prints."""
        verdict = "contiguous" if self.contiguous else "BROKEN at the seams"
        seams = ", ".join(str(d) for d in self.seam_deltas) or "none"
        return "\n".join(
            [
                f"{self.laps} laps, {self.compared} frames compared "
                f"(phase offset {self.phase_offset:+d})",
                f"max |delta| {self.max_delta} of amplitude {SEAM_AMPLITUDE}",
                f"per-seam max |delta|: {seams}",
                f"verdict: {verdict}",
            ]
        )


def _tone(periods: int = SEAM_PERIODS) -> np.ndarray:
    """Build a phase-aligned stereo tone of `periods` whole cycles."""
    count = int(RATE / SEAM_FREQ * periods)
    t = np.arange(count) / RATE
    wave_ = (SEAM_AMPLITUDE * np.sin(2 * np.pi * SEAM_FREQ * t)).astype(np.int16)
    return np.column_stack([wave_, wave_]).copy()


def capture_tone_loop(
    output: Path, laps: int = 5, *, buffer: int = BUFFER, stall: float = 0.0
) -> tuple[Capture, SeamCheck]:
    """Loop a phase-aligned tone through `Channel.queue` and measure the seam.

    `Channel.queue` holds exactly one pending sound -- a second `queue()`
    replaces it rather than appending -- so looping means re-queueing from
    Python. The question this answers is whether the queued sound starts on
    the next *sample* or on the next buffer boundary, which would put an
    11-23 ms hole in every lap.

    Args:
        output: Path the raw capture is written to.
        laps: Segments to play back to back.
        buffer: Mixer buffer size, in samples.
        stall: Seconds to block the main thread once, mid-loop. The queue is
            a one-segment lookahead, so a stall shorter than a segment should
            leave no trace.

    Returns:
        The capture's summary and the seam comparison.
    """
    use_disk_driver(output)
    import pygame

    if pygame.mixer.get_init() is not None:
        pygame.mixer.quit()
    pygame.mixer.init(frequency=RATE, size=-16, channels=2, buffer=buffer)
    segment = _tone()
    sound = pygame.mixer.Sound(buffer=segment.tobytes())

    channel = pygame.mixer.Channel(0)
    channel.play(sound)
    channel.queue(sound)
    started, stalled = 2, False
    while started < laps:
        if channel.get_queue() is None:
            channel.queue(sound)
            started += 1
            if stall and not stalled:
                pygame.time.wait(int(stall * 1000))
                stalled = True
        pygame.time.wait(2)
    while channel.get_busy():
        pygame.time.wait(5)
    pygame.mixer.quit()

    return read_capture(output, RATE), compare_with_sine(output, laps, len(segment))


def compare_with_sine(path: Path, laps: int, segment_frames: int) -> SeamCheck:
    """Compare a looped capture against one unbroken sine.

    Public because it is the half that can fail without leaving silence
    behind: a dropped or duplicated sample shifts the phase, which no
    silence check sees. Point it at any capture of `_tone` looped a known
    number of times.

    Args:
        path: A raw capture of the phase-aligned tone, looped.
        laps: Segments the capture is expected to contain.
        segment_frames: Frames in one segment.

    Returns:
        The comparison. `max_delta` of zero means every sample landed
        where an unbroken sine would have put it.
    """
    mono = _left_channel(path)
    sounding = np.flatnonzero(mono != 0)
    first = int(sounding[0]) if len(sounding) else 0
    span = segment_frames * laps
    ideal = (
        SEAM_AMPLITUDE * np.sin(2 * np.pi * SEAM_FREQ * np.arange(span) / RATE)
    ).astype(np.int64)

    best: tuple[np.ndarray, int] | None = None
    for offset in range(-4, int(RATE / SEAM_FREQ) + 1):
        start = first + offset
        if start < 0 or start + span > len(mono):
            continue
        error = np.abs(mono[start : start + span] - ideal)
        if best is None or error.max() < best[0].max():
            best = (error, offset)
    if best is None:
        return SeamCheck(laps, 0, 0, -1, [])

    error, offset = best
    seams = [
        int(error[lap * segment_frames - 64 : lap * segment_frames + 64].max())
        for lap in range(1, laps)
    ]
    return SeamCheck(laps, span, offset, int(error.max()), seams)


def main(argv: list[str] | None = None) -> int:
    """Run the capture named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--asset", type=Path, help="audio file to play and capture")
    parser.add_argument(
        "--seam",
        action="store_true",
        help="loop a tone through Channel.queue and measure the join",
    )
    parser.add_argument("--laps", type=int, default=5, help="segments, with --seam")
    parser.add_argument(
        "--stall",
        type=float,
        default=0.0,
        help="seconds to block the main thread once, with --seam",
    )
    parser.add_argument("--buffer", type=int, default=BUFFER, help="mixer buffer size")
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / ".agent-audio",
        help="directory for the capture",
    )
    parser.add_argument("--wav", action="store_true", help="also write a .wav")
    args = parser.parse_args(argv)

    if not args.asset and not args.seam:
        parser.error("pass --asset <path> or --seam")

    args.out.mkdir(parents=True, exist_ok=True)
    if args.seam:
        raw = args.out / "seam.raw"
        capture, seam = capture_tone_loop(
            raw, args.laps, buffer=args.buffer, stall=args.stall
        )
        print(capture.report())
        print(seam.report())
    else:
        raw = args.out / f"{args.asset.stem}.raw"
        capture = capture_asset(args.asset, raw, buffer=args.buffer)
        print(f"{args.asset}:")
        print(capture.report())
    print(f"raw capture: {raw}")
    if args.wav:
        destination = raw.with_suffix(".wav")
        write_wav(raw, destination)
        print(f"wav: {destination}")
    return 1 if args.asset and capture.is_silent else 0


if __name__ == "__main__":
    raise SystemExit(main())
