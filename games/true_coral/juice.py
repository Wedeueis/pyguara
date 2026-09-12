"""True Coral - the feedback layer: sparks and screen shake.

Both are pooled, screen-space and deliberately small. The engine ships
`ParticleSystem`, which is the right tool when particles are textured
sprites; these are not. Under the ModernGL backend the sprite path carries
no per-instance tint, so a textured particle can only ever be white, while
the shape path (`draw_circle`/`draw_line`) takes a colour per primitive and
batches them into one instanced draw call per shape type anyway. Coloured
embers are the entire point of an eat burst, so these go through shapes.

Shake is the engine's `CameraShake` maths, driven directly rather than
through a camera: this demo draws in screen space, so the offset is added
to what it draws rather than to a camera position.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.graphics.components.camera import CameraShake
from pyguara.graphics.protocols import IRenderer


@dataclass(slots=True)
class _Spark:
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


class Sparks:
    """A pool of short-lived coloured particles."""

    def __init__(self, capacity: int = 320, rng: RandomStream | None = None) -> None:
        """Pre-allocate the pool.

        Args:
            capacity: Maximum particles alive at once. A burst that would
                exceed it drops the excess rather than growing, the same
                way `ParticleSystem` does.
            rng: Random stream driving spread and speed jitter.
        """
        self._pool = [_Spark() for _ in range(capacity)]
        self._next = 0
        self._rng = rng if rng is not None else RandomStream()

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
        """Emit a burst of particles from one point.

        Args:
            position: Screen-space origin.
            color: Starting colour; alpha fades to zero over `life`.
            count: How many particles to emit.
            speed: Base speed in pixels per second.
            speed_jitter: Fraction of `speed` to vary each particle by.
            direction: Centre angle in radians, or None for a full circle.
            spread: Angular width of the cone around `direction`.
            life: Seconds each particle lives.
            radius: Particle radius in pixels.
            gravity: Downward acceleration in pixels per second squared.
            drag: Per-frame velocity retention; below 1.0 slows them down.
            streak: Draw each particle as a short line along its velocity
                instead of a dot -- right for rain splashes and embers.
        """
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
        """Integrate every live particle and retire the expired ones.

        Args:
            dt: Seconds since the last frame.
        """
        for spark in self._pool:
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
        """Draw every live particle.

        Args:
            renderer: Target renderer.
            offset: Screen-space offset applied to every particle, so the
                sparks shake with the rest of the arena.
        """
        for spark in self._pool:
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

    def _acquire(self) -> _Spark | None:
        """Return the next free pool slot, or None when the pool is full."""
        start = self._next
        while True:
            spark = self._pool[self._next]
            self._next = (self._next + 1) % len(self._pool)
            if not spark.active:
                return spark
            if self._next == start:
                return None


class Shaker:
    """Several overlapping camera shakes, summed into one offset."""

    def __init__(self, rng: RandomStream | None = None) -> None:
        """Start still.

        Args:
            rng: Random stream driving shake direction, shared by every
                shake this adds.
        """
        self._shakes: list[CameraShake] = []
        self._rng = rng if rng is not None else RandomStream()
        self._offset = Vector2.zero()

    @property
    def offset(self) -> Vector2:
        """The current shake offset, in pixels."""
        return self._offset

    def add(self, magnitude: float, duration: float = 0.25) -> None:
        """Start another shake on top of whatever is already running.

        Args:
            magnitude: Peak offset in pixels; decays linearly to zero.
            duration: Seconds the shake lasts.
        """
        if magnitude <= 0.0:
            return
        self._shakes.append(
            CameraShake(duration=duration, magnitude=magnitude, rng=self._rng)
        )

    def update(self, dt: float) -> Vector2:
        """Advance every live shake and return their combined offset.

        Args:
            dt: Seconds since the last frame.

        Returns:
            The offset to add to everything drawn this frame.
        """
        total = Vector2.zero()
        still_running = []
        for shake in self._shakes:
            offset = shake.update(dt)
            if shake.elapsed < shake.duration:
                still_running.append(shake)
                total = total + offset
        self._shakes = still_running
        self._offset = total
        return total
