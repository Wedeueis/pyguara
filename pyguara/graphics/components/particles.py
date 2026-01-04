"""
High-performance Particle System logic.

This module implements a specialized rendering system for transient visual effects
(smoke, fire, sparks). It prioritizes raw throughput (count) over individual
sorting precision.

It utilizes the 'Object Pool' pattern to minimize memory allocation during gameplay,
ensuring smooth frame rates even when emitting hundreds of particles per second.
"""

from __future__ import annotations
from dataclasses import dataclass
import random
from typing import Dict, List, Tuple, Optional, cast

from pyguara.common.types import Vector2
from pyguara.resources.types import Texture
from pyguara.graphics.protocols import IRenderer
from pyguara.graphics.types import RenderBatch
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.viewport import Viewport


@dataclass
class Particle:
    """
    A single particle instance.

    Attributes:
        position (Vector2): Current world position.
        velocity (Vector2): Movement vector per second.
        life (float): Time remaining in seconds.
        texture (Texture): The visual representation.
        active (bool): Whether this particle is currently in use.
    """

    position: Vector2
    velocity: Vector2
    life: float
    texture: Texture | None = None
    active: bool = False


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
    ) -> None:
        """
        Spawn new particles.

        Args:
            texture (Texture): The image to use.
            position (Vector2): The emission origin in World Space.
            count (int): How many particles to spawn at once.
            speed (float): Initial speed magnitude.
            spread (float): Angle spread in degrees (360 = circle, 0 = laser).
            life (float): Duration in seconds before disappearing.
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

                # Random Velocity Calculation
                angle = random.uniform(0, spread)
                # Create a unit vector and rotate it
                # (Assuming (1,0) is base direction, rotate by angle)
                direction = Vector2(1, 0).rotate(angle)
                random_velocity = direction * random.uniform(speed * 0.5, speed * 1.5)
                p.velocity = cast(Vector2, random_velocity)

                spawned += 1

            # Advance index, wrap around if needed
            self._next_index = (self._next_index + 1) % self._capacity

            # Safety: If we looped back to start, pool is full
            if self._next_index == search_start:
                # Optional: Force overwrite oldest? For now, just stop emitting.
                break

    def update(self, dt: float) -> None:
        """
        Advance the simulation.

        Updates positions and kills particles that ran out of life.

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
                    # Euler Integration
                    # p.position += p.velocity * dt
                    # Optimization: Vector math can be slow in loops.
                    # If strictly needed, unpack to floats here.
                    p.position = Vector2(
                        p.position.x + p.velocity.x * dt,
                        p.position.y + p.velocity.y * dt,
                    )

    def render(
        self, backend: IRenderer, camera: Camera2D, viewport: Optional[Viewport] = None
    ) -> None:
        """Draw all active particles to the backend."""
        if viewport is None:
            viewport = Viewport(0, 0, backend.width, backend.height)

        batches: Dict[Texture, List[Tuple[float, float]]] = {}
        zoom = camera.zoom

        offset_vec: Vector2 = cast(
            Vector2, viewport.center_vec - (camera.position * zoom)
        )
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
