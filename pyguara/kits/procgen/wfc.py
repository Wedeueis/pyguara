"""Wave Function Collapse: constraint-propagation grid generation.

Genre-agnostic like `bsp.py` -- states are caller-defined values (a tile
kind, a biome id, anything hashable), and adjacency is expressed as plain
`AdjacencyRule`s the caller supplies; nothing here knows what a "state"
means. `dungeon.py`'s BSP recipe is the roguelike-room flavor of its
sibling algorithm; a WFC-driven tile palette (cave walls, biome blending)
is this algorithm's own recipe, left to the caller to build.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from pyguara.common.grid import Cell, neighbors4
from pyguara.common.random import RandomStream, weighted_choice

S = TypeVar("S")


class WfcContradictionError(RuntimeError):
    """Every attempt narrowed some cell to zero possible states."""


@dataclass(frozen=True)
class AdjacencyRule(Generic[S]):  # noqa: UP046 -- mypy is pinned to python_version = "3.10" (pyproject.toml)
    """One allowed neighbor pairing.

    Attributes:
        from_state: The state occupying a cell.
        to_state: A state allowed in the neighbor reached by `direction`.
        direction: The offset from the `from_state` cell to that neighbor,
            e.g. `(1, 0)` for "to the east". Directions are not implied
            reciprocal -- a symmetric constraint needs its own rule for
            each direction.
    """

    from_state: S
    to_state: S
    direction: Cell


class _Contradiction(Exception):
    """Internal signal: a cell was narrowed to zero possible states."""


def generate_wfc(
    width: int,
    height: int,
    states: Sequence[S],
    rules: Sequence[AdjacencyRule[S]],
    rng: RandomStream,
    weights: Mapping[S, float] | None = None,
    pinned: Mapping[Cell, S] | None = None,
    neighbor_fn: Callable[[Cell], Sequence[Cell]] = neighbors4,
    max_attempts: int = 20,
) -> dict[Cell, S]:
    """Generate a `width` x `height` grid by Wave Function Collapse.

    Repeatedly collapses the lowest-entropy remaining cell to one of its
    possible states (weighted, via `weights`), then propagates that choice
    through `rules` to narrow every neighbor's possibilities. A rule set
    that paints a cell into zero possible states (a contradiction) restarts
    the whole grid and tries again, up to `max_attempts` -- still
    deterministic overall, since every attempt draws from the same `rng`
    in sequence.

    Args:
        width: Grid width, in cells.
        height: Grid height, in cells.
        states: Every state a cell may end up in. Must be non-empty.
        rules: Adjacency constraints. A `(state, direction)` pair with no
            matching rule leaves that neighbor unconstrained in that
            direction.
        rng: Seeded stream driving every collapse choice.
        weights: Relative odds per state when a cell has several
            possibilities left. Defaults to uniform. A state missing from
            this mapping gets weight 1.0.
        pinned: Cells forced to a specific state before generation starts,
            e.g. a fixed entrance tile. Every key must be in bounds and
            every value must be one of `states`.
        neighbor_fn: Adjacency topology -- `pyguara.common.grid.neighbors4`
            (the default) or `neighbors8` for diagonal adjacency too.
        max_attempts: Retries allowed after a contradiction before giving
            up.

    Returns:
        Every in-bounds cell's final state.

    Raises:
        ValueError: `states` is empty, or `pinned` names an out-of-bounds
            cell or a state not in `states`.
        WfcContradictionError: Every attempt hit a contradiction.
    """
    if not states:
        raise ValueError("generate_wfc: states must not be empty")

    cells = [(x, y) for x in range(width) for y in range(height)]
    in_bounds = set(cells)
    pinned = pinned or {}
    state_set = set(states)
    for cell, state in pinned.items():
        if cell not in in_bounds:
            raise ValueError(f"generate_wfc: pinned cell {cell} is out of bounds")
        if state not in state_set:
            raise ValueError(f"generate_wfc: pinned state {state!r} not in states")

    state_order = {state: index for index, state in enumerate(states)}
    rules_by_from_direction: dict[tuple[S, Cell], set[S]] = {}
    for rule in rules:
        key = (rule.from_state, rule.direction)
        rules_by_from_direction.setdefault(key, set()).add(rule.to_state)

    for _ in range(max_attempts):
        try:
            return _attempt(
                cells=cells,
                width=width,
                in_bounds=in_bounds,
                state_set=state_set,
                state_order=state_order,
                rules_by_from_direction=rules_by_from_direction,
                rng=rng,
                weights=weights,
                pinned=pinned,
                neighbor_fn=neighbor_fn,
            )
        except _Contradiction:
            continue

    raise WfcContradictionError(
        f"generate_wfc: no consistent grid found in {max_attempts} attempts"
    )


def _attempt(
    cells: list[Cell],
    width: int,
    in_bounds: set[Cell],
    state_set: set[S],
    state_order: dict[S, int],
    rules_by_from_direction: dict[tuple[S, Cell], set[S]],
    rng: RandomStream,
    weights: Mapping[S, float] | None,
    pinned: Mapping[Cell, S],
    neighbor_fn: Callable[[Cell], Sequence[Cell]],
) -> dict[Cell, S]:
    possible: dict[Cell, set[S]] = {cell: set(state_set) for cell in cells}

    def propagate(start: Cell) -> None:
        stack = [start]
        while stack:
            cell = stack.pop()
            states_here = possible[cell]
            if len(states_here) != 1:
                continue
            (from_state,) = states_here
            for neighbor in neighbor_fn(cell):
                if neighbor not in in_bounds:
                    continue
                direction = (neighbor[0] - cell[0], neighbor[1] - cell[1])
                allowed = rules_by_from_direction.get((from_state, direction))
                if allowed is None:
                    continue
                before = possible[neighbor]
                after = before & allowed
                if after == before:
                    continue
                if not after:
                    raise _Contradiction
                possible[neighbor] = after
                stack.append(neighbor)

    for cell, state in pinned.items():
        if state not in possible[cell]:
            raise _Contradiction
        possible[cell] = {state}
        propagate(cell)

    while True:
        undecided = [cell for cell in cells if len(possible[cell]) > 1]
        if not undecided:
            break
        undecided.sort(key=lambda c: (len(possible[c]), c[1] * width + c[0]))
        target = undecided[0]
        ordered_states = sorted(possible[target], key=lambda s: state_order[s])
        choices = [
            (state, 1.0 if weights is None else weights.get(state, 1.0))
            for state in ordered_states
        ]
        chosen = weighted_choice(rng, choices)
        possible[target] = {chosen}
        propagate(target)

    return {cell: next(iter(possible[cell])) for cell in cells}
