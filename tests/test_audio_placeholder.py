"""`pyguara.audio.placeholder`: synthesized stand-in sounds, from code or recipes."""

from __future__ import annotations

import importlib.util
import json
import math
import wave
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from pyguara.audio import placeholder as ph
from pyguara.audio.placeholder import RecipeError, build_placeholder, build_placeholders
from pyguara.cli import main as cli

DEMO_AUDIO = Path(__file__).parent.parent / "games/quintal_cerrado/assets/audio"

HIT = {
    "envelope": {
        "decay_rate": 20.0,
        "attack": 0.001,
        "of": {
            "mix": [
                {"transient": {"duration": 0.03, "amplitude": 0.5}},
                {"sine": {"freq": 140.0, "duration": 0.12, "amplitude": 0.6}},
            ]
        },
    }
}


def test_a_recipe_builds_what_the_functions_build():
    rng = ph.rng_for("hit")
    by_hand = ph.envelope(
        ph.mix(ph.transient(0.03, 0.5, rng), ph.sine(140.0, 0.12, 0.6)),
        attack=0.001,
        decay_rate=20.0,
    )
    assert build_placeholder("hit", HIT) == by_hand


@pytest.mark.parametrize(
    ("recipe", "expected"),
    [
        ({"sine": {"freq": 440.0, "duration": 0.1}}, lambda r: ph.sine(440.0, 0.1)),
        (
            {"square": {"freq": 200.0, "duration": 0.05, "amplitude": 0.3}},
            lambda r: ph.square(200.0, 0.05, 0.3),
        ),
        (
            {"sweep": {"freq_start": 900, "freq_end": 380, "duration": 0.16}},
            lambda r: ph.sweep(900.0, 380.0, 0.16),
        ),
        (
            {"noise": {"duration": 0.05, "amplitude": 0.4}},
            lambda r: ph.noise(0.05, 0.4, r),
        ),
        (
            {"transient": {"duration": 0.02, "amplitude": 0.4}},
            lambda r: ph.transient(0.02, 0.4, r),
        ),
        (
            {
                "concat": {
                    "gap": 0.02,
                    "of": [
                        {"sine": {"freq": 523.25, "duration": 0.05}},
                        {"sine": {"freq": 659.25, "duration": 0.05}},
                    ],
                }
            },
            lambda r: ph.concat(ph.sine(523.25, 0.05), ph.sine(659.25, 0.05), gap=0.02),
        ),
        (
            {"envelope": {"of": {"sine": {"freq": 300.0, "duration": 0.05}}}},
            lambda r: ph.envelope(ph.sine(300.0, 0.05)),
        ),
    ],
)
def test_each_recipe_node_is_its_function(recipe: Any, expected: Any):
    assert build_placeholder("s", recipe) == expected(ph.rng_for("s"))


def test_noise_follows_the_sound_name_and_the_seed():
    recipe = {"noise": {"duration": 0.02, "amplitude": 1.0}}
    assert build_placeholder("a", recipe) == build_placeholder("a", recipe)
    assert build_placeholder("a", recipe) != build_placeholder("b", recipe)
    assert build_placeholder("a", recipe) != build_placeholder("a", recipe, seed=1)


def test_editing_one_sound_leaves_another_alone(tmp_path: Path):
    noisy = {"noise": {"duration": 0.02, "amplitude": 1.0}}
    first = build_placeholders({"a": noisy, "b": noisy}, tmp_path / "1")
    edited = {"a": {"noise": {"duration": 0.03, "amplitude": 1.0}}, "b": noisy}
    second = build_placeholders(edited, tmp_path / "2")
    assert first[0].read_bytes() != second[0].read_bytes()
    assert first[1].read_bytes() == second[1].read_bytes()


def test_build_placeholders_writes_mono_16_bit_wavs(tmp_path: Path):
    written = build_placeholders({"hit": HIT}, tmp_path / "new" / "dir")
    assert written == [tmp_path / "new" / "dir" / "hit.wav"]
    with wave.open(str(written[0])) as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == ph.SAMPLE_RATE
        assert wav.getnframes() == len(build_placeholder("hit", HIT))


def test_a_rebuild_is_byte_identical(tmp_path: Path):
    (first,) = build_placeholders({"hit": HIT}, tmp_path / "1")
    (second,) = build_placeholders({"hit": HIT}, tmp_path / "2")
    assert first.read_bytes() == second.read_bytes()


def test_samples_past_full_scale_are_clipped(tmp_path: Path):
    loud = {"mix": [{"square": {"freq": 100.0, "duration": 0.01}}] * 3}
    (path,) = build_placeholders({"loud": loud}, tmp_path)
    with wave.open(str(path)) as wav:
        frames = wav.readframes(wav.getnframes())
    values = memoryview(frames).cast("h")
    assert max(values) == 32767
    assert min(values) == -32767


def test_one_bad_recipe_writes_nothing(tmp_path: Path):
    with pytest.raises(RecipeError):
        build_placeholders({"good": HIT, "bad": {"sine": {}}}, tmp_path)
    assert not tmp_path.exists() or not any(tmp_path.iterdir())


@pytest.mark.parametrize("name", ["", "../escape", "a/b", ".hidden"])
def test_a_name_must_be_a_plain_file_name(tmp_path: Path, name: str):
    with pytest.raises(RecipeError, match="plain file name"):
        build_placeholders({name: HIT}, tmp_path)


@pytest.mark.parametrize(
    ("recipe", "message"),
    [
        (
            {"sin": {"freq": 1, "duration": 1}},
            r"hit: unknown sound 'sin'; did you mean 'sine'\?",
        ),
        (
            {"sine": {"frq": 440, "duration": 0.1}},
            r"hit > sine: unknown argument 'frq'; did you mean 'freq'\?",
        ),
        ({"sine": {"duration": 0.1}}, r"hit > sine: missing freq\."),
        ({"envelope": {"attack": 0.01}}, r"hit > envelope: missing of\."),
        ({"sine": {"freq": "440", "duration": 0.1}}, "freq must be a number"),
        ({"sine": {"freq": True, "duration": 0.1}}, "freq must be a number"),
        ({"sine": {"freq": 440, "duration": 0}}, "duration must be above 0"),
        ({"sine": {"freq": 440, "duration": math.nan}}, "duration must be finite"),
        (
            {"sine": {"freq": 440, "duration": 0.1, "amplitude": -1}},
            "amplitude must be 0 or more",
        ),
        ({"mix": []}, r"hit > mix: expected a list of one or more sounds"),
        ({"concat": {"of": {"sine": {}}}}, r"hit > concat > of: expected a list"),
        ({"sine": 440}, "expected an object of arguments"),
        ({"sine": {}, "square": {}}, "exactly one key"),
        ("sine", "exactly one key"),
        (
            {
                "envelope": {
                    "of": {
                        "mix": [
                            {"sine": {"freq": 1, "duration": 1}},
                            {"sine": {"freq": 1}},
                        ]
                    }
                }
            },
            r"hit > envelope > of > mix\[1\] > sine: missing duration\.",
        ),
        (
            {
                "concat": {
                    "of": [{"noise": {"duration": 1, "amplitude": 1}}, {"tone": {}}]
                }
            },
            r"hit > concat > of\[1\]: unknown sound 'tone'",
        ),
    ],
)
def test_a_mistake_names_where_it_is(recipe: Any, message: str):
    with pytest.raises(RecipeError, match=message):
        build_placeholder("hit", recipe)


def test_the_demo_still_makes_the_sounds_it_ships(tmp_path: Path, monkeypatch: Any):
    """Quintal do Cerrado's generator, moved onto this module, rebuilds its files."""
    spec = importlib.util.spec_from_file_location(
        "generate_placeholder_sfx", DEMO_AUDIO / "generate_placeholder_sfx.py"
    )
    assert spec is not None and spec.loader is not None
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    shipped = sorted(DEMO_AUDIO.glob("*.wav"))
    assert shipped
    for name, samples in demo._build_sounds().items():
        ph.write_wav(tmp_path / f"{name}.wav", samples)
    for path in shipped:
        assert (tmp_path / path.name).read_bytes() == path.read_bytes(), path.name


def test_the_command_builds_a_recipe_file(tmp_path: Path):
    recipes = tmp_path / "sounds.json"
    recipes.write_text(json.dumps({"hit": HIT}))
    result = CliRunner().invoke(cli, ["sounds", str(recipes), str(tmp_path / "out")])
    assert result.exit_code == 0, result.output
    assert "hit.wav" in result.output
    assert (tmp_path / "out" / "hit.wav").exists()


def test_the_command_reports_a_bad_recipe(tmp_path: Path):
    recipes = tmp_path / "sounds.json"
    recipes.write_text(json.dumps({"hit": {"sin": {}}}))
    result = CliRunner().invoke(cli, ["sounds", str(recipes), str(tmp_path / "out")])
    assert result.exit_code != 0
    assert "unknown sound 'sin'; did you mean 'sine'?" in result.output
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("text", ["{not json", "[1, 2]"])
def test_the_command_reports_a_bad_file(tmp_path: Path, text: str):
    recipes = tmp_path / "sounds.json"
    recipes.write_text(text)
    result = CliRunner().invoke(cli, ["sounds", str(recipes), str(tmp_path / "out")])
    assert result.exit_code != 0
    assert str(recipes) in result.output


def test_the_seed_option_rerolls_noise(tmp_path: Path):
    recipes = tmp_path / "sounds.json"
    recipes.write_text(json.dumps({"n": {"noise": {"duration": 0.02, "amplitude": 1}}}))
    runner = CliRunner()
    runner.invoke(cli, ["sounds", str(recipes), str(tmp_path / "a")])
    runner.invoke(cli, ["sounds", str(recipes), str(tmp_path / "b"), "--seed", "7"])
    assert (tmp_path / "a/n.wav").read_bytes() != (tmp_path / "b/n.wav").read_bytes()
