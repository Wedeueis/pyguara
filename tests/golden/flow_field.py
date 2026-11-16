"""Scenarios and recorded results for the flow field's golden vectors.

`flow_field.json` holds, for each scenario here, the cost of every cell
and the steering vector at every cell centre, as the Python and Rust
stores last agreed on them. Floats are stored as `float.hex()` so the
comparison is exact.

Regenerate with `uv run python -m tests.golden.flow_field`. That writes
what `tests.reference.flow_field` computes, so only do it after reading
why the recorded values should change.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pyguara.ai.pathfinding.grid import GridGraph, GridNode
from pyguara.common.types import Vector2

VECTORS = Path(__file__).with_name("flow_field.json")


class Field(Protocol):
    """What a scenario needs of a flow field, reference or Rust."""

    def recompute(
        self, goals: list[GridNode], max_cost: float | None = None
    ) -> object: ...

    def cost_at(self, cell: GridNode) -> float: ...

    def vector_at(
        self, world_pos: Vector2, cell_size: float, offset: Vector2 = ...
    ) -> Vector2: ...


@dataclass(frozen=True)
class Scenario:
    """One grid, one set of goals, and how the field is queried."""

    name: str
    width: int
    height: int
    goals: tuple[GridNode, ...]
    allow_diagonal: bool = True
    max_cost: float | None = None
    cell_size: float = 32.0
    offset: tuple[float, float] = (0.0, 0.0)
    wall_seed: int | None = None
    wall_density: float = 0.0
    weight_density: float = 0.0
    walls: tuple[GridNode, ...] = ()
    weights: tuple[tuple[GridNode, float], ...] = field(default=())

    def graph(self) -> GridGraph:
        """Build the scenario's grid, deterministically."""
        graph = GridGraph(self.width, self.height, allow_diagonal=self.allow_diagonal)
        if self.wall_seed is not None:
            rng = random.Random(self.wall_seed)
            for y in range(self.height):
                for x in range(self.width):
                    if rng.random() < self.wall_density:
                        graph.walls.add((x, y))
                    elif rng.random() < self.weight_density:
                        graph.weights[(x, y)] = rng.choice([0.5, 2.0, 3.7])
        graph.walls.update(self.walls)
        graph.weights.update(dict(self.weights))
        for goal in self.goals:
            graph.walls.discard(goal)
        return graph


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("open-diagonal", 12, 12, ((6, 6),)),
    Scenario("open-orthogonal", 12, 12, ((6, 6),), allow_diagonal=False),
    Scenario("maze", 24, 24, ((12, 12),), wall_seed=1, wall_density=0.25),
    Scenario(
        "maze-weighted",
        24,
        24,
        ((12, 12),),
        wall_seed=2,
        wall_density=0.2,
        weight_density=0.2,
    ),
    Scenario("two-goals", 16, 16, ((0, 0), (15, 15)), wall_seed=3, wall_density=0.15),
    Scenario("cutoff", 16, 16, ((8, 8),), max_cost=5.0),
    Scenario(
        "awkward-world",
        16,
        16,
        ((8, 8),),
        cell_size=33.3,
        offset=(7.7, -11.1),
        walls=((8, 7), (7, 8), (3, 3)),
    ),
    Scenario(
        "tiny-far-world",
        16,
        16,
        ((8, 8),),
        cell_size=0.1,
        offset=(-1e5, 1e5),
        walls=((8, 7), (7, 8), (3, 3)),
    ),
    Scenario(
        "infinite-weight",
        8,
        8,
        ((0, 0),),
        allow_diagonal=False,
        weights=(((3, 3), math.inf),),
    ),
    Scenario("walled-off", 8, 8, ((0, 0),), walls=tuple((4, y) for y in range(8))),
)


def measure(scenario: Scenario, flow: Field) -> dict[str, Any]:
    """Run a scenario and return every cell's cost and direction.

    Args:
        scenario: What to compute and how to query it.
        flow: The field to ask, built over `scenario.graph()`.

    Returns:
        `costs` and `directions`, row-major, as indices into `values`,
        a table of the distinct floats in `float.hex()` form.
    """
    flow.recompute(list(scenario.goals), max_cost=scenario.max_cost)
    offset = Vector2(*scenario.offset)
    size = scenario.cell_size

    values: dict[str, int] = {}

    def index(number: float) -> int:
        return values.setdefault(float(number).hex(), len(values))

    costs: list[int] = []
    directions: list[list[int]] = []
    for y in range(scenario.height):
        for x in range(scenario.width):
            costs.append(index(flow.cost_at((x, y))))
            centre = Vector2(
                x * size + size / 2 + offset.x, y * size + size / 2 + offset.y
            )
            vector = flow.vector_at(centre, size, offset)
            directions.append([index(vector.x), index(vector.y)])
    return {"values": list(values), "costs": costs, "directions": directions}


def load() -> dict[str, dict[str, Any]]:
    """Return the recorded results by scenario name."""
    recorded: dict[str, dict[str, Any]] = json.loads(
        VECTORS.read_text(encoding="utf-8")
    )
    return recorded


def main() -> None:
    """Write `flow_field.json` from the Python reference."""
    from tests.reference.flow_field import ReferenceFlowField

    recorded = {
        scenario.name: measure(scenario, ReferenceFlowField(scenario.graph()))
        for scenario in SCENARIOS
    }
    lines = [
        f"{json.dumps(name)}: {json.dumps(result, separators=(',', ':'))}"
        for name, result in recorded.items()
    ]
    VECTORS.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    print(f"wrote {len(recorded)} scenarios to {VECTORS}")


if __name__ == "__main__":
    main()
