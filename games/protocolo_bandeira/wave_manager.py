"""Protocolo Bandeira - Wave Manager.

Spawns enemies in waves with scaling difficulty.
"""

import random
from typing import List, Tuple

from pyguara.events.dispatcher import EventDispatcher
from pyguara.common.types import Vector2

from games.protocolo_bandeira.pooling import EnemyPool
from games.protocolo_bandeira.events import WaveStartEvent, WaveCompleteEvent


class WaveManager:
    """Manages enemy wave spawning with difficulty scaling."""

    # Arena bounds
    ARENA_WIDTH = 800
    ARENA_HEIGHT = 600
    SPAWN_MARGIN = 100  # Spawn outside visible area

    # Wave configuration
    BASE_ENEMIES = 3
    ENEMIES_PER_WAVE = 2
    MAX_ENEMIES = 20

    # Spawn timing
    SPAWN_DELAY = 0.5  # Seconds between enemy spawns
    WAVE_DELAY = 3.0  # Seconds between waves

    def __init__(self, enemy_pool: EnemyPool, event_dispatcher: EventDispatcher):
        """Initialize the wave manager.

        Args:
            enemy_pool: Pool for enemy entities
            event_dispatcher: Event dispatcher for wave events
        """
        self._pool = enemy_pool
        self._dispatcher = event_dispatcher

        # Wave state
        self._current_wave = 0
        self._enemies_to_spawn = 0
        self._enemies_alive = 0
        self._spawn_timer = 0.0
        self._wave_timer = 0.0
        self._is_wave_active = False

        # Spawn queue
        self._spawn_queue: List[Tuple[str, int]] = []

    def start_wave(self, wave_number: int) -> None:
        """Start a new wave.

        Args:
            wave_number: The wave number (1-indexed)
        """
        self._current_wave = wave_number
        self._is_wave_active = True
        self._wave_timer = 0.0

        # Calculate enemies for this wave
        total_enemies = min(
            self.BASE_ENEMIES + (wave_number - 1) * self.ENEMIES_PER_WAVE,
            self.MAX_ENEMIES,
        )

        # Determine enemy composition based on wave
        self._spawn_queue = self._generate_enemy_composition(wave_number, total_enemies)
        self._enemies_to_spawn = len(self._spawn_queue)
        self._enemies_alive = 0
        self._spawn_timer = 0.0

        self._dispatcher.dispatch(
            WaveStartEvent(wave_number=wave_number, enemy_count=total_enemies)
        )

    def _generate_enemy_composition(
        self, wave: int, total: int
    ) -> List[Tuple[str, int]]:
        """Generate enemy types and health for a wave.

        Args:
            wave: Current wave number
            total: Total enemies to spawn

        Returns:
            List of (enemy_type, health) tuples
        """
        composition = []

        # Base chances (evolve with waves)
        # Bomber gets remaining probability after chaser and shooter
        chaser_chance = max(0.3, 0.7 - wave * 0.05)
        shooter_chance = min(0.4, 0.2 + wave * 0.03)

        # Health scaling
        base_health = 1 + wave // 3

        for _ in range(total):
            roll = random.random()
            if roll < chaser_chance:
                enemy_type = "chaser"
                health = base_health
            elif roll < chaser_chance + shooter_chance:
                enemy_type = "shooter"
                health = base_health + 1
            else:
                enemy_type = "bomber"
                health = max(1, base_health - 1)

            composition.append((enemy_type, health))

        return composition

    def update(self, dt: float, player_position: Vector2) -> None:
        """Update wave spawning logic.

        Args:
            dt: Delta time
            player_position: Current player position (for spawn placement)
        """
        if not self._is_wave_active:
            return

        self._spawn_timer += dt

        # Spawn enemies from queue
        if self._spawn_queue and self._spawn_timer >= self.SPAWN_DELAY:
            self._spawn_timer = 0.0
            enemy_type, health = self._spawn_queue.pop(0)

            # Get spawn position away from player
            spawn_pos = self._get_spawn_position(player_position)

            entity = self._pool.spawn_enemy(spawn_pos, enemy_type, health)
            if entity:
                self._enemies_alive += 1

    def on_enemy_killed(self) -> None:
        """Handle enemy kill notification."""
        self._enemies_alive = max(0, self._enemies_alive - 1)

        # Check for wave completion
        if self._enemies_alive == 0 and len(self._spawn_queue) == 0:
            self._is_wave_active = False
            self._dispatcher.dispatch(WaveCompleteEvent(wave_number=self._current_wave))

    def _get_spawn_position(self, player_pos: Vector2) -> Vector2:
        """Get a spawn position away from the player.

        Args:
            player_pos: Current player position

        Returns:
            Spawn position outside the visible area
        """
        # Choose a random edge
        edge = random.choice(["top", "bottom", "left", "right"])

        if edge == "top":
            x = random.uniform(0, self.ARENA_WIDTH)
            y = -self.SPAWN_MARGIN
        elif edge == "bottom":
            x = random.uniform(0, self.ARENA_WIDTH)
            y = self.ARENA_HEIGHT + self.SPAWN_MARGIN
        elif edge == "left":
            x = -self.SPAWN_MARGIN
            y = random.uniform(0, self.ARENA_HEIGHT)
        else:  # right
            x = self.ARENA_WIDTH + self.SPAWN_MARGIN
            y = random.uniform(0, self.ARENA_HEIGHT)

        return Vector2(x, y)

    @property
    def current_wave(self) -> int:
        """Get current wave number."""
        return self._current_wave

    @property
    def is_wave_active(self) -> bool:
        """Check if a wave is currently active."""
        return self._is_wave_active

    @property
    def enemies_remaining(self) -> int:
        """Get total remaining enemies (alive + to spawn)."""
        return self._enemies_alive + len(self._spawn_queue)
