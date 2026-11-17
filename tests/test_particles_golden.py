"""The particle pool, held to values recorded while two stores agreed.

`tests/golden/particles.json` was recorded from the Rust pool when the
engine still had a Python pool beside it, at a point where the two
agreed to the parity suite's tolerance. Values are compared to
`TOLERANCE`; `tests/golden/particles.py` says why not exactly.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from tests.golden.particles import SCENARIOS, TOLERANCE, Scenario, load, measure

RECORDED = load()


def _rows_differ(wanted: list[float], gotten: list[float]) -> bool:
    """Whether two rows of numbers differ by more than the tolerance."""
    return len(wanted) != len(gotten) or any(
        abs(a - b) > TOLERANCE for a, b in zip(wanted, gotten, strict=False)
    )


def _differences(want: dict[str, Any], got: dict[str, Any]) -> list[str]:
    """Name what `got` holds or draws that the recording does not."""
    differing: list[str] = []
    if want["live"] != got["live"]:
        differing.append(f"live {got['live']}, recorded {want['live']}")
    for index, (wanted, gotten) in enumerate(
        zip(want["slots"], got["slots"], strict=True)
    ):
        if _rows_differ(wanted, gotten):
            differing.append(f"slot {index} {gotten}, recorded {wanted}")

    if len(want["batches"]) != len(got["batches"]):
        differing.append(
            f"{len(got['batches'])} batches, recorded {len(want['batches'])}"
        )
        return differing
    for wanted, gotten in zip(want["batches"], got["batches"], strict=True):
        name = f"batch for texture {wanted['texture']}"
        if (wanted["texture"], wanted["tinted"]) != (
            gotten["texture"],
            gotten["tinted"],
        ):
            differing.append(f"{name}: texture or tint flag differs")
        for key in ("destinations", "colors"):
            if len(wanted[key]) != len(gotten[key]):
                differing.append(f"{name}: {len(gotten[key])} {key}")
                continue
            for index, (a, b) in enumerate(zip(wanted[key], gotten[key], strict=True)):
                if _rows_differ(a, b):
                    differing.append(f"{name} {key}[{index}] {b}, recorded {a}")
    return differing


class TestTheRecording:
    """The file covers the scenarios, and they are not trivial."""

    def test_every_scenario_is_recorded(self) -> None:
        assert set(RECORDED) == {scenario.name for scenario in SCENARIOS}

    def test_tinted_untinted_and_two_textures_are_covered(self) -> None:
        batches = [b for s in SCENARIOS for b in RECORDED[s.name]["batches"]]
        assert any(batch["tinted"] for batch in batches)
        assert any(not batch["tinted"] for batch in batches)
        assert len(RECORDED["two-textures"]["batches"]) == 2

    def test_expiry_is_recorded_on_both_sides_of_the_tick(self) -> None:
        assert RECORDED["last-tick-alive"]["live"] == 10
        assert RECORDED["expired"]["live"] == 0


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_the_pool_matches_the_recording(scenario: Scenario) -> None:
    """Every slot, and every batch's positions and tints."""
    differing = _differences(RECORDED[scenario.name], measure(scenario))
    assert not differing, f"{len(differing)} differ: {differing[:5]}"


class TestTheComparisonCanFail:
    """The control: a pool that is slightly off is caught."""

    def test_a_position_a_hundredth_of_a_pixel_off_is_reported(self) -> None:
        got = copy.deepcopy(RECORDED["plain"])
        got["batches"][0]["destinations"][0][0] += 0.01
        assert _differences(RECORDED["plain"], got)

    def test_a_tint_one_step_off_is_reported(self) -> None:
        name = "tinted-a-third-through"
        got = copy.deepcopy(RECORDED[name])
        got["batches"][0]["colors"][0][0] += 1
        assert _differences(RECORDED[name], got)

    def test_a_different_seed_is_reported(self) -> None:
        scenario = SCENARIOS[0]
        other = Scenario(scenario.name, scenario.capacity, 1234, scenario.emits)
        assert _differences(RECORDED[scenario.name], measure(other))
