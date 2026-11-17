"""Textured particles for transient effects: smoke, fire, debris.

`ParticleSystem` is a fixed-capacity pool that favours count over
per-particle sorting. The pool is held in Rust as arrays and has no
Python implementation; the random draws of an emission stay in Python,
on the engine's seeded stream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.protocols import IRenderer
from pyguara.graphics.types import RenderBatch
from pyguara.native import require_extension
from pyguara.resources.types import Texture


class ParticleSystem:
    """Manager for all particle effects in the game.

    Acts as a self-contained mini-engine that handles the lifecycle (Update)
    and batching (Render) of thousands of small entities.
    """

    def __init__(self, capacity: int = 1000, rng: RandomStream | None = None):
        """Initialize the particle pool.

        Args:
            capacity (int): Maximum number of concurrent particles.
                            Higher numbers use more RAM but allow denser effects.
            rng (RandomStream | None): Random stream driving per-particle
                spread/speed/rotation. Defaults to a fresh, unseeded stream.

        Raises:
            RuntimeError: If the native extension cannot be imported.
        """
        self._capacity = capacity
        self._rng = rng if rng is not None else RandomStream()
        self._native: Any = require_extension("ParticleSystem").NativeParticlePool(
            capacity
        )
        # Textures cannot live in a float column, so the native pool holds
        # an index into this list and the mapping stays here.
        self._textures: list[Texture] = []
        self._texture_ids: dict[int, int] = {}

    @property
    def live_count(self) -> int:
        """How many particles are currently alive."""
        return int(self._native.live_count())

    def _texture_slot(self, texture: Texture) -> int:
        """Return this texture's index, registering it on first use.

        Keyed on identity rather than equality: a `Texture` is a handle to a
        GPU allocation, and two handles to the same image are still two
        bindings.
        """
        key = id(texture)
        slot = self._texture_ids.get(key)
        if slot is None:
            slot = len(self._textures)
            self._texture_ids[key] = slot
            self._textures.append(texture)
        return slot

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
        """Spawn new particles with optional physics and visual effects.

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
        # The random draws stay in Python: an emission takes three per
        # particle from the engine's seeded stream, and a replay restores
        # that seed. Only as many particles as will fit are drawn for, so
        # an emission that overflows leaves the stream where a smaller one
        # would have.
        spawnable = min(count, self._capacity - int(self._native.live_count()))

        velocity_x: list[float] = []
        velocity_y: list[float] = []
        rotations: list[float] = []
        for _ in range(spawnable):
            angle = self._rng.uniform(0, spread)
            direction = Vector2.right().rotate_degrees(angle)
            velocity = direction * self._rng.uniform(speed * 0.5, speed * 1.5)
            velocity_x.append(velocity.x)
            velocity_y.append(velocity.y)
            rotations.append(self._rng.uniform(0, 360))

        self._native.emit(
            self._texture_slot(texture),
            position.x,
            position.y,
            velocity_x,
            velocity_y,
            rotations,
            life,
            acceleration.x,
            acceleration.y,
            damping,
            angular_velocity,
            scale.x,
            scale.y,
            scale_velocity.x,
            scale_velocity.y,
            color_start,
            color_end,
        )

    def emit_preset(
        self,
        preset_name: str,
        texture: Texture,
        position: Vector2,
    ) -> None:
        """Emit particles using a pre-configured preset.

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
        """Advance the simulation with physics and visual effects.

        Updates positions, applies physics (acceleration, damping),
        visual effects (rotation, scale), and color animation.

        Args:
            dt (float): Delta time in seconds.
        """
        self._native.update(dt)

    def render(
        self, backend: IRenderer, camera: Camera2D, viewport: Viewport | None = None
    ) -> None:
        """Draw all active particles, one `RenderBatch` per texture."""
        if viewport is None:
            viewport = Viewport(0, 0, backend.width, backend.height)

        zoom = camera.zoom
        offset_vec = camera.screen_offset(viewport)
        offset_x, offset_y = offset_vec.x, offset_vec.y

        # The world-to-screen transform, the colour lerp and the grouping
        # by texture happen in Rust; this wraps each group for the renderer.
        for slot, destinations, tints, tinted in self._native.pack_for_render(
            zoom, offset_x, offset_y
        ):
            backend.render_batch(
                RenderBatch(
                    self._textures[slot],
                    destinations,
                    colors=tints if tinted else [],
                    colors_enabled=tinted,
                )
            )


# ===== Particle Emitter Presets =====


@dataclass
class ParticleEmitterConfig:
    """Configuration preset for particle effects.

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
    color_start: tuple[int, int, int, int] | None = None
    color_end: tuple[int, int, int, int] | None = None


# Pre-configured particle presets
PARTICLE_PRESETS: dict[str, ParticleEmitterConfig] = {
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
