"""Lightweight visual feedback for the plot: dirt/pollen particle motes.

Adapted from the pooled-particle pattern `pyguara.graphics.vfx.sparks.Sparks`
uses, but typed against `UIRenderer` rather than `IRenderer`: the plot has
no camera or world space at all (Phase 1's bootstrap deliberately registers
neither -- see `bootstrap.py`), and everything here draws straight in the
screen-space coordinates `GardenGridCanvas` already computes for a cell, so
reusing `Sparks` itself would mean satisfying a renderer type it was never
meant to take.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import UIRenderer


@dataclass(slots=True)
class _Mote:
    """One pooled particle. Inactive entries keep their storage."""

    position: Vector2 = field(default_factory=Vector2.zero)
    velocity: Vector2 = field(default_factory=Vector2.zero)
    life: float = 0.0
    life_total: float = 1.0
    radius: float = 2.0
    color: Color = field(default_factory=lambda: Color(255, 255, 255))
    active: bool = False


class Motes:
    """A small pool of soft particles for a till/plant/growth beat."""

    def __init__(self, capacity: int = 96, rng: RandomStream | None = None) -> None:
        """Pre-allocate the pool.

        Args:
            capacity: Maximum particles alive at once. A burst that would
                exceed it drops the excess, the same as `Sparks`.
            rng: Random stream driving spread and speed jitter.
        """
        self._pool = [_Mote() for _ in range(capacity)]
        self._next = 0
        self._rng = rng if rng is not None else RandomStream()

    def burst(
        self,
        position: Vector2,
        color: Color,
        *,
        count: int = 8,
        speed: float = 40.0,
        life: float = 0.5,
        radius: float = 3.0,
    ) -> None:
        """Emit a soft burst of particles from one point.

        Args:
            position: Screen-space origin.
            color: Starting colour; alpha fades to zero over `life`.
            count: How many particles to emit.
            speed: Base speed in pixels per second.
            life: Seconds each particle lives.
            radius: Particle radius in pixels.
        """
        for _ in range(count):
            mote = self._acquire()
            if mote is None:
                return

            angle = self._rng.uniform(0.0, math.tau)
            magnitude = speed * (1.0 + self._rng.uniform(-0.4, 0.4))
            mote.position = position
            mote.velocity = Vector2(
                math.cos(angle) * magnitude, math.sin(angle) * magnitude - 15.0
            )
            mote.life = life * (1.0 + self._rng.uniform(-0.2, 0.2))
            mote.life_total = mote.life
            mote.radius = radius
            mote.color = color
            mote.active = True

    def update(self, dt: float) -> None:
        """Integrate every live particle and retire the expired ones."""
        for mote in self._pool:
            if not mote.active:
                continue

            mote.life -= dt
            if mote.life <= 0.0:
                mote.active = False
                continue

            mote.velocity = Vector2(
                mote.velocity.x * 0.92, mote.velocity.y * 0.92 + 70.0 * dt
            )
            mote.position = mote.position + mote.velocity * dt

    def render(self, renderer: UIRenderer) -> None:
        """Draw every live particle."""
        for mote in self._pool:
            if not mote.active:
                continue

            remaining = mote.life / mote.life_total if mote.life_total > 0 else 0.0
            color = Color(
                mote.color.r, mote.color.g, mote.color.b, int(mote.color.a * remaining)
            )
            renderer.draw_circle(mote.position, mote.radius * remaining, color)

    def _acquire(self) -> _Mote | None:
        """Return the next free pool slot, or None when the pool is full."""
        start = self._next
        while True:
            mote = self._pool[self._next]
            self._next = (self._next + 1) % len(self._pool)
            if not mote.active:
                return mote
            if self._next == start:
                return None
