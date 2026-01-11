"""
High-performance Particle System logic.

This module implements a specialized rendering system for transient visual effects
(smoke, fire, sparks). It prioritizes raw throughput (count) over individual
sorting precision.

It utilizes the 'Object Pool' pattern to minimize memory allocation during gameplay,
ensuring smooth frame rates even when emitting hundreds of particles per second.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import random
from typing import Dict, List, Tuple, Optional

from pyguara.common.types import Vector2
from pyguara.resources.types import Texture
from pyguara.graphics.protocols import IRenderer
from pyguara.graphics.types import RenderBatch
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.viewport import Viewport


@dataclass
class Particle:
    """
    A single particle instance with physics and visual effects.

    Attributes:
        position (Vector2): Current world position.
        velocity (Vector2): Movement vector per second.
        life (float): Time remaining in seconds.
        texture (Texture): The visual representation.
        active (bool): Whether this particle is currently in use.

        # Physics
        acceleration (Vector2): Constant acceleration (e.g., gravity).
        damping (float): Velocity damping factor (0.0 = no damping, 1.0 = instant stop).

        # Transform (Renderable protocol)
        rotation (float): Rotation in degrees.
        scale (Vector2): Scale factor.

        # Visual effects
        angular_velocity (float): Rotation speed in degrees per second.
        scale_velocity (Vector2): Scale change per second.

        # Color animation
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
    color_start: Optional[tuple[int, int, int, int]] = None
    color_end: Optional[tuple[int, int, int, int]] = None
    life_total: float = 1.0


class ParticleSystem:
    """
    Manager for all particle effects in the game.

    Acts as a self-contained mini-engine that handles the lifecycle (Update)
    and batching (Render) of thousands of small entities.
    """

    def __init__(self, capacity: int = 1000):
        """
        Initialize the particle pool.

        Args:
            capacity (int): Maximum number of concurrent particles.
                            Higher numbers use more RAM but allow denser effects.
        """
        # Pre-allocate the pool to avoid runtime instantiation
        self._pool = [
            Particle(Vector2.zero(), Vector2.zero(), 0.0) for _ in range(capacity)
        ]
        self._capacity = capacity
        # Pointer to the next available slot (Simple Ring Buffer or Search)
        self._next_index = 0

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
        color_start: Optional[tuple[int, int, int, int]] = None,
        color_end: Optional[tuple[int, int, int, int]] = None,
    ) -> None:
        """
        Spawn new particles with optional physics and visual effects.

        Args:
            texture (Texture): The image to use.
            position (Vector2): The emission origin in World Space.
            count (int): How many particles to spawn at once.
            speed (float): Initial speed magnitude.
            spread (float): Angle spread in degrees (360 = circle, 0 = laser).
            life (float): Duration in seconds before disappearing.
            acceleration (Vector2): Constant acceleration (e.g., Vector2(0, 200) for gravity).
            damping (float): Velocity damping (1.0 = none, 0.98 = slight air resistance).
            angular_velocity (float): Rotation speed in degrees per second.
            scale (Vector2): Initial scale.
            scale_velocity (Vector2): Scale change per second.
            color_start (Optional[tuple]): Initial RGBA color (r, g, b, a).
            color_end (Optional[tuple]): Final RGBA color for fade effect.
        """
        spawned = 0
        search_start = self._next_index

        # Linear search for inactive particles (Ring Buffer strategy)
        while spawned < count:
            p = self._pool[self._next_index]

            # Found a dead particle, recycle it
            if not p.active:
                p.active = True
                p.position = Vector2(position.x, position.y)
                p.texture = texture
                p.life = life
                p.life_total = life

                # Random Velocity Calculation
                angle = random.uniform(0, spread)
                direction = Vector2(1, 0).rotate(angle)
                random_velocity = direction * random.uniform(speed * 0.5, speed * 1.5)
                p.velocity = random_velocity

                # Physics
                p.acceleration = acceleration
                p.damping = damping

                # Visual effects
                p.rotation = random.uniform(0, 360)  # Random initial rotation
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

    def emit_preset(
        self,
        preset_name: str,
        texture: Texture,
        position: Vector2,
    ) -> None:
        """
        Emit particles using a pre-configured preset.

        Args:
            preset_name (str): Name of the preset ("fire", "smoke", "explosion", etc.).
            texture (Texture): The particle texture to use.
            position (Vector2): Emission position in world space.

        Raises:
            KeyError: If preset_name doesn't exist.

        Example:
            particle_system.emit_preset("fire", fire_texture, player_pos)
        """
        if preset_name not in PARTICLE_PRESETS:
            available = ", ".join(PARTICLE_PRESETS.keys())
            raise KeyError(f"Preset '{preset_name}' not found. Available: {available}")

        config = PARTICLE_PRESETS[preset_name]

        self.emit(
            texture=texture,
            position=position,
            count=config.count,
            speed=config.speed,
            spread=config.spread,
            life=config.life,
            acceleration=config.acceleration,
            damping=config.damping,
            angular_velocity=config.angular_velocity,
            scale=config.scale,
            scale_velocity=config.scale_velocity,
            color_start=config.color_start,
            color_end=config.color_end,
        )

    def update(self, dt: float) -> None:
        """
        Advance the simulation with physics and visual effects.

        Updates positions, applies physics (acceleration, damping),
        visual effects (rotation, scale), and color animation.

        Args:
            dt (float): Delta time in seconds.
        """
        for p in self._pool:
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
        self, backend: IRenderer, camera: Camera2D, viewport: Optional[Viewport] = None
    ) -> None:
        """Draw all active particles to the backend."""
        if viewport is None:
            viewport = Viewport(0, 0, backend.width, backend.height)

        batches: Dict[Texture, List[Tuple[float, float]]] = {}
        zoom = camera.zoom

        offset_vec = viewport.center_vec - (camera.position * zoom)
        offset_x, offset_y = offset_vec.x, offset_vec.y

        for p in self._pool:
            if p.active and p.texture:
                if p.texture not in batches:
                    batches[p.texture] = []

                screen_x = (p.position.x * zoom) + offset_x
                screen_y = (p.position.y * zoom) + offset_y

                batches[p.texture].append((screen_x, screen_y))

        for texture, destinations in batches.items():
            batch = RenderBatch(texture, destinations)
            backend.render_batch(batch)


# ===== Particle Emitter Presets =====


@dataclass
class ParticleEmitterConfig:
    """
    Configuration preset for particle effects.

    Stores all parameters needed to emit a specific particle effect style.
    """

    count: int = 10
    speed: float = 100.0
    spread: float = 360.0
    life: float = 1.0
    acceleration: Vector2 = field(default_factory=Vector2.zero)
    damping: float = 1.0
    angular_velocity: float = 0.0
    scale: Vector2 = field(default_factory=Vector2.one)
    scale_velocity: Vector2 = field(default_factory=Vector2.zero)
    color_start: Optional[tuple[int, int, int, int]] = None
    color_end: Optional[tuple[int, int, int, int]] = None


# Pre-configured particle presets
PARTICLE_PRESETS: Dict[str, ParticleEmitterConfig] = {
    "fire": ParticleEmitterConfig(
        count=20,
        speed=50.0,
        spread=45.0,  # Upward cone
        life=0.8,
        acceleration=Vector2(0, -100),  # Float upward
        damping=0.95,  # Slight air resistance
        angular_velocity=180.0,  # Spin moderately
        scale=Vector2(0.5, 0.5),
        scale_velocity=Vector2(0.3, 0.3),  # Grow over time
        color_start=(255, 200, 50, 255),  # Bright yellow-orange
        color_end=(255, 50, 0, 0),  # Fade to transparent red
    ),
    "smoke": ParticleEmitterConfig(
        count=15,
        speed=30.0,
        spread=90.0,  # Wide spread
        life=2.0,
        acceleration=Vector2(0, -20),  # Slow float upward
        damping=0.98,  # Strong air resistance
        angular_velocity=45.0,  # Slow spin
        scale=Vector2(0.3, 0.3),
        scale_velocity=Vector2(0.5, 0.5),  # Expand significantly
        color_start=(100, 100, 100, 200),  # Gray, semi-transparent
        color_end=(50, 50, 50, 0),  # Fade to transparent
    ),
    "explosion": ParticleEmitterConfig(
        count=50,
        speed=300.0,
        spread=360.0,  # Full circle
        life=0.5,
        acceleration=Vector2(0, 200),  # Strong gravity
        damping=0.92,  # Rapid slowdown
        angular_velocity=720.0,  # Fast spin
        scale=Vector2(0.8, 0.8),
        scale_velocity=Vector2(-1.0, -1.0),  # Shrink over time
        color_start=(255, 255, 150, 255),  # Bright white-yellow
        color_end=(255, 100, 0, 0),  # Fade to orange
    ),
    "sparks": ParticleEmitterConfig(
        count=30,
        speed=200.0,
        spread=180.0,  # Upward hemisphere
        life=0.6,
        acceleration=Vector2(0, 400),  # Strong gravity
        damping=0.96,
        angular_velocity=360.0,
        scale=Vector2(0.2, 0.2),
        scale_velocity=Vector2(-0.2, -0.2),  # Shrink
        color_start=(255, 255, 200, 255),  # Bright yellow
        color_end=(255, 150, 0, 0),  # Fade to orange
    ),
    "rain": ParticleEmitterConfig(
        count=100,
        speed=400.0,
        spread=10.0,  # Narrow, downward
        life=1.5,
        acceleration=Vector2(0, 200),  # Gravity
        damping=1.0,  # No air resistance
        angular_velocity=0.0,  # No rotation
        scale=Vector2(0.1, 0.4),  # Elongated
        scale_velocity=Vector2(0, 0),  # No size change
        color_start=(100, 150, 255, 150),  # Blue, semi-transparent
        color_end=(100, 150, 255, 50),  # Fade slightly
    ),
}
