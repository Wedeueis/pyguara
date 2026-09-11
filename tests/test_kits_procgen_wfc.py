"""Tests for `pyguara/kits/procgen/wfc.py` (Wave Function Collapse)."""

from __future__ import annotations

import pytest

from pyguara.common.grid import neighbors4
from pyguara.common.random import RandomStream
from pyguara.kits.procgen import (
    AdjacencyRule,
    WfcContradictionError,
    generate_wfc,
)

_CHECKERBOARD_RULES = [
    AdjacencyRule(from_state="A", to_state="B", direction=(1, 0)),
    AdjacencyRule(from_state="A", to_state="B", direction=(-1, 0)),
    AdjacencyRule(from_state="A", to_state="B", direction=(0, 1)),
    AdjacencyRule(from_state="A", to_state="B", direction=(0, -1)),
    AdjacencyRule(from_state="B", to_state="A", direction=(1, 0)),
    AdjacencyRule(from_state="B", to_state="A", direction=(-1, 0)),
    AdjacencyRule(from_state="B", to_state="A", direction=(0, 1)),
    AdjacencyRule(from_state="B", to_state="A", direction=(0, -1)),
]


def test_a_zero_size_grid_returns_empty() -> None:
    assert generate_wfc(0, 0, ["A"], [], RandomStream(1)) == {}


def test_a_single_state_fills_every_cell() -> None:
    result = generate_wfc(3, 3, ["only"], [], RandomStream(1))

    assert result == {(x, y): "only" for x in range(3) for y in range(3)}


def test_checkerboard_rules_force_every_neighbor_to_differ() -> None:
    result = generate_wfc(4, 4, ["A", "B"], _CHECKERBOARD_RULES, RandomStream(1))

    assert set(result.keys()) == {(x, y) for x in range(4) for y in range(4)}
    for cell, state in result.items():
        for neighbor in neighbors4(cell):
            if neighbor in result:
                assert result[neighbor] != state


def test_generation_is_deterministic() -> None:
    a = generate_wfc(5, 5, ["A", "B"], _CHECKERBOARD_RULES, RandomStream(42))
    b = generate_wfc(5, 5, ["A", "B"], _CHECKERBOARD_RULES, RandomStream(42))

    assert a == b


def test_pinned_cell_forces_its_state() -> None:
    result = generate_wfc(
        4,
        4,
        ["A", "B"],
        _CHECKERBOARD_RULES,
        RandomStream(1),
        pinned={(0, 0): "A"},
    )

    assert result[(0, 0)] == "A"


def test_weights_bias_the_distribution() -> None:
    result = generate_wfc(
        20,
        20,
        ["common", "rare"],
        rules=[],
        rng=RandomStream(123),
        weights={"common": 9.0, "rare": 1.0},
    )

    rare_fraction = list(result.values()).count("rare") / len(result)
    assert 0.05 < rare_fraction < 0.15  # expected ~0.10


def test_an_unsatisfiable_rule_set_raises_after_max_attempts() -> None:
    rules = [AdjacencyRule(from_state="A", to_state="B", direction=(1, 0))]

    with pytest.raises(WfcContradictionError):
        generate_wfc(
            2,
            1,
            ["A", "B"],
            rules,
            RandomStream(1),
            pinned={(0, 0): "A", (1, 0): "A"},
            max_attempts=3,
        )


def test_empty_states_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        generate_wfc(2, 2, [], [], RandomStream(1))


def test_an_out_of_bounds_pinned_cell_is_rejected() -> None:
    with pytest.raises(ValueError, match="out of bounds"):
        generate_wfc(2, 2, ["A"], [], RandomStream(1), pinned={(5, 5): "A"})


def test_a_pinned_state_not_in_states_is_rejected() -> None:
    with pytest.raises(ValueError, match="not in states"):
        generate_wfc(2, 2, ["A"], [], RandomStream(1), pinned={(0, 0): "B"})
