"""Scenarios and recorded results for the swarm's golden vectors.

`swarm.json` holds every live agent's id, position and velocity after each
scenario, as `float.hex()`, recorded from the native swarm where the Python
reference in `tests/reference/swarm.py` agreed with it exactly. The
comparison is exact: the swarm is f64, sums in the grid's fixed order and
calls no maths function but `sqrt`.

Regenerate with `uv run python -m tests.golden.swarm`, which records what
the native swarm does now.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pyguara.ai.swarm import Swarm, SwarmKind
from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2

VECTORS = Path(__file__).with_name("swarm.json")

DT = 1.0 / 60.0


class SwarmLike(Protocol):
    """What a scenario drives: `Swarm` or `ReferenceSwarm`."""

    def add_kind(self, kind: SwarmKind) -> int: ...  # noqa: D102
    def spawn(  # noqa: D102
        self,
        kind: int,
        positions: list[Vector2],
        velocities: list[Vector2] | None = None,
    ) -> list[int]: ...
    def kill(self, ids: list[int]) -> None: ...  # noqa: D102
    def ids(self) -> list[int]: ...  # noqa: D102
    def set_kind_seek(self, kind: int, target: Vector2 | None) -> None: ...  # noqa: D102
    def set_seek(self, ids: list[int], targets: list[Vector2]) -> None: ...  # noqa: D102
    def set_detail_bands(self, bands: list[tuple[float, int]]) -> None: ...  # noqa: D102
    def set_detail_focus(self, focus: Vector2 | None) -> None: ...  # noqa: D102
    def update(self, dt: float) -> None: ...  # noqa: D102


@dataclass(frozen=True)
class Scenario:
    """A seeded swarm, what happens to it, and for how long."""

    name: str
    count: int
    spread: float
    ticks: int
    seed: int = 1234
    cell_size: float = 64.0
    kinds: tuple[dict[str, float], ...] = ({},)
    kind_seek: bool = False
    own_seek_every: int = 0
    kill_at: int = -1
    respawn_at: int = -1
    detail: tuple[tuple[float, int], ...] = ()

    def build(self, swarm: SwarmLike) -> None:
        """Fill `swarm` with the scenario's agents, deterministically."""
        rng = RandomStream(self.seed)
        kinds = [swarm.add_kind(SwarmKind(**tuning)) for tuning in self.kinds]
        for index in range(self.count):
            position = Vector2(
                rng.uniform(0.0, self.spread), rng.uniform(0.0, self.spread)
            )
            velocity = Vector2(rng.uniform(-40.0, 40.0), rng.uniform(-40.0, 40.0))
            swarm.spawn(kinds[index % len(kinds)], [position], [velocity])
        if self.kind_seek:
            swarm.set_kind_seek(kinds[0], Vector2(self.spread / 2, self.spread / 3))
        if self.own_seek_every:
            chosen = swarm.ids()[:: self.own_seek_every]
            swarm.set_seek(
                chosen,
                [
                    Vector2(self.spread * (i % 3) / 2, self.spread)
                    for i in range(len(chosen))
                ],
            )

    def play(self, swarm: SwarmLike) -> None:
        """Build and tick the scenario on `swarm`."""
        self.build(swarm)
        if self.detail:
            swarm.set_detail_bands(list(self.detail))
        for tick in range(self.ticks):
            if tick == self.kill_at:
                swarm.kill(swarm.ids()[1::3])
            if tick == self.respawn_at:
                swarm.spawn(
                    0,
                    [Vector2(self.spread / 2 + i, self.spread / 2) for i in range(10)],
                )
            if self.detail:
                # A focus crossing the swarm, so agents change band.
                swarm.set_detail_focus(Vector2(self.spread * tick / self.ticks, 0.0))
            swarm.update(DT)


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("sparse", 60, 1500.0, 30),
    Scenario("dense", 120, 300.0, 30),
    Scenario("one-cell", 40, 50.0, 20),
    Scenario("seeking", 60, 600.0, 30, kind_seek=True),
    Scenario("own-targets", 60, 600.0, 30, own_seek_every=4),
    Scenario(
        "two-kinds",
        80,
        350.0,
        30,
        seed=9,
        kinds=(
            {},
            {
                "max_speed": 90.0,
                "max_force": 30.0,
                "mass": 2.5,
                "neighbor_radius": 120.0,
                "separation_radius": 40.0,
                "cohesion_weight": 0.4,
                "alignment_weight": 1.6,
                "separation_weight": 2.2,
                "seek_weight": 0.0,
            },
        ),
        kind_seek=True,
    ),
    Scenario("killed-and-respawned", 90, 300.0, 40, kill_at=10, respawn_at=20),
    Scenario("small-cells", 60, 400.0, 20, cell_size=16.0),
    Scenario(
        "detail-bands",
        120,
        400.0,
        40,
        detail=((120.0, 1), (260.0, 3), (400.0, 5)),
        kind_seek=True,
    ),
    Scenario("long", 40, 400.0, 240),
)


def native(scenario: Scenario) -> Swarm:
    """Play a scenario on the native swarm."""
    swarm = Swarm(cell_size=scenario.cell_size)
    scenario.play(swarm)
    return swarm


def encode(swarm: Swarm) -> list[list[str | int]]:
    """`[id, x, y, vx, vy]` per live agent, floats as hex, in slot order."""
    ids = swarm.ids()
    return [
        [agent, position.x.hex(), position.y.hex(), velocity.x.hex(), velocity.y.hex()]
        for agent, position, velocity in zip(
            ids, swarm.positions(ids), swarm.velocities(ids), strict=True
        )
    ]


def load() -> dict[str, list[list[str | int]]]:
    """Read the recording."""
    recorded: dict[str, list[list[str | int]]] = json.loads(VECTORS.read_text())
    return recorded


def record() -> None:
    """Write what the native swarm does now to `swarm.json`."""
    vectors = {scenario.name: encode(native(scenario)) for scenario in SCENARIOS}
    VECTORS.write_text(json.dumps(vectors, indent=0) + "\n")


if __name__ == "__main__":
    record()
