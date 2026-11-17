"""The spark pool, held to values recorded while two stores agreed.

`tests/golden/sparks.json` was recorded from the Rust pool when the
engine still had a Python pool beside it, at a point where the two
agreed to the parity suite's tolerance. Values are compared to
`TOLERANCE`; `tests/golden/sparks.py` says why not exactly.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from tests.golden.sparks import SCENARIOS, TOLERANCE, Scenario, load, measure

RECORDED = load()
SECTIONS = ("slots", "circles", "lines", "rows")


def _differences(want: dict[str, Any], got: dict[str, Any]) -> list[str]:
    """Name what `got` holds or draws that the recording does not."""
    differing: list[str] = []
    if want["live"] != got["live"]:
        differing.append(f"live {got['live']}, recorded {want['live']}")
    for section in SECTIONS:
        if len(want[section]) != len(got[section]):
            differing.append(
                f"{section}: {len(got[section])} entries, recorded {len(want[section])}"
            )
            continue
        for index, (wanted, gotten) in enumerate(
            zip(want[section], got[section], strict=True)
        ):
            if len(wanted) != len(gotten) or any(
                abs(a - b) > TOLERANCE for a, b in zip(wanted, gotten, strict=False)
            ):
                differing.append(f"{section}[{index}] {gotten}, recorded {wanted}")
    return differing


class TestTheRecording:
    """The file covers the scenarios, and they are not trivial."""

    def test_every_scenario_is_recorded(self) -> None:
        assert set(RECORDED) == {scenario.name for scenario in SCENARIOS}

    def test_every_scenario_draws_something(self) -> None:
        """An empty pool would agree with a pool that never spawned."""
        for scenario in SCENARIOS:
            recorded = RECORDED[scenario.name]
            assert recorded["live"] > 0, scenario.name
            assert recorded["rows"], scenario.name

    def test_both_shapes_and_an_expiry_are_covered(self) -> None:
        assert any(RECORDED[s.name]["circles"] for s in SCENARIOS)
        assert any(RECORDED[s.name]["lines"] for s in SCENARIOS)
        assert RECORDED["expiring"]["live"] < 10


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_the_pool_matches_the_recording(scenario: Scenario) -> None:
    """Every slot, every primitive and every batched row."""
    differing = _differences(RECORDED[scenario.name], measure(scenario))
    assert not differing, f"{len(differing)} differ: {differing[:5]}"


class TestTheComparisonCanFail:
    """The control: a pool that is slightly off is caught."""

    def test_a_position_a_hundredth_of_a_pixel_off_is_reported(self) -> None:
        scenario = SCENARIOS[0]
        got = copy.deepcopy(RECORDED[scenario.name])
        got["circles"][0][0] += 0.01
        assert _differences(RECORDED[scenario.name], got)

    def test_a_missing_spark_is_reported(self) -> None:
        scenario = SCENARIOS[0]
        got = copy.deepcopy(RECORDED[scenario.name])
        got["rows"].pop()
        assert _differences(RECORDED[scenario.name], got)

    def test_a_different_seed_is_reported(self) -> None:
        scenario = SCENARIOS[0]
        other = Scenario(scenario.name, scenario.capacity, 1234, scenario.bursts)
        assert _differences(RECORDED[scenario.name], measure(other))
