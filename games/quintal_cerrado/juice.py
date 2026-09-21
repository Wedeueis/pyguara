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


@dataclass(slots=True)
class _Label:
    """One pooled floating label. Inactive entries keep their storage."""

    text: str = ""
    position: Vector2 = field(default_factory=Vector2.zero)
    color: Color = field(default_factory=lambda: Color(255, 255, 255))
    life: float = 0.0
    life_total: float = 1.0
    active: bool = False


class FloatingLabels:
    """A pool of short-lived text that drifts up and fades: "+16", "Need 15".

    The same idea as `pyguara.graphics.components.floating_text.FloatingText`
    and adapted for the same reason as `Motes`: that one is typed against
    `IRenderer` plus a `Camera2D`, and this plot has neither.
    """

    DRIFT = Vector2(0, -34)
    """Pixels per second every label rises at."""

    def __init__(self, capacity: int = 16) -> None:
        """Pre-allocate the pool.

        Args:
            capacity: Maximum labels alive at once. A spawn past it is
                dropped, the same as `Motes`.
        """
        self._pool = [_Label() for _ in range(capacity)]
        self._next = 0

    def spawn(
        self, text: str, position: Vector2, color: Color, life: float = 1.0
    ) -> None:
        """Start one label.

        Args:
            text: What to show. Never wrapped or measured -- keep it short.
            position: Screen-space start.
            color: Starting colour; alpha fades to zero over `life`.
            life: Seconds it lives.
        """
        for _ in range(len(self._pool)):
            label = self._pool[self._next]
            self._next = (self._next + 1) % len(self._pool)
            if not label.active:
                label.text = text
                label.position = position
                label.color = color
                label.life = life
                label.life_total = life
                label.active = True
                return

    def update(self, dt: float) -> None:
        """Advance every live label and retire the expired ones."""
        for label in self._pool:
            if not label.active:
                continue
            label.life -= dt
            if label.life <= 0.0:
                label.active = False
                continue
            label.position = label.position + self.DRIFT * dt

    def render(self, renderer: UIRenderer) -> None:
        """Draw every live label, faded by its remaining life."""
        for label in self._pool:
            if not label.active:
                continue
            remaining = label.life / label.life_total if label.life_total > 0 else 0.0
            color = Color(
                label.color.r,
                label.color.g,
                label.color.b,
                int(label.color.a * remaining),
            )
            renderer.draw_text(label.text, label.position, color, 16)
