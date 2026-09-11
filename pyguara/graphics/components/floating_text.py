"""Pooled, transient world-space text: damage numbers, pickup labels, prompts.

Mirrors `ParticleSystem`'s shape (a self-contained pool, `spawn`/`update`/
`render`, scene-composed rather than DI-registered) since this is the same
category of thing -- a burst of short-lived visual feedback -- built on
`IRenderer.draw_text` (#71) the same way particles are built on
`render_batch`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.protocols import IRenderer

DEFAULT_VELOCITY = Vector2(0, -40)  # Drifts upward, pixels/second.


@dataclass
class _FloatingTextEntry:
    text: str = ""
    position: Vector2 = Vector2.zero()
    color: Color = field(default_factory=lambda: Color(255, 255, 255))
    size: int = 16
    velocity: Vector2 = Vector2.zero()
    life: float = 0.0
    life_total: float = 1.0
    active: bool = False


class FloatingText:
    """A pool of short-lived world-space text entries that drift and fade."""

    def __init__(self, capacity: int = 32) -> None:
        """Pre-allocate the pool.

        Args:
            capacity: Maximum number of entries visible at once. `spawn()`
                beyond this silently drops, the same as `ParticleSystem`.
        """
        self._pool = [_FloatingTextEntry() for _ in range(capacity)]
        self._capacity = capacity
        self._next_index = 0

    def spawn(
        self,
        text: str,
        position: Vector2,
        color: Color = Color.WHITE,
        size: int = 16,
        life: float = 1.0,
        velocity: Vector2 = DEFAULT_VELOCITY,
    ) -> None:
        """Spawn one floating text entry.

        Args:
            text: The string to show. Never re-wrapped or measured -- keep
                it short.
            position: World-space spawn point.
            color: Starting color; alpha fades linearly to 0 over `life`.
            size: Font size in pixels, passed straight to `draw_text`.
            life: Seconds until this entry expires and is recycled.
            velocity: World-space drift, pixels/second. Defaults to a slow
                upward float, the conventional "damage number" motion.
        """
        search_start = self._next_index
        while True:
            entry = self._pool[self._next_index]
            if not entry.active:
                entry.text = text
                entry.position = position
                entry.color = color
                entry.size = size
                entry.velocity = velocity
                entry.life = life
                entry.life_total = life
                entry.active = True
                return

            self._next_index = (self._next_index + 1) % self._capacity
            if self._next_index == search_start:
                return  # Pool full; drop the spawn, like ParticleSystem does.

    def update(self, dt: float) -> None:
        """Advance every active entry's position and remaining life."""
        for entry in self._pool:
            if not entry.active:
                continue
            entry.life -= dt
            if entry.life <= 0:
                entry.active = False
                continue
            entry.position = entry.position + entry.velocity * dt

    def render(
        self, backend: IRenderer, camera: Camera2D, viewport: Rect | None = None
    ) -> None:
        """Draw every active entry, faded by its remaining life fraction."""
        for entry in self._pool:
            if not entry.active:
                continue
            fraction = max(0.0, entry.life / entry.life_total)
            faded = Color(
                entry.color.r,
                entry.color.g,
                entry.color.b,
                int(entry.color.a * fraction),
            )
            screen_pos = camera.world_to_screen(entry.position, viewport)
            backend.draw_text(entry.text, screen_pos, faded, entry.size)
