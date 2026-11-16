"""The flow field, held to the values recorded while two stores agreed.

`tests/golden/flow_field.json` was written when the engine still had a
Python flow-field store beside the Rust one, from results both produced.
The comparison is exact: costs and directions are stored as float hex.

`test_flow_field_reference.py` compares against a living Python
implementation. This file is what still stands if that reference and the
Rust were ever changed together.
"""

from __future__ import annotations

import pytest

from pyguara.ai.pathfinding.flow_field_service import FlowFieldService
from tests.golden.flow_field import SCENARIOS, Scenario, load, measure
from tests.reference.flow_field import ReferenceFlowField

RECORDED = load()


def _differences(scenario: Scenario, got: dict) -> list[str]:
    """Name the cells where `got` departs from the recording."""
    want = RECORDED[scenario.name]
    differing: list[str] = []
    for index in range(scenario.width * scenario.height):
        cell = (index % scenario.width, index // scenario.width)
        want_cost = want["values"][want["costs"][index]]
        got_cost = got["values"][got["costs"][index]]
        if want_cost != got_cost:
            differing.append(f"{cell} cost {got_cost}, recorded {want_cost}")
        want_dir = [want["values"][i] for i in want["directions"][index]]
        got_dir = [got["values"][i] for i in got["directions"][index]]
        if want_dir != got_dir:
            differing.append(f"{cell} direction {got_dir}, recorded {want_dir}")
    return differing


class TestTheRecording:
    """The file covers the scenarios, and only them."""

    def test_every_scenario_is_recorded(self) -> None:
        assert set(RECORDED) == {scenario.name for scenario in SCENARIOS}

    def test_a_recording_is_not_trivially_empty(self) -> None:
        """A field of zeros would agree with a broken engine."""
        for scenario in SCENARIOS:
            assert len(RECORDED[scenario.name]["values"]) > 10, scenario.name


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
class TestTheFieldMatchesTheRecording:
    """Every cell's cost and direction, bit for bit."""

    def test_the_rust_service_matches(self, scenario: Scenario) -> None:
        got = measure(scenario, FlowFieldService(scenario.graph()))
        differing = _differences(scenario, got)
        assert not differing, f"{len(differing)} differ: {differing[:5]}"

    def test_the_python_reference_matches(self, scenario: Scenario) -> None:
        """So a regenerated file cannot quietly record something else."""
        got = measure(scenario, ReferenceFlowField(scenario.graph()))
        differing = _differences(scenario, got)
        assert not differing, f"{len(differing)} differ: {differing[:5]}"


class TestTheComparisonCanFail:
    """The control: a field that is one step off is caught."""

    def test_a_different_goal_is_reported(self) -> None:
        scenario = SCENARIOS[0]
        moved = Scenario(scenario.name, scenario.width, scenario.height, ((5, 6),))
        got = measure(moved, FlowFieldService(moved.graph()))
        assert _differences(scenario, got)

    def test_a_diagonal_step_of_root_two_is_reported(self) -> None:
        """`GridGraph.cost` uses 1.414; the more accurate constant is wrong."""
        scenario = SCENARIOS[0]
        got = measure(scenario, FlowFieldService(scenario.graph()))
        slipped = dict(got)
        slipped["values"] = [
            (2.0**0.5).hex() if value == (1.414).hex() else value
            for value in got["values"]
        ]
        assert slipped["values"] != got["values"]
        assert _differences(scenario, slipped)
