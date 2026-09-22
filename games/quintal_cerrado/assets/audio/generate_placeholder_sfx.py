"""Generates the placeholder SFX `.wav` files that live alongside this script.

Quintal do Cerrado's audio was wired up (`AudioManager.play_sfx`, see
`garden_widget.py`/`scenes.py`) before any real sound assets existed. Rather
than ship silence until an artist is involved, these are short, synthesized
tones -- a stdlib-only substitute (`wave` + `math`, no numpy/soundfile) so
regenerating or retuning them needs nothing beyond Python itself.

Run it whenever a placeholder needs retuning:

    uv run python games/quintal_cerrado/assets/audio/generate_placeholder_sfx.py

It is deterministic (fixed RNG seed) so a re-run without code changes
produces byte-identical files -- a diff means the envelope actually changed.

Replacing a placeholder with a real recording later needs no code change:
`play_sfx` takes a path, and the filenames here are the contract.
"""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 22050
"""Low enough to keep every file a few KB; plenty for a short blip."""

_RNG_SEED = 20260921
"""Fixed so regenerating without edits yields byte-identical output."""

Samples = list[float]


def _sine(freq: float, duration: float, amplitude: float = 1.0) -> Samples:
    """A pure tone, `amplitude` peak, `freq` Hz, `duration` seconds."""
    count = int(SAMPLE_RATE * duration)
    return [
        amplitude * math.sin(2.0 * math.pi * freq * (i / SAMPLE_RATE))
        for i in range(count)
    ]


def _sweep(
    freq_start: float, freq_end: float, duration: float, amplitude: float = 1.0
) -> Samples:
    """A tone whose frequency glides linearly from `freq_start` to `freq_end`."""
    count = int(SAMPLE_RATE * duration)
    samples = []
    phase = 0.0
    for i in range(count):
        t = i / SAMPLE_RATE
        freq = freq_start + (freq_end - freq_start) * (t / duration if duration else 0)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        samples.append(amplitude * math.sin(phase))
    return samples


def _square(freq: float, duration: float, amplitude: float = 1.0) -> Samples:
    """A square wave -- flatter, more "mechanical" than a sine."""
    count = int(SAMPLE_RATE * duration)
    period = SAMPLE_RATE / freq
    return [
        amplitude if (i % period) < (period / 2) else -amplitude for i in range(count)
    ]


def _noise(duration: float, amplitude: float, rng: random.Random) -> Samples:
    """Flat white noise -- for a hiss, a rustle, or dirt crumbling."""
    count = int(SAMPLE_RATE * duration)
    return [rng.uniform(-amplitude, amplitude) for _ in range(count)]


def _envelope(
    samples: Samples, *, attack: float = 0.005, decay_rate: float = 8.0
) -> Samples:
    """Apply a fast linear attack then an exponential decay, so nothing clicks."""
    attack_samples = max(1, int(SAMPLE_RATE * attack))
    out = []
    for i, value in enumerate(samples):
        t = i / SAMPLE_RATE
        if i < attack_samples:
            gain = i / attack_samples
        else:
            gain = math.exp(-decay_rate * t)
        out.append(value * gain)
    return out


def _concat(*segments: Samples, gap: float = 0.01) -> Samples:
    """Chain segments end to end, with a short silence between each."""
    silence = [0.0] * int(SAMPLE_RATE * gap)
    out: Samples = []
    for i, segment in enumerate(segments):
        if i > 0:
            out.extend(silence)
        out.extend(segment)
    return out


def _mix(*segments: Samples) -> Samples:
    """Sum segments sample-for-sample (shorter ones are zero-padded)."""
    length = max(len(s) for s in segments)
    out = [0.0] * length
    for segment in segments:
        for i, value in enumerate(segment):
            out[i] += value
    return out


def _write_wav(path: Path, samples: Samples) -> None:
    """Clamp to [-1, 1], convert to 16-bit PCM, and write a mono `.wav`."""
    frames = struct.pack(
        f"<{len(samples)}h",
        *(int(max(-1.0, min(1.0, s)) * 32767) for s in samples),
    )
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(frames)


def _build_sounds(rng: random.Random) -> dict[str, Samples]:
    """The full placeholder catalogue, keyed by filename stem."""
    return {
        # Tilling: a dull, low thud -- turning dirt, not a bell.
        "till": _envelope(_sine(110.0, 0.14, 0.6), decay_rate=14.0),
        # Watering: a quick downward droplet.
        "water": _envelope(_sweep(900.0, 380.0, 0.16, 0.5), decay_rate=10.0),
        # Planting: a soft, small pop.
        "plant": _envelope(_sweep(320.0, 520.0, 0.09, 0.45), decay_rate=18.0),
        # A growth-stage advance: a cheerful two-note rise.
        "grow_stage": _concat(
            _envelope(_sine(523.25, 0.08, 0.4), decay_rate=16.0),
            _envelope(_sine(659.25, 0.1, 0.45), decay_rate=14.0),
        ),
        # Harvest / sale: a brighter arpeggio -- the "cha-ching" beat.
        "harvest": _concat(
            _envelope(_sine(659.25, 0.07, 0.4), decay_rate=18.0),
            _envelope(_sine(783.99, 0.07, 0.45), decay_rate=16.0),
            _envelope(_sine(1046.5, 0.12, 0.5), decay_rate=10.0),
        ),
        # Compost: a soft organic rustle -- noise, not a tone.
        "compost": _envelope(
            _mix(_noise(0.16, 0.35, rng), _sine(180.0, 0.16, 0.2)), decay_rate=9.0
        ),
        # Chemical spray: a thin hiss.
        "spray": _envelope(_noise(0.18, 0.4, rng), attack=0.01, decay_rate=8.0),
        # Infestation: a low, dissonant beat between two close frequencies.
        "infested": _envelope(
            _mix(_sine(110.0, 0.32, 0.35), _sine(116.0, 0.32, 0.35)), decay_rate=5.0
        ),
        # A plant dying: a slow, sad downward slide.
        "dying": _envelope(
            _sweep(420.0, 140.0, 0.42, 0.4), attack=0.02, decay_rate=4.0
        ),
        # Denied / can't afford: a flat, short buzz.
        "denied": _envelope(_square(150.0, 0.12, 0.3), decay_rate=16.0),
        # Placing a structure: a short mechanical click.
        "build": _concat(
            _envelope(_square(200.0, 0.03, 0.35), decay_rate=40.0),
            _envelope(_noise(0.03, 0.2, rng), decay_rate=40.0),
        ),
        # Outbreak starting: an urgent two-tone alarm.
        "outbreak_start": _concat(
            _envelope(_sine(600.0, 0.1, 0.5), decay_rate=12.0),
            _envelope(_sine(500.0, 0.1, 0.5), decay_rate=12.0),
            _envelope(_sine(600.0, 0.1, 0.5), decay_rate=12.0),
        ),
        # Outbreak resolved: a relieved little major-ish rise.
        "outbreak_resolved": _concat(
            _envelope(_sine(392.0, 0.09, 0.4), decay_rate=14.0),
            _envelope(_sine(493.88, 0.09, 0.42), decay_rate=13.0),
            _envelope(_sine(587.33, 0.14, 0.45), decay_rate=9.0),
        ),
        # Solar income ticking in: a tiny, quiet high blip.
        "solar_income": _envelope(_sine(1046.5, 0.05, 0.25), decay_rate=30.0),
    }


def main() -> None:
    """Regenerate every placeholder `.wav` next to this script."""
    out_dir = Path(__file__).parent
    rng = random.Random(_RNG_SEED)
    for name, samples in _build_sounds(rng).items():
        _write_wav(out_dir / f"{name}.wav", samples)
        print(f"wrote {name}.wav ({len(samples) / SAMPLE_RATE:.2f}s)")


if __name__ == "__main__":
    main()
