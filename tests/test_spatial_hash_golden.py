"""The spatial hash, held to answers recorded while two stores agreed.

`tests/golden/spatial.json` was recorded from the Rust index when the
engine still had a Python index beside it, which gave the same
membership on every query. The comparison is exact on sorted keys;
neither index defines an order.
"""

from __future__ import annotations

import copy

import pytest

from pyguara.common.spatial import SpatialHash
from tests.golden.spatial import SCRIPTS, Script, load, play
from tests.reference.spatial import ReferenceSpatialHash

RECORDED = load()
QUERIES = ("query_radius", "masked query_radius", "query_point", "query_rect")


def _differences(script: Script, got: list[list[list[str]]]) -> list[str]:
    """Name the queries whose answer departs from the recording."""
    want = RECORDED[script.name]
    if len(want) != len(got):
        return [f"{len(got)} query steps, recorded {len(want)}"]
    return [
        f"step {step} {QUERIES[kind]}: {sorted(set(b) ^ set(a))} differ"
        for step, (wanted, gotten) in enumerate(zip(want, got, strict=True))
        for kind, (a, b) in enumerate(zip(wanted, gotten, strict=True))
        if a != b
    ]


class TestTheRecording:
    """The file covers the scripts, and they are not trivial."""

    def test_every_script_is_recorded(self) -> None:
        assert set(RECORDED) == {script.name for script in SCRIPTS}

    def test_most_answers_are_not_empty(self) -> None:
        """An index that found nothing would agree with an empty recording."""
        for script in SCRIPTS:
            answers = [a for step in RECORDED[script.name] for a in step]
            assert sum(1 for a in answers if a) > len(answers) / 2, script.name


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda s: s.name)
def test_the_rust_index_matches_the_recording(script: Script) -> None:
    differing = _differences(script, play(script, SpatialHash[str](script.cell_size)))
    assert not differing, f"{len(differing)} differ: {differing[:3]}"


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda s: s.name)
def test_the_python_reference_matches_the_recording(script: Script) -> None:
    """So the recording is not only the Rust index agreeing with itself."""
    reference = ReferenceSpatialHash[str](script.cell_size)
    differing = _differences(script, play(script, reference))
    assert not differing, f"{len(differing)} differ: {differing[:3]}"


class TestTheComparisonCanFail:
    """The control: one key too many or too few is caught."""

    def test_an_extra_key_is_reported(self) -> None:
        script = SCRIPTS[0]
        got = copy.deepcopy(RECORDED[script.name])
        got[0][0].append("intruder")
        assert _differences(script, got)

    def test_a_missing_key_is_reported(self) -> None:
        script = SCRIPTS[0]
        got = copy.deepcopy(RECORDED[script.name])
        step = next(s for s in got if s[3])
        step[3].pop()
        assert _differences(script, got)
