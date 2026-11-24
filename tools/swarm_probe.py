"""A crowded raid stepped by the swarm and by the flocking solver.

    uv run python tools/swarm_probe.py                  # 5,000 and 10,000
    uv run python tools/swarm_probe.py --ants 20000
    uv run python tools/swarm_probe.py --near-share 0.2   # level of detail
    uv run python tools/swarm_probe.py --threads 4 --threads 0   # 0: shared pool

Builds the same raid for both: agents in a disc sized for about 60
flockmates each, seeking its centre with Correição's tuning and eight
speeds, which crowds them to 75 to 85 flockmates, as dense as Correição's
ants get in play. Both settle for 30 ticks, then the best
of 30 is kept. The solver is the one inside `FlockingSystem`, fed packed
rows directly. Its row-conversion cost, measured with every agent disabled,
is subtracted, so its figure is the sweep alone, the part no Python change
can remove. The swarm's figure is its whole tick, at full detail and with
each `--near-share`: a band around the raid's centre holding that share of
it steers every tick, and the rest every fourth. Each row runs on one
thread unless `--threads` adds rows on more. Milliseconds per tick.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyguara.ai.swarm import Swarm, SwarmKind  # noqa: E402
from pyguara.common.random import RandomStream  # noqa: E402
from pyguara.common.types import Vector2  # noqa: E402
from pyguara.native import require_extension  # noqa: E402

DT = 1 / 60
FLOCKMATES = 60
RADIUS = 26.0
TUNING = {
    "max_force": 300.0,
    "neighbor_radius": RADIUS,
    "separation_radius": 12.0,
    "cohesion_weight": 0.2,
    "alignment_weight": 0.5,
    "separation_weight": 2.2,
    "seek_weight": 1.0,
}


def _raid(ants: int) -> tuple[list[Vector2], list[Vector2], list[float]]:
    """Positions, velocities and speeds for a disc of the right density."""
    disc = math.sqrt(ants * RADIUS * RADIUS / FLOCKMATES)
    rng = RandomStream(5)
    positions, velocities, speeds = [], [], []
    for _ in range(ants):
        r = disc * math.sqrt(rng.uniform(0, 1))
        angle = rng.uniform(0, math.tau)
        positions.append(
            Vector2(3000 + r * math.cos(angle), 3000 + r * math.sin(angle))
        )
        velocities.append(Vector2(rng.uniform(-40, 40), rng.uniform(-40, 40)))
        speeds.append(85.0 + 55.0 * rng.randint(0, 7) / 7)
    return positions, velocities, speeds


def probe(
    ants: int, near_share: float = 1.0, threads: int | None = 1
) -> dict[str, float]:
    """Time both solvers on one raid size."""
    positions, velocities, speeds = _raid(ants)
    centre = Vector2(3000, 3000)

    swarm = Swarm(cell_size=RADIUS, threads=threads)
    kinds = {
        speed: swarm.add_kind(SwarmKind(max_speed=speed, **TUNING))
        for speed in sorted(set(speeds))
    }
    for position, velocity, speed in zip(positions, velocities, speeds, strict=True):
        swarm.spawn(kinds[speed], [position], [velocity])
    for kind in kinds.values():
        swarm.set_kind_seek(kind, centre)
    if near_share < 1.0:
        distances = sorted(abs(point - centre) for point in positions)
        near = distances[int(near_share * (ants - 1))]
        swarm.set_detail_bands([(near, 1), (near + 1.0, 4)])
        swarm.set_detail_focus(centre)

    solver: Any = require_extension("swarm_probe").NativeFlockingSolver()
    tuning = (300.0, 1.0, RADIUS, 12.0, 0.2, 0.5, 2.2, 1.0, centre.x, centre.y)

    def pack(points: list[Vector2], moving: list[Vector2]) -> list[float]:
        flat: list[float] = []
        for point, velocity, speed in zip(points, moving, speeds, strict=True):
            flat += (point.x, point.y, velocity.x, velocity.y, speed, *tuning)
        return flat

    flat = pack(positions, velocities)
    on, off = [True] * ants, [False] * ants
    for _ in range(30):
        swarm.update(DT)
        rows = solver.tick(DT, RADIUS, 1, 0, flat, on, True)
        flat = pack([row[0] for row in rows], [row[1] for row in rows])

    best = {"swarm": math.inf, "solver": math.inf, "conversions": math.inf}
    for _ in range(30):
        for key, step in (
            ("swarm", lambda: swarm.update(DT)),
            ("solver", lambda: solver.tick(DT, RADIUS, 1, 0, flat, on, True)),
            ("conversions", lambda: solver.tick(DT, RADIUS, 1, 0, flat, off, True)),
        ):
            start = time.perf_counter()
            step()
            best[key] = min(best[key], (time.perf_counter() - start) * 1e3)
    counts = swarm.neighbour_counts()
    return {
        "swarm": best["swarm"],
        "sweep": best["solver"] - best["conversions"],
        "flockmates": sum(counts) / len(counts),
    }


def main() -> None:
    """Print one row per raid size."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ants", type=int, action="append")
    parser.add_argument("--near-share", type=float, action="append")
    parser.add_argument("--threads", type=int, action="append")
    arguments = parser.parse_args()
    sizes = arguments.ants or [5000, 10000]
    shares = [1.0, *(arguments.near_share or [])]
    pools: list[int | None] = [1, *((t or None) for t in (arguments.threads or []))]
    print(
        f"{'ants':>6}  {'near':>5}  {'threads':>7}  {'solver sweep':>12}  "
        f"{'swarm tick':>10}  flockmates"
    )
    for ants in sizes:
        for share in shares:
            for threads in pools:
                row = probe(ants, share, threads)
                print(
                    f"{ants:>6}  {share:>5.0%}  {threads or 'shared':>7}  "
                    f"{row['sweep']:>12.2f}  {row['swarm']:>10.2f}  "
                    f"{row['flockmates']:.1f}"
                )


if __name__ == "__main__":
    main()
