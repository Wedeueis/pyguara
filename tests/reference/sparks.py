"""The spark pool as plain Python, for the Rust one to be held to.

One object per spark, in f64. `Sparks` keeps the same pool in Rust as
f32 arrays, so the two agree to a tolerance, not bit for bit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import IRenderer


@dataclass(slots=True)
class Spark:
    """One pooled particle. Inactive entries keep their storage."""

    position: Vector2 = field(default_factory=Vector2.zero)
    velocity: Vector2 = field(default_factory=Vector2.zero)
    life: float = 0.0
    life_total: float = 1.0
    radius: float = 2.0
    color: Color = field(default_factory=lambda: Color(255, 255, 255))
    gravity: float = 0.0
    drag: float = 1.0
    streak: bool = False
    active: bool = False


class ReferenceSparks:
    """Does what `Sparks` does, one Python object per spark."""

    def __init__(self, capacity: int = 320, rng: RandomStream | None = None) -> None:
        """Pre-allocate `capacity` sparks."""
        self._capacity = capacity
        self._next = 0
        self._rng = rng if rng is not None else RandomStream()
        self.pool: list[Spark] = [Spark() for _ in range(capacity)]

    @property
    def live_count(self) -> int:
        """How many sparks are currently alive."""
        return sum(1 for spark in self.pool if spark.active)

    def burst(
        self,
        position: Vector2,
        color: Color,
        *,
        count: int = 12,
        speed: float = 160.0,
        speed_jitter: float = 0.55,
        direction: float | None = None,
        spread: float = math.tau,
        life: float = 0.55,
        radius: float = 3.0,
        gravity: float = 220.0,
        drag: float = 0.92,
        streak: bool = False,
    ) -> None:
        """Emit a burst; a slot is taken before its three draws are made."""
        for _ in range(count):
            spark = self._acquire()
            if spark is None:
                return

            if direction is None:
                angle = self._rng.uniform(0.0, math.tau)
            else:
                angle = direction + self._rng.uniform(-spread / 2, spread / 2)
            magnitude = speed * (1.0 + self._rng.uniform(-speed_jitter, speed_jitter))

            spark.position = position
            spark.velocity = Vector2(
                math.cos(angle) * magnitude, math.sin(angle) * magnitude
            )
            spark.life = life * (1.0 + self._rng.uniform(-0.25, 0.25))
            spark.life_total = spark.life
            spark.radius = radius
            spark.color = color
            spark.gravity = gravity
            spark.drag = drag
            spark.streak = streak
            spark.active = True

    def update(self, dt: float) -> None:
        """Integrate every live spark and retire the expired ones."""
        for spark in self.pool:
            if not spark.active:
                continue

            spark.life -= dt
            if spark.life <= 0.0:
                spark.active = False
                continue

            spark.velocity = Vector2(
                spark.velocity.x * spark.drag,
                spark.velocity.y * spark.drag + spark.gravity * dt,
            )
            spark.position = spark.position + spark.velocity * dt

    def render(self, renderer: IRenderer, offset: Vector2 = Vector2.zero()) -> None:
        """Draw every live spark, one call each."""
        for spark in self.pool:
            if not spark.active:
                continue

            remaining = spark.life / spark.life_total if spark.life_total > 0 else 0.0
            color = Color(
                spark.color.r,
                spark.color.g,
                spark.color.b,
                int(spark.color.a * remaining),
            )
            position = spark.position + offset

            if spark.streak:
                tail = position - spark.velocity * 0.03
                renderer.draw_line(
                    tail, position, color, width=max(1, int(spark.radius))
                )
            else:
                renderer.draw_circle(position, spark.radius * remaining, color)

    def _acquire(self) -> Spark | None:
        """Return the next free pool slot, or None when the pool is full."""
        start = self._next
        while True:
            spark = self.pool[self._next]
            self._next = (self._next + 1) % self._capacity
            if not spark.active:
                return spark
            if self._next == start:
                return None
