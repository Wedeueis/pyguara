"""The flocking solver, held to values recorded while two stores agreed.

`tests/golden/flocking.json` was recorded from the Rust solver when the
engine still had a Python path beside it, which agreed to summation
noise. The comparison is exact, in `float.hex()`: the solver is f64,
sweeps in a fixed order and calls no platform maths function.
"""

from __future__ import annotations

import pytest

from tests.golden.flocking import SCENARIOS, Scenario, encode, load, play
from tests.reference.flocking import ReferenceFlockingSystem

RECORDED = load()

REFERENCE_TOLERANCE = 1e-9
"""Summation noise between the solver and the Python reference."""

SHORT = tuple(scenario for scenario in SCENARIOS if scenario.ticks <= 31)
"""The scenarios short enough that summation noise has not compounded."""


def _differences(scenario: Scenario, got: list[list[str]]) -> list[str]:
    """Name the agents whose row departs from the recording."""
    want = RECORDED[scenario.name]
    if len(want) != len(got):
        return [f"{len(got)} agents, recorded {len(want)}"]
    return [
        f"agent {index}: {gotten}, recorded {wanted}"
        for index, (wanted, gotten) in enumerate(zip(want, got, strict=True))
        if wanted != gotten
    ]


class TestTheRecording:
    """The file covers the scenarios, and they are not trivial."""

    def test_every_scenario_is_recorded(self) -> None:
        assert set(RECORDED) == {scenario.name for scenario in SCENARIOS}

    def test_every_flock_actually_moved(self) -> None:
        """A flock at rest would agree with a solver that does nothing."""
        for scenario in SCENARIOS:
            before = encode(play(Scenario(**{**vars(scenario), "ticks": 0})))
            assert before != RECORDED[scenario.name], scenario.name


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_the_solver_matches_the_recording(scenario: Scenario) -> None:
    """Every agent's position and velocity, bit for bit."""
    differing = _differences(scenario, encode(play(scenario)))
    assert not differing, f"{len(differing)} differ: {differing[:3]}"


@pytest.mark.parametrize("scenario", SHORT, ids=lambda s: s.name)
def test_the_python_reference_is_within_summation_noise(scenario: Scenario) -> None:
    """So the recording is not only the Rust solver agreeing with itself."""
    reference = play(scenario, ReferenceFlockingSystem)
    recorded = [
        [float.fromhex(value) for value in row] for row in RECORDED[scenario.name]
    ]
    worst = max(
        abs(a - b)
        for want, got in zip(recorded, reference, strict=True)
        for a, b in zip(want, got, strict=True)
    )
    assert worst <= REFERENCE_TOLERANCE, f"reference is {worst:.2e} from the recording"


class TestTheComparisonCanFail:
    """The control: a flock one step off is caught."""

    def test_one_more_tick_is_reported(self) -> None:
        scenario = SCENARIOS[0]
        longer = Scenario(**{**vars(scenario), "ticks": scenario.ticks + 1})
        assert _differences(scenario, encode(play(longer)))

    def test_a_single_bit_is_reported(self) -> None:
        scenario = SCENARIOS[1]
        rows = play(scenario)
        rows[0][0] = rows[0][0] + abs(rows[0][0]) * 2.0**-52
        assert _differences(scenario, encode(rows))
