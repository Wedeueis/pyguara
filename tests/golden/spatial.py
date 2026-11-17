"""Scripts and recorded answers for the spatial hash's golden vectors.

`spatial.json` holds, for each script here, the sorted answer to every
query it asks, recorded from the Rust index while the Python index still
shipped and gave identical membership. Membership is exact, so the
comparison is too. Order is not recorded: neither index defines it.

Regenerate with `uv run python -m tests.golden.spatial`, which records
what the Rust index answers now.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyguara.common.random import RandomStream
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Rect, Vector2

VECTORS = Path(__file__).with_name("spatial.json")

FULL = 0xFFFFFFFF
MASKS = (0b01, 0b10, FULL)


@dataclass(frozen=True)
class Script:
    """A seeded run of writes, with queries asked between them."""

    name: str
    cell_size: float
    steps: int
    seed: int
    spread: float
    radius: float
    writes_per_query: int = 1
    fill: int = 0


SCRIPTS: tuple[Script, ...] = (
    Script("fill-then-sweep", 64.0, 60, 1, 800.0, 90.0, writes_per_query=0, fill=300),
    Script("one-write-per-query", 64.0, 300, 2, 600.0, 80.0),
    Script("bursts-past-the-pending-limit", 64.0, 40, 3, 600.0, 120.0, 25, fill=200),
    Script("small-cells", 8.0, 200, 4, 200.0, 20.0, 2, fill=50),
    Script("large-cells", 512.0, 200, 5, 3000.0, 400.0, 3, fill=80),
    Script("negative-and-boundaries", 32.0, 200, 6, 256.0, 32.0, 2, fill=60),
)


def _point(rng: RandomStream, script: Script) -> Vector2:
    """A position in the script's square, snapped to cell edges a third of the time."""
    half = script.spread / 2
    x, y = rng.uniform(-half, half), rng.uniform(-half, half)
    if rng.uniform(0.0, 1.0) < 1 / 3:
        size = script.cell_size
        x, y = round(x / size) * size, round(y / size) * size
    return Vector2(x, y)


def play(script: Script, index: Any) -> list[list[list[str]]]:
    """Run a script against `index` and return every answer, sorted.

    Args:
        script: The writes and queries to make.
        index: A `SpatialHash`, or anything with its methods.

    Returns:
        Per query step, the sorted answers of `query_radius`, a masked
        `query_radius`, `query_point` and `query_rect`.
    """
    rng = RandomStream(script.seed)
    live: list[str] = []
    for number in range(script.fill):
        key = f"fill-{number}"
        index.insert(key, _point(rng, script), MASKS[number % 3])
        live.append(key)

    answers: list[list[list[str]]] = []
    for step in range(script.steps):
        for write in range(script.writes_per_query):
            action = rng.uniform(0.0, 1.0)
            if action < 0.5 or not live:
                key = f"key-{step}-{write}"
                index.insert(key, _point(rng, script), MASKS[(step + write) % 3])
                live.append(key)
            elif action < 0.8:
                key = live[int(rng.uniform(0, len(live) - 1e-9))]
                index.insert(key, _point(rng, script), MASKS[step % 3])
            else:
                index.remove(live.pop(int(rng.uniform(0, len(live) - 1e-9))))

        probe = _point(rng, script)
        width = int(script.radius * 2)
        rect = Rect(int(probe.x) - width // 2, int(probe.y) - width // 3, width, width)
        answers.append(
            [
                sorted(index.query_radius(probe, script.radius)),
                sorted(index.query_radius(probe, script.radius, 0b10)),
                sorted(index.query_point(probe)),
                sorted(index.query_rect(rect)),
            ]
        )
    return answers


def load() -> dict[str, list[list[list[str]]]]:
    """Return the recorded answers by script name."""
    recorded: dict[str, list[list[list[str]]]] = json.loads(
        VECTORS.read_text(encoding="utf-8")
    )
    return recorded


def main() -> None:
    """Write `spatial.json` from the Rust index."""
    lines = [
        f"{json.dumps(s.name)}: "
        f"{json.dumps(play(s, SpatialHash[str](s.cell_size)), separators=(',', ':'))}"
        for s in SCRIPTS
    ]
    VECTORS.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    print(f"wrote {len(lines)} scripts to {VECTORS}")


if __name__ == "__main__":
    main()
