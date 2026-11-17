"""The particle pool as plain Python, for the Rust one to be held to.

One `Particle` object per slot, in f64. `ParticleSystem` keeps the same
pool in Rust as f32 arrays, so the two agree to a tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.protocols import IRenderer
from pyguara.graphics.types import RenderBatch
from pyguara.resources.types import Texture

_OPAQUE_WHITE = (255, 255, 255, 255)


def _particle_color(p: Particle) -> tuple[int, int, int, int]:
    """Return the particle's current tint, lerped from color_start to color_end.

    Opaque white (a no-op tint) if this particle has no color animation
    set -- `emit()`'s default, so a particle spawned without `color_start`/
    `color_end` renders exactly as before this existed.
    """
    if p.color_start is None or p.color_end is None:
        return _OPAQUE_WHITE
    t = 0.0 if p.life_total <= 0 else 1.0 - (p.life / p.life_total)
    t = max(0.0, min(1.0, t))
    blended = Color(*p.color_start).lerp(Color(*p.color_end), t)
    return (blended.r, blended.g, blended.b, blended.a)


@dataclass
class Particle:
    """A single particle instance with physics and visual effects.

    Attributes:
        position (Vector2): Current world position.
        velocity (Vector2): Movement vector per second.
        life (float): Time remaining in seconds.
        texture (Texture): The visual representation.
        active (bool): Whether this particle is currently in use.
        acceleration (Vector2): Constant acceleration (e.g., gravity).
        damping (float): Velocity damping factor (0.0 = no damping, 1.0 = instant stop).
        rotation (float): Rotation in degrees.
        scale (Vector2): Scale factor.
        angular_velocity (float): Rotation speed in degrees per second.
        scale_velocity (Vector2): Scale change per second.
        color_start (Color): Initial color.
        color_end (Color): Final color (lerped based on lifetime).
        life_total (float): Total lifetime for calculating color lerp.
    """

    position: Vector2
    velocity: Vector2
    life: float
    texture: Texture | None = None
    active: bool = False

    # Physics
    acceleration: Vector2 = field(default_factory=Vector2.zero)
    damping: float = 1.0  # 1.0 = no damping, 0.98 = slight air resistance

    # Protocol compliance for Renderable
    rotation: float = 0.0
    scale: Vector2 = field(default_factory=lambda: Vector2(1, 1))

    # Visual effects
    angular_velocity: float = 0.0  # degrees per second
    scale_velocity: Vector2 = field(default_factory=Vector2.zero)

    # Color animation (optional, None = no color animation)
    color_start: tuple[int, int, int, int] | None = None
    color_end: tuple[int, int, int, int] | None = None
    life_total: float = 1.0

    # Optional material for custom shaders/effects (None = default shader)
    material: Any = None  # Type: Optional["Material"]


class ReferenceParticles:
    """Does what `ParticleSystem` does, one Python object per particle."""

    def __init__(self, capacity: int = 1000, rng: RandomStream | None = None) -> None:
        """Pre-allocate `capacity` particles."""
        self._capacity = capacity
        self._next_index = 0
        self._rng = rng if rng is not None else RandomStream()
        self.pool: list[Particle] = [
            Particle(Vector2.zero(), Vector2.zero(), 0.0) for _ in range(capacity)
        ]

    @property
    def live_count(self) -> int:
        """How many particles are currently alive."""
        return sum(1 for particle in self.pool if particle.active)

    def emit(
        self,
        texture: Texture,
        position: Vector2,
        count: int = 1,
        speed: float = 100.0,
        spread: float = 360.0,
        life: float = 1.0,
        acceleration: Vector2 = Vector2.zero(),
        damping: float = 1.0,
        angular_velocity: float = 0.0,
        scale: Vector2 = Vector2.one(),
        scale_velocity: Vector2 = Vector2.zero(),
        color_start: tuple[int, int, int, int] | None = None,
        color_end: tuple[int, int, int, int] | None = None,
    ) -> None:
        """Spawn particles; a slot is found before its three draws are made."""
        spawned = 0
        search_start = self._next_index

        # Linear search for inactive particles (Ring Buffer strategy)
        while spawned < count:
            p = self.pool[self._next_index]

            # Found a dead particle, recycle it
            if not p.active:
                p.active = True
                p.position = Vector2(position.x, position.y)
                p.texture = texture
                p.life = life
                p.life_total = life

                # Random Velocity Calculation
                angle = self._rng.uniform(0, spread)
                direction = Vector2.right().rotate_degrees(angle)
                random_velocity = direction * self._rng.uniform(
                    speed * 0.5, speed * 1.5
                )
                p.velocity = random_velocity

                # Physics
                p.acceleration = acceleration
                p.damping = damping

                # Visual effects
                p.rotation = self._rng.uniform(0, 360)  # Random initial rotation
                p.angular_velocity = angular_velocity
                p.scale = Vector2(scale.x, scale.y)
                p.scale_velocity = scale_velocity

                # Color animation
                p.color_start = color_start
                p.color_end = color_end

                spawned += 1

            # Advance index, wrap around if needed
            self._next_index = (self._next_index + 1) % self._capacity

            # Safety: If we looped back to start, pool is full
            if self._next_index == search_start:
                # Optional: Force overwrite oldest? For now, just stop emitting.
                break

    def update(self, dt: float) -> None:
        """Integrate every live particle and retire the expired ones."""
        for p in self.pool:
            if p.active:
                p.life -= dt
                if p.life <= 0:
                    p.active = False
                    p.texture = None  # Release reference
                else:
                    # Physics: Apply acceleration
                    p.velocity = Vector2(
                        p.velocity.x + p.acceleration.x * dt,
                        p.velocity.y + p.acceleration.y * dt,
                    )

                    # Physics: Apply damping (air resistance)
                    p.velocity = Vector2(
                        p.velocity.x * p.damping,
                        p.velocity.y * p.damping,
                    )

                    # Euler Integration for position
                    p.position = Vector2(
                        p.position.x + p.velocity.x * dt,
                        p.position.y + p.velocity.y * dt,
                    )

                    # Visual effects: Rotation
                    p.rotation += p.angular_velocity * dt

                    # Visual effects: Scale
                    p.scale = Vector2(
                        p.scale.x + p.scale_velocity.x * dt,
                        p.scale.y + p.scale_velocity.y * dt,
                    )

    def render(
        self, backend: IRenderer, camera: Camera2D, viewport: Viewport | None = None
    ) -> None:
        """Draw every live particle, one `RenderBatch` per texture."""
        if viewport is None:
            viewport = Viewport(0, 0, backend.width, backend.height)

        zoom = camera.zoom
        offset_vec = camera.screen_offset(viewport)
        offset_x, offset_y = offset_vec.x, offset_vec.y

        batches: dict[Texture, list[tuple[float, float]]] = {}
        colors: dict[Texture, list[tuple[int, int, int, int]]] = {}
        has_color: dict[Texture, bool] = {}

        for p in self.pool:
            if p.active and p.texture:
                if p.texture not in batches:
                    batches[p.texture] = []
                    colors[p.texture] = []
                    has_color[p.texture] = False

                screen_x = (p.position.x * zoom) + offset_x
                screen_y = (p.position.y * zoom) + offset_y

                batches[p.texture].append((screen_x, screen_y))

                rgba = _particle_color(p)
                colors[p.texture].append(rgba)
                if rgba != _OPAQUE_WHITE:
                    has_color[p.texture] = True

        for texture, destinations in batches.items():
            enabled = has_color[texture]
            batch = RenderBatch(
                texture,
                destinations,
                colors=colors[texture] if enabled else [],
                colors_enabled=enabled,
            )
            backend.render_batch(batch)
