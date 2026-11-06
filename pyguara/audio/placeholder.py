"""Placeholder sound effects, built from simple tones, before any real ones exist.

A game wires its sounds up long before an artist records any. Rather than ship
silence, this makes short synthesized stand-ins -- a thud, a blip, a hiss -- from
the standard library alone, and writes them as `.wav` files the game then loads
like any other. Replacing one with a real recording later changes no code: the
file name is the contract.

Two ways in, the same sounds out:

- **Functions**, which build and combine samples in Python:

      hit = envelope(mix(transient(0.03, 0.5, rng), sine(140.0, 0.12, 0.6)),
                     decay_rate=20.0)

- **Recipes**, the same tree as data, for a game that keeps its tuning in files:

      {"hit": {"envelope": {"decay_rate": 20.0, "of": {"mix": [
          {"transient": {"duration": 0.03, "amplitude": 0.5}},
          {"sine": {"freq": 140.0, "duration": 0.12, "amplitude": 0.6}}]}}}}

  A recipe node is an object with one key, naming a function below, whose value
  holds that function's arguments: `envelope` and `concat` take what they wrap
  as `of`, and `mix` takes a list. `build_placeholders` checks the whole tree
  and names the exact place a mistake is, with the closest valid name. From
  the command line: `pyguara sounds recipes.json out/`.

Output is deterministic. Noise draws from a stream seeded by the sound's own
name, so editing one sound never changes another's bytes, and a rebuild without
edits writes identical files -- a diff means a sound changed.
"""

from __future__ import annotations

import difflib
import math
import random
import struct
import wave
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

SAMPLE_RATE = 22050
"""Samples per second. Low enough to keep each file a few KB; plenty for a blip."""

DEFAULT_SEED = 20260921
"""What `rng_for` seeds with unless told otherwise."""

Samples = list[float]


def sine(freq: float, duration: float, amplitude: float = 1.0) -> Samples:
    """Return a pure tone.

    Args:
        freq: Hz.
        duration: Seconds.
        amplitude: Peak, where 1.0 is full scale.
    """
    count = int(SAMPLE_RATE * duration)
    return [
        amplitude * math.sin(2.0 * math.pi * freq * (i / SAMPLE_RATE))
        for i in range(count)
    ]


def sweep(
    freq_start: float, freq_end: float, duration: float, amplitude: float = 1.0
) -> Samples:
    """Return a tone whose pitch glides in a straight line from one Hz to another.

    Args:
        freq_start: Hz at the start.
        freq_end: Hz at the end.
        duration: Seconds.
        amplitude: Peak, where 1.0 is full scale.
    """
    count = int(SAMPLE_RATE * duration)
    samples = []
    phase = 0.0
    for i in range(count):
        t = i / SAMPLE_RATE
        freq = freq_start + (freq_end - freq_start) * (t / duration if duration else 0)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        samples.append(amplitude * math.sin(phase))
    return samples


def square(freq: float, duration: float, amplitude: float = 1.0) -> Samples:
    """Return a square wave: flatter and more mechanical than a sine.

    Args:
        freq: Hz.
        duration: Seconds.
        amplitude: Peak, where 1.0 is full scale.
    """
    count = int(SAMPLE_RATE * duration)
    period = SAMPLE_RATE / freq
    return [
        amplitude if (i % period) < (period / 2) else -amplitude for i in range(count)
    ]


def noise(duration: float, amplitude: float, rng: random.Random) -> Samples:
    """Return flat white noise: a hiss, a rustle, grit.

    Args:
        duration: Seconds.
        amplitude: Peak, where 1.0 is full scale.
        rng: Where the noise comes from. See `rng_for`.
    """
    count = int(SAMPLE_RATE * duration)
    return [rng.uniform(-amplitude, amplitude) for _ in range(count)]


def envelope(
    samples: Samples, *, attack: float = 0.005, decay_rate: float = 8.0
) -> Samples:
    """Fade a sound in quickly and let it die away, so it doesn't click.

    Args:
        samples: The sound.
        attack: Seconds of linear fade-in.
        decay_rate: How fast it dies away after that: the gain is
            `exp(-decay_rate * t)`, so 20 is a blip and 4 a long tail.
    """
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


def concat(*segments: Samples, gap: float = 0.01) -> Samples:
    """Play sounds one after another, with a short silence between each.

    Args:
        *segments: The sounds, in order.
        gap: Seconds of silence between two.
    """
    silence = [0.0] * int(SAMPLE_RATE * gap)
    out: Samples = []
    for i, segment in enumerate(segments):
        if i > 0:
            out.extend(silence)
        out.extend(segment)
    return out


def mix(*segments: Samples) -> Samples:
    """Play sounds at once, summed sample by sample. Shorter ones end early.

    Args:
        *segments: The sounds, at least one.
    """
    length = max(len(s) for s in segments)
    out = [0.0] * length
    for segment in segments:
        for i, value in enumerate(segment):
            out[i] += value
    return out


def transient(duration: float, amplitude: float, rng: random.Random) -> Samples:
    """Return a very short, sharply decaying burst of noise.

    A tone's onset sounds sluggish however fast it fades in: the ear hears
    "instant" in a broadband rise, not in one frequency. Mixed under a tone,
    this is what makes a thud land on the frame it was meant for instead of a
    beat late.

    Args:
        duration: Seconds.
        amplitude: Peak, where 1.0 is full scale.
        rng: Where the noise comes from. See `rng_for`.
    """
    return envelope(noise(duration, amplitude, rng), attack=0.0005, decay_rate=90.0)


def rng_for(name: str, seed: int = DEFAULT_SEED) -> random.Random:
    """Return a noise stream of one sound's own, seeded by its name.

    Shared by every sound, one stream would make editing one sound shift the
    noise of every sound built after it.

    Args:
        name: The sound's name.
        seed: Shared by every sound in a set; change it to reroll them all.
    """
    return random.Random(f"{seed}:{name}")


def write_wav(path: Path, samples: Samples) -> None:
    """Write a sound as a mono 16-bit `.wav`, clipping anything past full scale.

    Args:
        path: Where to write it. Its directory must exist.
        samples: The sound.
    """
    frames = struct.pack(
        f"<{len(samples)}h",
        *(int(max(-1.0, min(1.0, s)) * 32767) for s in samples),
    )
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(frames)


# ===== Recipes =====


class RecipeError(ValueError):
    """A placeholder recipe that can't be built. The message says where, and why."""


# What each recipe node accepts: required fields, then optional ones with their
# defaults. `of` is the nested sound(s), checked separately.
_FIELDS: dict[str, tuple[tuple[str, ...], dict[str, float]]] = {
    "sine": (("freq", "duration"), {"amplitude": 1.0}),
    "square": (("freq", "duration"), {"amplitude": 1.0}),
    "sweep": (("freq_start", "freq_end", "duration"), {"amplitude": 1.0}),
    "noise": (("duration", "amplitude"), {}),
    "transient": (("duration", "amplitude"), {}),
    "envelope": ((), {"attack": 0.005, "decay_rate": 8.0}),
    "concat": ((), {"gap": 0.01}),
    "mix": ((), {}),
}
# Fields that must be above zero; everything else must be at least zero.
_POSITIVE = {"freq", "freq_start", "freq_end", "duration"}


def _closest(word: str, choices: Sequence[str]) -> str:
    match = difflib.get_close_matches(word, choices, n=1)
    return f"; did you mean {match[0]!r}?" if match else ""


def _number(value: object, where: str, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RecipeError(f"{where}: {name} must be a number, got {value!r}.")
    number = float(value)
    if not math.isfinite(number):
        raise RecipeError(f"{where}: {name} must be finite, got {value!r}.")
    if name in _POSITIVE and number <= 0.0:
        raise RecipeError(f"{where}: {name} must be above 0, got {value!r}.")
    if number < 0.0:
        raise RecipeError(f"{where}: {name} must be 0 or more, got {value!r}.")
    return number


def _nested(value: object, where: str) -> list[object]:
    if not isinstance(value, list) or not value:
        raise RecipeError(f"{where}: expected a list of one or more sounds.")
    return value


def _build(node: object, where: str, rng: random.Random) -> Samples:
    if not isinstance(node, Mapping) or len(node) != 1:
        raise RecipeError(
            f"{where}: a sound is an object with exactly one key, naming what it "
            f"is ({', '.join(sorted(_FIELDS))}); got {node!r}."
        )
    ((kind, body),) = node.items()
    if kind not in _FIELDS:
        raise RecipeError(
            f"{where}: unknown sound {kind!r}{_closest(kind, sorted(_FIELDS))}"
        )
    where = f"{where} > {kind}"
    if kind == "mix":
        parts = _nested(body, where)
        return mix(*(_build(p, f"{where}[{i}]", rng) for i, p in enumerate(parts)))

    if not isinstance(body, Mapping):
        raise RecipeError(f"{where}: expected an object of arguments, got {body!r}.")
    required, optional = _FIELDS[kind]
    wraps = kind in ("envelope", "concat")
    allowed = [*required, *optional, *(["of"] if wraps else [])]
    for key in body:
        if key not in allowed:
            raise RecipeError(
                f"{where}: unknown argument {key!r}{_closest(str(key), allowed)}"
            )
    missing = [
        key for key in (*required, *(["of"] if wraps else [])) if key not in body
    ]
    if missing:
        raise RecipeError(f"{where}: missing {', '.join(missing)}.")
    args = {
        key: _number(body.get(key, optional.get(key)), where, key)
        for key in (*required, *optional)
    }

    if kind == "envelope":
        inner = _build(body["of"], f"{where} > of", rng)
        return envelope(inner, **args)
    if kind == "concat":
        parts = _nested(body["of"], f"{where} > of")
        return concat(
            *(_build(p, f"{where} > of[{i}]", rng) for i, p in enumerate(parts)),
            **args,
        )
    builders: dict[str, Callable[..., Samples]] = {
        "sine": sine,
        "square": square,
        "sweep": sweep,
    }
    if kind in builders:
        return builders[kind](**args)
    return (noise if kind == "noise" else transient)(rng=rng, **args)


def build_placeholder(
    name: str, recipe: object, *, seed: int = DEFAULT_SEED
) -> Samples:
    """Build one sound from its recipe.

    Args:
        name: The sound's name, which seeds its noise. Errors start with it.
        recipe: The recipe tree; see the module docstring.
        seed: Shared by every sound in a set.

    Returns:
        The sound.

    Raises:
        RecipeError: If the recipe is malformed, naming where.
    """
    return _build(recipe, name, rng_for(name, seed))


def build_placeholders(
    recipes: Mapping[str, Any], out_dir: Path, *, seed: int = DEFAULT_SEED
) -> list[Path]:
    """Build every sound in a set and write each as `<name>.wav`.

    Every recipe is checked before any file is written, so a mistake in the
    last one doesn't leave half a set rebuilt.

    Args:
        recipes: Sound name to recipe.
        out_dir: Where to write them. Created if missing.
        seed: Shared by every sound in the set.

    Returns:
        The files written, in the order given.

    Raises:
        RecipeError: If any recipe is malformed, or a name isn't a plain
            file name.
    """
    built: dict[str, Samples] = {}
    for name, recipe in recipes.items():
        if not name or Path(name).name != name or name.startswith("."):
            raise RecipeError(f"{name!r}: a sound's name must be a plain file name.")
        built[name] = build_placeholder(name, recipe, seed=seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, samples in built.items():
        path = out_dir / f"{name}.wav"
        write_wav(path, samples)
        written.append(path)
    return written
