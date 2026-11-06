"""Generates the placeholder SFX `.wav` files that live alongside this script.

Quintal do Cerrado's audio was wired up (`AudioManager.play_sfx`, see
`garden_widget.py`/`scenes.py`) before any real sound assets existed. Rather
than ship silence until an artist is involved, these are short, synthesized
tones, built with the engine's `pyguara.audio.placeholder`, which needs
nothing beyond the standard library.

Run it whenever a placeholder needs retuning:

    uv run python games/quintal_cerrado/assets/audio/generate_placeholder_sfx.py

It is deterministic (fixed RNG seed) so a re-run without code changes
produces byte-identical files -- a diff means the envelope actually changed.

Replacing a placeholder with a real recording later needs no code change:
`play_sfx` takes a path, and the filenames here are the contract.
"""

from __future__ import annotations

from pathlib import Path

from pyguara.audio.placeholder import (
    SAMPLE_RATE,
    Samples,
    concat,
    envelope,
    mix,
    noise,
    rng_for,
    sine,
    square,
    sweep,
    transient,
    write_wav,
)


def _build_sounds() -> dict[str, Samples]:
    """The full placeholder catalogue, keyed by filename stem.

    Each entry that needs noise draws from its own `rng_for(name)` stream,
    so editing one sound never perturbs another's bytes on a re-run.
    """
    return {
        # Tilling: a dull, low thud with a sharp crack of dirt breaking on
        # top -- the crack is what makes it read as landing on the click,
        # not a beat after it (a pure low tone's onset alone feels soft).
        "till": envelope(
            mix(transient(0.05, 0.55, rng_for("till")), sine(110.0, 0.14, 0.6)),
            attack=0.001,
            decay_rate=14.0,
        ),
        # Watering: a quick downward droplet.
        "water": envelope(sweep(900.0, 380.0, 0.16, 0.5), decay_rate=10.0),
        # Planting: a soft, small pop.
        "plant": envelope(sweep(320.0, 520.0, 0.09, 0.45), decay_rate=18.0),
        # Collecting a seed instead of a sale (a pulled weed, an overripe
        # crop): a soft two-note descent -- smaller and quieter than the
        # "harvest" cha-ching, since it is a smaller, different kind of win.
        "seed": concat(
            envelope(sine(660.0, 0.06, 0.35), decay_rate=20.0),
            envelope(sine(495.0, 0.09, 0.3), decay_rate=14.0),
        ),
        # A growth-stage advance: a cheerful two-note rise.
        "grow_stage": concat(
            envelope(sine(523.25, 0.08, 0.4), decay_rate=16.0),
            envelope(sine(659.25, 0.1, 0.45), decay_rate=14.0),
        ),
        # Harvest / sale: a brighter arpeggio -- the "cha-ching" beat.
        "harvest": concat(
            envelope(sine(659.25, 0.07, 0.4), decay_rate=18.0),
            envelope(sine(783.99, 0.07, 0.45), decay_rate=16.0),
            envelope(sine(1046.5, 0.12, 0.5), decay_rate=10.0),
        ),
        # Compost: a soft organic rustle -- noise, not a tone.
        "compost": envelope(
            mix(noise(0.16, 0.35, rng_for("compost")), sine(180.0, 0.16, 0.2)),
            decay_rate=9.0,
        ),
        # Chemical spray: a thin hiss.
        "spray": envelope(
            noise(0.18, 0.4, rng_for("spray")), attack=0.01, decay_rate=8.0
        ),
        # Infestation: a low, dissonant beat between two close frequencies.
        "infested": envelope(
            mix(sine(110.0, 0.32, 0.35), sine(116.0, 0.32, 0.35)), decay_rate=5.0
        ),
        # A plant dying: a slow, sad downward slide.
        "dying": envelope(sweep(420.0, 140.0, 0.42, 0.4), attack=0.02, decay_rate=4.0),
        # Denied / can't afford: a flat, short buzz.
        "denied": envelope(square(150.0, 0.12, 0.3), decay_rate=16.0),
        # Placing a structure: a short mechanical click.
        "build": concat(
            envelope(square(200.0, 0.03, 0.35), decay_rate=40.0),
            envelope(noise(0.03, 0.2, rng_for("build")), decay_rate=40.0),
        ),
        # Outbreak starting: an urgent two-tone alarm.
        "outbreak_start": concat(
            envelope(sine(600.0, 0.1, 0.5), decay_rate=12.0),
            envelope(sine(500.0, 0.1, 0.5), decay_rate=12.0),
            envelope(sine(600.0, 0.1, 0.5), decay_rate=12.0),
        ),
        # Outbreak resolved: a relieved little major-ish rise.
        "outbreak_resolved": concat(
            envelope(sine(392.0, 0.09, 0.4), decay_rate=14.0),
            envelope(sine(493.88, 0.09, 0.42), decay_rate=13.0),
            envelope(sine(587.33, 0.14, 0.45), decay_rate=9.0),
        ),
        # Solar income ticking in: a tiny, quiet high blip.
        "solar_income": envelope(sine(1046.5, 0.05, 0.25), decay_rate=30.0),
        # Going to sleep: a slow settling sigh, falling away. Longer and
        # softer than any action sound -- it is the end of a day, not a
        # click landing.
        "sleep": envelope(sweep(430.0, 180.0, 0.5, 0.3), attack=0.04, decay_rate=4.0),
        # Waking to the morning report: a gentle three-note rise, quieter
        # than "harvest" -- a good morning, not a prize.
        "morning": concat(
            envelope(sine(392.0, 0.11, 0.26), attack=0.02, decay_rate=9.0),
            envelope(sine(523.25, 0.11, 0.28), attack=0.02, decay_rate=9.0),
            envelope(sine(659.25, 0.2, 0.3), attack=0.02, decay_rate=6.0),
            gap=0.02,
        ),
    }


def main() -> None:
    """Regenerate every placeholder `.wav` next to this script."""
    out_dir = Path(__file__).parent
    for name, samples in _build_sounds().items():
        write_wav(out_dir / f"{name}.wav", samples)
        print(f"wrote {name}.wav ({len(samples) / SAMPLE_RATE:.2f}s)")


if __name__ == "__main__":
    main()
