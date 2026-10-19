"""Tests for `pyguara/kits/procgen/wfc.py` (Wave Function Collapse)."""

from __future__ import annotations

import hashlib

import pytest

from pyguara.common.grid import Cell, neighbors4, neighbors8
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


# --- Output parity across the entropy-heap rewrite -------------------
#
# `generate_wfc` used to find the next cell to collapse by listing every
# undecided cell and sorting it, once per collapse -- O(N^2 log N) overall,
# and 95% of a 48x48 generation. It now keeps a lazily-invalidated heap
# keyed on `(entropy, row-major position)`.
#
# That is a rewrite of the thing which decides *which* cell collapses, so
# "the tests still pass" is not the question: a wrong-but-plausible
# selection order still produces a valid grid, from the same seed, obeying
# every rule -- and a different one. Every assertion above would stay
# green. What has to hold is that a given seed produces the *same* grid it
# produced before, because a saved level, a replay and a shared seed all
# depend on it.
#
# These digests were captured from the scan-and-sort implementation and
# are not to be regenerated to make a failure go away. A failure here
# means seeds have stopped meaning what they meant, which is a breaking
# change to every world already generated.

_TERRAIN = ["water", "sand", "grass", "rock"]
_TERRAIN_ADJACENCY = {
    "water": ["water", "sand"],
    "sand": ["water", "sand", "grass"],
    "grass": ["sand", "grass", "rock"],
    "rock": ["grass", "rock"],
}
_DIRS4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
_DIRS8 = _DIRS4 + ((1, 1), (1, -1), (-1, 1), (-1, -1))


def _terrain_rules(directions: tuple[Cell, ...]) -> list[AdjacencyRule[str]]:
    """The terrain adjacency above, expanded over `directions`."""
    return [
        AdjacencyRule(from_state=a, to_state=b, direction=d)
        for a, allowed in _TERRAIN_ADJACENCY.items()
        for b in allowed
        for d in directions
    ]


def _grid_digest(grid: dict[Cell, str]) -> str:
    """A short, order-independent fingerprint of a generated grid."""
    payload = ";".join(f"{x},{y}={grid[(x, y)]}" for (x, y) in sorted(grid))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _state_digest(rng: RandomStream) -> str:
    """A fingerprint of how far the stream was consumed."""
    return hashlib.sha256(repr(rng.get_state()).encode()).hexdigest()[:16]


# name -> (kwargs, seed, grid digest, rng-state digest)
_GOLDENS: list[tuple[str, dict[str, object], int, str, str]] = [
    (
        "4way_8x8",
        {"width": 8, "height": 8, "states": _TERRAIN, "rules": _terrain_rules(_DIRS4)},
        1,
        "026c08f41bd5fcb4",
        "5406b754d2f19ec9",
    ),
    (
        "4way_8x8_other_seed",
        {"width": 8, "height": 8, "states": _TERRAIN, "rules": _terrain_rules(_DIRS4)},
        2,
        "818cc77ae86fab04",
        "a638475d09d0e569",
    ),
    (
        "4way_oblong",
        {"width": 12, "height": 9, "states": _TERRAIN, "rules": _terrain_rules(_DIRS4)},
        7,
        "ac145d8deeac46dc",
        "8811af935365a710",
    ),
    (
        "8way",
        {
            "width": 10,
            "height": 10,
            "states": _TERRAIN,
            "rules": _terrain_rules(_DIRS8),
            "neighbor_fn": neighbors8,
        },
        3,
        "321a249656cc6f95",
        "cbe3a227967f71da",
    ),
    (
        "weighted",
        {
            "width": 10,
            "height": 10,
            "states": _TERRAIN,
            "rules": _terrain_rules(_DIRS4),
            "weights": {"water": 5.0, "rock": 0.2},
        },
        5,
        "b2caca1b1257a660",
        "283cb41c159956b3",
    ),
    (
        "pinned",
        {
            "width": 10,
            "height": 10,
            "states": _TERRAIN,
            "rules": _terrain_rules(_DIRS4),
            "pinned": {(0, 0): "water", (9, 9): "rock"},
        },
        11,
        "e9c98af0ec8c5b0a",
        "40880264d2b8910f",
    ),
    (
        "single_state",
        {"width": 6, "height": 6, "states": ["A"], "rules": []},
        1,
        "52bf2f7f085206e5",
        "b55f01246d4598a8",
    ),
    (
        "no_rules_at_all",
        {"width": 8, "height": 8, "states": _TERRAIN, "rules": []},
        4,
        "25910fe97bd6a8f9",
        "23158309fbd94d87",
    ),
    (
        "tall",
        {"width": 3, "height": 20, "states": _TERRAIN, "rules": _terrain_rules(_DIRS4)},
        9,
        "99410c20a6b05305",
        "cec0ed4c7de5abf6",
    ),
    (
        "wide",
        {"width": 20, "height": 3, "states": _TERRAIN, "rules": _terrain_rules(_DIRS4)},
        9,
        "17c668f0be7be93a",
        "4339fada6cec701c",
    ),
]


@pytest.mark.parametrize(
    ("kwargs", "seed", "grid_digest", "rng_digest"),
    [case[1:] for case in _GOLDENS],
    ids=[case[0] for case in _GOLDENS],
)
def test_a_seed_produces_the_grid_it_always_produced(
    kwargs: dict[str, object],
    seed: int,
    grid_digest: str,
    rng_digest: str,
) -> None:
    """The ten shapes that between them exercise every selection path.

    `tall` and `wide` are both here because the tie-break is row-major
    (`y * width + x`) while the cell list is built column-major, so a
    structure that accidentally ordered by the latter agrees with the
    former on a square grid and disagrees on either oblong one.

    `single_state` and `no_rules_at_all` are the degenerate ends: one
    where every cell starts decided and the heap must drain without
    collapsing anything, and one where nothing ever narrows so every
    choice is made on the tie-break alone.
    """
    rng = RandomStream(seed)

    grid = generate_wfc(rng=rng, **kwargs)  # type: ignore[arg-type]

    assert _grid_digest(grid) == grid_digest
    # Not just the same grid: the same number of draws, in the same order.
    # A selection that collapsed the same cells in a different order could
    # land the same grid while leaving the stream somewhere else, and a
    # caller drawing from `rng` afterwards would diverge.
    assert _state_digest(rng) == rng_digest
