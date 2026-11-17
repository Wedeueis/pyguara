"""Scenarios and recorded results for the flocking solver's golden vectors.

`flocking.json` holds every agent's position and velocity after each
scenario, as `float.hex()`, recorded from the Rust solver while the
Python path still shipped and agreed with it to summation noise. The
comparison is exact: the solver is f64, sweeps in a fixed order and
calls no platform maths function.

Regenerate with `uv run python -m tests.golden.flocking`, which records
what the Rust solver does now.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager

VECTORS = Path(__file__).with_name("flocking.json")

DT = 1.0 / 60.0


@dataclass(frozen=True)
class Scenario:
    """A seeded flock, how it is ticked, and for how long."""

    name: str
    count: int
    spread: float
    ticks: int
    seed: int = 1234
    cell_size: float = 64.0
    groups: int = 1
    integrate: bool = True
    seek_every: int = 0
    disable_every: int = 0
    agent: dict[str, float] = field(default_factory=dict)

    def world(self) -> EntityManager:
        """Build the scenario's flock, deterministically."""
        rng = RandomStream(self.seed)
        manager = EntityManager()
        for index in range(self.count):
            entity = manager.create_entity()
            entity.add_component(
                Transform(
                    position=Vector2(
                        rng.uniform(0.0, self.spread), rng.uniform(0.0, self.spread)
                    )
                )
            )
            agent = FlockingAgent(
                velocity=Vector2(rng.uniform(-40.0, 40.0), rng.uniform(-40.0, 40.0)),
                **self.agent,  # type: ignore[arg-type]
            )
            if self.seek_every and index % self.seek_every == 0:
                agent.seek_target = Vector2(self.spread / 2, self.spread / 3)
                agent.seek_weight = 0.7
            if self.disable_every and index % self.disable_every == 0:
                agent.enabled = False
            entity.add_component(agent)
        return manager


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("sparse", 60, 1500.0, 30),
    Scenario("dense", 80, 300.0, 30),
    Scenario("one-cell", 40, 50.0, 20),
    Scenario("seeking", 60, 600.0, 30, seek_every=3),
    Scenario("some-disabled", 60, 400.0, 30, disable_every=7),
    Scenario("staggered", 60, 400.0, 31, groups=4),
    Scenario("steer-only", 60, 400.0, 30, integrate=False),
    Scenario("small-cells", 60, 400.0, 20, cell_size=16.0),
    Scenario(
        "tuned",
        50,
        350.0,
        30,
        seed=9,
        agent={
            "max_speed": 90.0,
            "max_force": 30.0,
            "mass": 2.5,
            "neighbor_radius": 120.0,
            "separation_radius": 40.0,
            "cohesion_weight": 0.4,
            "alignment_weight": 1.6,
            "separation_weight": 2.2,
        },
    ),
    Scenario("long", 40, 400.0, 240),
)


def state(manager: EntityManager) -> list[list[float]]:
    """Return `[x, y, velocity_x, velocity_y]` per agent, in sweep order."""
    rows: list[list[float]] = []
    for entity in manager.get_entities_with_cached(FlockingAgent, Transform):
        position = entity.get_component(Transform).position
        velocity = entity.get_component(FlockingAgent).velocity
        rows.append([position.x, position.y, velocity.x, velocity.y])
    return rows


def play(scenario: Scenario, system_type: Any = FlockingSystem) -> list[list[float]]:
    """Tick a scenario's flock and return its final state.

    Args:
        scenario: What to build and tick.
        system_type: `FlockingSystem`, or anything constructed like it.

    Returns:
        One `[x, y, velocity_x, velocity_y]` row per agent.
    """
    manager = scenario.world()
    system = system_type(
        manager,
        cell_size=scenario.cell_size,
        groups=scenario.groups,
        integrate=scenario.integrate,
    )
    for _ in range(scenario.ticks):
        system.update(DT)
    return state(manager)


def encode(rows: list[list[float]]) -> list[list[str]]:
    """Turn rows of floats into rows of `float.hex()` strings."""
    return [[float(value).hex() for value in row] for row in rows]


def load() -> dict[str, list[list[str]]]:
    """Return the recorded rows by scenario name."""
    recorded: dict[str, list[list[str]]] = json.loads(
        VECTORS.read_text(encoding="utf-8")
    )
    return recorded


def main() -> None:
    """Write `flocking.json` from the Rust solver."""
    lines = [
        f"{json.dumps(s.name)}: {json.dumps(encode(play(s)), separators=(',', ':'))}"
        for s in SCENARIOS
    ]
    VECTORS.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    print(f"wrote {len(lines)} scenarios to {VECTORS}")


if __name__ == "__main__":
    main()
