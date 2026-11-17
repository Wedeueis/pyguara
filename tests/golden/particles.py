"""Scenarios and recorded results for the particle pool's golden vectors.

`particles.json` holds what the Rust pool held and handed a renderer
after each scenario: every slot, and each texture's batch of screen
positions and tints. It was recorded where the Python pool agreed to
the parity suite's tolerance.

Regenerate with `uv run python -m tests.golden.particles`, which records
what the Rust pool does now.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.graphics.components.particles import ParticleSystem

VECTORS = Path(__file__).with_name("particles.json")

TOLERANCE = 1e-3
"""How far a value may sit from its recording, in pixels or degrees.

Not zero: an emitted velocity comes from `Vector2.rotate_degrees`, whose
sine and cosine are not the same to the last bit on every platform.
"""

DT = 1.0 / 60.0
ZOOM = 1.5
SCREEN_OFFSET = (10.0, -4.0)

Rgba = tuple[int, int, int, int]


@dataclass(frozen=True)
class Emit:
    """One `ParticleSystem.emit` call, then `ticks` updates."""

    count: int
    ticks: int
    texture: int = 0
    position: tuple[float, float] = (5.0, 5.0)
    speed: float = 100.0
    spread: float = 360.0
    life: float = 1.0
    acceleration: tuple[float, float] = (0.0, 0.0)
    damping: float = 1.0
    angular_velocity: float = 0.0
    scale: tuple[float, float] = (1.0, 1.0)
    scale_velocity: tuple[float, float] = (0.0, 0.0)
    color_start: Rgba | None = None
    color_end: Rgba | None = None


@dataclass(frozen=True)
class Scenario:
    """A pool, a seed, and the emissions played into it in order."""

    name: str
    capacity: int
    seed: int
    emits: tuple[Emit, ...]


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("plain", 16, 99, (Emit(8, 20, life=2.0),)),
    Scenario(
        "gravity-and-damping",
        16,
        5,
        (Emit(8, 100, speed=120.0, life=100.0, damping=0.99, acceleration=(0, 300)),),
    ),
    Scenario(
        "tinted-a-third-through",
        16,
        7,
        (
            Emit(
                6,
                20,
                speed=40.0,
                color_start=(255, 0, 0, 255),
                color_end=(0, 0, 255, 0),
            ),
        ),
    ),
    Scenario(
        "two-textures",
        16,
        11,
        (
            Emit(4, 5, texture=0, life=10.0, speed=30.0),
            Emit(3, 5, texture=1, life=10.0, position=(50.0, 50.0), spread=45.0),
            Emit(
                2,
                5,
                texture=0,
                life=10.0,
                color_start=(9, 9, 9, 9),
                color_end=(1, 2, 3, 4),
            ),
        ),
    ),
    Scenario(
        "overflow-then-refill",
        8,
        3,
        (Emit(40, 10, speed=50.0, life=0.05), Emit(4, 5, life=5.0)),
    ),
    Scenario(
        "spin-and-grow",
        16,
        13,
        (
            Emit(
                5,
                30,
                life=3.0,
                angular_velocity=90.0,
                scale=(0.5, 2.0),
                scale_velocity=(0.25, -0.5),
            ),
        ),
    ),
    Scenario("last-tick-alive", 16, 2, (Emit(10, 5, life=0.1, speed=10.0),)),
    Scenario("expired", 16, 2, (Emit(10, 7, life=0.1, speed=10.0),)),
)


class _Texture:
    """A stand-in a pool can hold; only its identity is used."""

    def __init__(self, index: int) -> None:
        self.index = index


class _Backend:
    """A renderer that records the batches it is handed."""

    width = 800
    height = 600

    def __init__(self) -> None:
        self.batches: list[dict[str, Any]] = []

    def render_batch(self, batch: Any) -> None:
        """Record one batch as plain values."""
        self.batches.append(
            {
                "texture": batch.texture.index,
                "destinations": [[float(x), float(y)] for x, y in batch.destinations],
                "tinted": bool(batch.colors_enabled),
                "colors": [list(color) for color in batch.colors],
            }
        )


class _Camera:
    """A camera with a fixed zoom and screen offset."""

    zoom = ZOOM

    def screen_offset(self, viewport: Any) -> Vector2:
        """Return the fixed offset, whatever the viewport."""
        return Vector2(*SCREEN_OFFSET)


def play(scenario: Scenario, pool: Any) -> None:
    """Play a scenario's emissions and ticks into `pool`.

    Args:
        scenario: What to play.
        pool: A `ParticleSystem` or anything with its `emit` and `update`.
    """
    textures = [_Texture(0), _Texture(1)]
    for emit in scenario.emits:
        pool.emit(
            textures[emit.texture],
            Vector2(*emit.position),
            count=emit.count,
            speed=emit.speed,
            spread=emit.spread,
            life=emit.life,
            acceleration=Vector2(*emit.acceleration),
            damping=emit.damping,
            angular_velocity=emit.angular_velocity,
            scale=Vector2(*emit.scale),
            scale_velocity=Vector2(*emit.scale_velocity),
            color_start=emit.color_start,
            color_end=emit.color_end,
        )
        for _ in range(emit.ticks):
            pool.update(DT)


def drawn(pool: Any) -> list[dict[str, Any]]:
    """Return the batches `pool` hands a renderer, sorted by texture."""
    backend = _Backend()
    pool.render(backend, _Camera())
    return sorted(backend.batches, key=lambda batch: batch["texture"])


def measure(scenario: Scenario) -> dict[str, Any]:
    """Play a scenario into the Rust pool and return what it holds and draws.

    Args:
        scenario: What to play.

    Returns:
        `live`, the live count; `slots`, each slot's position, velocity,
        life, rotation and active flag; and `batches`, one per texture.
    """
    pool = ParticleSystem(scenario.capacity, RandomStream(scenario.seed))
    play(scenario, pool)
    slots = [
        [float(value) for value in pool._native.slot(index)]
        for index in range(scenario.capacity)
    ]
    return {"live": pool.live_count, "slots": slots, "batches": drawn(pool)}


def load() -> dict[str, dict[str, Any]]:
    """Return the recorded results by scenario name."""
    recorded: dict[str, dict[str, Any]] = json.loads(
        VECTORS.read_text(encoding="utf-8")
    )
    return recorded


def main() -> None:
    """Write `particles.json` from the Rust pool."""
    lines = [
        f"{json.dumps(s.name)}: {json.dumps(measure(s), separators=(',', ':'))}"
        for s in SCENARIOS
    ]
    VECTORS.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    print(f"wrote {len(lines)} scenarios to {VECTORS}")


if __name__ == "__main__":
    main()
