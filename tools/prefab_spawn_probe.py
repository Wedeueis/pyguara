"""How long prefabs take to spawn from a spawn table.

    uv run python tools/prefab_spawn_probe.py
    uv run python tools/prefab_spawn_probe.py --count 10000

Spawns Correição's ground, a `Transform` and a `Sprite` per prefab, picked
from `ground.spawn.json`, through `PrefabFactory.spawn`, each at its own
position. Textures are stand-ins, so the figure is the factory's own cost.
Best of five, in milliseconds, and per spawn in microseconds.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyguara.common.components import Transform  # noqa: E402
from pyguara.common.random import RandomStream  # noqa: E402
from pyguara.common.types import Vector2  # noqa: E402
from pyguara.ecs.manager import EntityManager  # noqa: E402
from pyguara.graphics.components.sprite import Sprite  # noqa: E402
from pyguara.prefabs import (  # noqa: E402
    ComponentRegistry,
    PrefabCache,
    PrefabFactory,
    load_spawn_table,
)
from pyguara.resources.types import Texture  # noqa: E402

TABLE = "examples/correicao/prefabs/ground.spawn.json"


class _Texture(Texture):
    @property
    def width(self) -> int:
        return 16

    @property
    def height(self) -> int:
        return 16

    @property
    def native_handle(self) -> object:
        return None


def probe(count: int) -> float:
    """Spawn `count` prefabs into a fresh world and return the seconds taken."""
    registry = ComponentRegistry()
    registry.register(Transform)
    registry.register(Sprite)
    registry.register_type_converter(Texture, _Texture)
    factory = PrefabFactory(EntityManager(), registry, PrefabCache().load)
    table = load_spawn_table(TABLE)
    points = [Vector2(i, i) for i in range(count)]
    start = time.perf_counter()
    factory.spawn(table, RandomStream(1), count=count, positions=points)
    return time.perf_counter() - start


def main() -> None:
    """Print the best of five runs."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=4000)
    count = parser.parse_args().count
    best = min(probe(count) for _ in range(5))
    print(f"{count} spawns: {best * 1e3:.0f} ms, {best * 1e6 / count:.0f} us each")


if __name__ == "__main__":
    main()
