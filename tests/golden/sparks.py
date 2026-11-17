"""Scenarios and recorded results for the spark pool's golden vectors.

`sparks.json` holds what the Rust pool held and drew after each
scenario: every slot, the primitives a plain renderer was sent, and the
rows a batching renderer was sent. It was recorded where the Python
pool agreed to the parity suite's tolerance.

Regenerate with `uv run python -m tests.golden.sparks`, which records
what the Rust pool does now.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.graphics.types import ShapeBatch
from pyguara.graphics.vfx.sparks import Sparks

VECTORS = Path(__file__).with_name("sparks.json")

TOLERANCE = 1e-3
"""How far a value may sit from its recording, in pixels or radians.

Not zero: a burst's velocity comes from `math.cos` and a packed row's
angle from the platform's `atan2`, and neither is the same to the last
bit on every platform.
"""

DT = 1.0 / 60.0
OFFSET = Vector2(7.0, -3.0)


@dataclass(frozen=True)
class Burst:
    """One `Sparks.burst` call, then `ticks` updates."""

    count: int
    ticks: int
    position: tuple[float, float] = (40.0, 15.0)
    color: tuple[int, int, int, int] = (255, 180, 60, 255)
    speed: float = 160.0
    speed_jitter: float = 0.55
    direction: float | None = None
    spread: float = math.tau
    life: float = 0.55
    radius: float = 3.0
    gravity: float = 220.0
    drag: float = 0.92
    streak: bool = False


@dataclass(frozen=True)
class Scenario:
    """A pool, a seed, and the bursts played into it in order."""

    name: str
    capacity: int
    seed: int
    bursts: tuple[Burst, ...]


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("dots", 16, 99, (Burst(6, 20, life=1.0, speed=80.0),)),
    Scenario("streaks", 16, 99, (Burst(6, 20, life=1.0, speed=80.0, streak=True),)),
    Scenario("long-flight", 16, 5, (Burst(8, 100, life=100.0, speed=120.0),)),
    Scenario(
        "cone",
        32,
        7,
        (Burst(20, 10, direction=math.pi / 3, spread=0.5, life=2.0),),
    ),
    Scenario(
        "overflow-then-refill",
        8,
        3,
        (Burst(40, 60, life=0.05), Burst(4, 5, speed=100.0, life=5.0)),
    ),
    Scenario(
        "mixed",
        24,
        11,
        (
            Burst(8, 12, life=1.5, radius=4.5, drag=0.8, gravity=0.0),
            Burst(8, 12, life=1.5, streak=True, color=(40, 200, 255, 128)),
            Burst(4, 3, life=0.5, position=(-20.0, 300.0), speed_jitter=0.0),
        ),
    ),
    Scenario("expiring", 16, 2, (Burst(10, 7, life=0.12, speed=10.0),)),
)


class _Recorder:
    """A renderer that records primitives and cannot take a batch."""

    def __init__(self) -> None:
        self.circles: list[list[float]] = []
        self.lines: list[list[float]] = []

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Record a circle as numbers."""
        self.circles.append([center.x, center.y, radius, *color])

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Record a line as numbers."""
        self.lines.append([start.x, start.y, end.x, end.y, width, *color])


class _BatchRecorder(_Recorder):
    """A renderer that takes batches, and records their rows."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[float]] = []

    def render_shapes(self, batch: ShapeBatch) -> None:
        """Record every row of a batch."""
        self.rows.extend([float(value) for value in row] for row in batch.instances)


def play(scenario: Scenario, pool: Any) -> None:
    """Play a scenario's bursts and ticks into `pool`.

    Args:
        scenario: What to play.
        pool: A `Sparks` or anything with its `burst` and `update`.
    """
    for burst in scenario.bursts:
        pool.burst(
            Vector2(*burst.position),
            Color(*burst.color),
            count=burst.count,
            speed=burst.speed,
            speed_jitter=burst.speed_jitter,
            direction=burst.direction,
            spread=burst.spread,
            life=burst.life,
            radius=burst.radius,
            gravity=burst.gravity,
            drag=burst.drag,
            streak=burst.streak,
        )
        for _ in range(burst.ticks):
            pool.update(DT)


def drawn(pool: Any) -> dict[str, list[list[float]]]:
    """Return the primitives `pool` sends a renderer that cannot batch."""
    recorder = _Recorder()
    pool.render(recorder, OFFSET)
    return {"circles": recorder.circles, "lines": recorder.lines}


def measure(scenario: Scenario) -> dict[str, Any]:
    """Play a scenario into the Rust pool and return what it holds and draws.

    Args:
        scenario: What to play.

    Returns:
        `live`, the live count; `slots`, each slot's position, velocity,
        life and flags; `circles` and `lines`, the unbatched primitives;
        and `rows`, the batched ones.
    """
    pool = Sparks(scenario.capacity, RandomStream(scenario.seed))
    play(scenario, pool)
    batched = _BatchRecorder()
    pool.render(batched, OFFSET)
    slots = [
        [float(value) for value in pool._native.slot(index)]
        for index in range(scenario.capacity)
    ]
    return {
        "live": pool.live_count,
        "slots": slots,
        "rows": batched.rows,
        **drawn(pool),
    }


def load() -> dict[str, dict[str, Any]]:
    """Return the recorded results by scenario name."""
    recorded: dict[str, dict[str, Any]] = json.loads(
        VECTORS.read_text(encoding="utf-8")
    )
    return recorded


def main() -> None:
    """Write `sparks.json` from the Rust pool."""
    lines = [
        f"{json.dumps(s.name)}: {json.dumps(measure(s), separators=(',', ':'))}"
        for s in SCENARIOS
    ]
    VECTORS.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    print(f"wrote {len(lines)} scenarios to {VECTORS}")


if __name__ == "__main__":
    main()
