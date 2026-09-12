"""Protocolo Bandeira - Wave Manager.

Spawns enemies in waves with scaling difficulty, on top of
`kits.spawn.SpawnDirector` -- this module owns only the game-specific
policy `SpawnDirector` deliberately stays agnostic to: how many enemies
per wave, what type/health mix, and where they appear on the arena's
edge. Pacing (how fast entries release) is the kit's `Wave.interval`;
this game never uses `SpawnDirector`'s budget gate (every entry costs
0.0), since it never had a budget concept of its own -- only a fixed
enemy count per wave and a release interval.
"""

from collections.abc import Callable
from dataclasses import dataclass

from games.protocolo_bandeira.events import WaveCompleteEvent, WaveStartEvent
from games.protocolo_bandeira.pooling import EnemyPool
from pyguara.common.random import RandomStream
from pyguara.common.types import Rect, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.spawn import SpawnDirector, SpawnEntry, Wave


@dataclass(slots=True)
class _PendingSpawn:
    """A telegraphed spawn: a ring on the ground counting down to an enemy."""

    position: Vector2
    remaining: float
    enemy_type: str
    health: float


class WaveManager:
    """Manages enemy wave spawning with difficulty scaling."""

    SPAWN_MARGIN = 70  # Spawn just off the field, and walk in

    # How long a spawn is telegraphed on the ground before the enemy
    # arrives. Enemies come in from off-screen, so without a ring to
    # watch, the first thing the player learns about a bomber is the hit.
    WARNING_LEAD = 0.7

    # Wave configuration
    BASE_ENEMIES = 5
    ENEMIES_PER_WAVE = 3
    MAX_ENEMIES = 24

    # Spawn timing
    SPAWN_DELAY = 0.5  # Seconds between enemy spawns

    def __init__(
        self,
        enemy_pool: EnemyPool,
        event_dispatcher: EventDispatcher,
        arena: Rect,
        rng: RandomStream | None = None,
    ):
        """Initialize the wave manager.

        Args:
            enemy_pool: Pool for enemy entities
            event_dispatcher: Event dispatcher for wave events
            arena: The play area. Spawns are placed just outside its
                edges, so an enemy walks onto the field rather than
                appearing on it.
            rng: Seeded stream driving composition rolls and spawn-edge
                placement. Defaults to a fresh, unseeded stream.
        """
        self._arena = arena
        self._pool = enemy_pool
        self._dispatcher = event_dispatcher
        self._rng = rng if rng is not None else RandomStream()
        self._director = SpawnDirector(budget=0.0, regen_rate=0.0, max_budget=0.0)

        # Wave state
        self._current_wave = 0
        self._enemies_alive = 0
        self._pending_in_wave = 0
        self._wave_size = 0
        self._last_player_position = Vector2.zero()
        self._warnings: list[_PendingSpawn] = []

    def start_wave(self, wave_number: int) -> None:
        """Start a new wave.

        Args:
            wave_number: The wave number (1-indexed)
        """
        self._current_wave = wave_number
        self._enemies_alive = 0

        # Calculate enemies for this wave
        total_enemies = min(
            self.BASE_ENEMIES + (wave_number - 1) * self.ENEMIES_PER_WAVE,
            self.MAX_ENEMIES,
        )

        composition = self._generate_enemy_composition(wave_number, total_enemies)
        entries = [
            SpawnEntry(factory=self._make_spawn_factory(enemy_type, health), cost=0.0)
            for enemy_type, health in composition
        ]
        self._pending_in_wave = len(entries)
        self._wave_size = len(entries)
        self._director.queue_wave(Wave(entries=entries, interval=self.SPAWN_DELAY))

        self._dispatcher.dispatch(
            WaveStartEvent(wave_number=wave_number, enemy_count=total_enemies)
        )

    def _make_spawn_factory(self, enemy_type: str, health: int) -> Callable[[], None]:
        """Build the zero-argument factory one `SpawnEntry` releases.

        Reads `self._last_player_position` at release time (set by the
        most recent `update()` call), not at queue time -- entries release
        over several ticks, and the spawn-edge choice should track where
        the player actually is when each one fires, same as before this
        went through `SpawnDirector`.
        """

        def factory() -> None:
            self._pending_in_wave = max(0, self._pending_in_wave - 1)
            spawn_pos = self._get_spawn_position(self._last_player_position)
            # Ring the ground first and spawn when the ring closes, so the
            # player is looking at the right patch of dirt before anything
            # is standing on it.
            self._warnings.append(
                _PendingSpawn(
                    position=spawn_pos,
                    remaining=self.WARNING_LEAD,
                    enemy_type=enemy_type,
                    health=float(health),
                )
            )

        return factory

    def _generate_enemy_composition(
        self, wave: int, total: int
    ) -> list[tuple[str, int]]:
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
            roll = self._rng.random()
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
        self._last_player_position = player_position
        self._director.update(dt)
        self._release_telegraphed(dt)

    def _release_telegraphed(self, dt: float) -> None:
        """Count the warning rings down and spawn the ones that close."""
        still_pending = []
        for warning in self._warnings:
            warning.remaining -= dt
            if warning.remaining > 0.0:
                still_pending.append(warning)
                continue
            if self._pool.spawn_enemy(
                warning.position, warning.enemy_type, warning.health
            ):
                self._enemies_alive += 1
        self._warnings = still_pending

    @property
    def warnings(self) -> list[tuple[Vector2, float]]:
        """`(position, progress)` per telegraphed spawn, for the renderer.

        Progress runs 0.0 when the ring appears to 1.0 as it closes.
        """
        return [
            (
                warning.position,
                1.0 - max(0.0, warning.remaining) / self.WARNING_LEAD,
            )
            for warning in self._warnings
        ]

    @property
    def wave_fraction(self) -> float:
        """Fraction of this wave still to be dealt with, for the HUD meter."""
        if self._wave_size <= 0:
            return 0.0
        return min(1.0, self.enemies_remaining / self._wave_size)

    def on_enemy_killed(self) -> None:
        """Handle enemy kill notification."""
        self._enemies_alive = max(0, self._enemies_alive - 1)

        # Check for wave completion
        if self._enemies_alive == 0 and self._director.is_idle and not self._warnings:
            self._dispatcher.dispatch(WaveCompleteEvent(wave_number=self._current_wave))

    def _get_spawn_position(self, player_pos: Vector2) -> Vector2:
        """Get a spawn position away from the player.

        Args:
            player_pos: Current player position

        Returns:
            Spawn position outside the visible area
        """
        # Choose a random edge
        edge = self._rng.choice(["top", "bottom", "left", "right"])
        arena = self._arena

        x: float
        y: float
        if edge == "top":
            x = self._rng.uniform(arena.left, arena.right)
            y = arena.top - self.SPAWN_MARGIN
        elif edge == "bottom":
            x = self._rng.uniform(arena.left, arena.right)
            y = arena.bottom + self.SPAWN_MARGIN
        elif edge == "left":
            x = arena.left - self.SPAWN_MARGIN
            y = self._rng.uniform(arena.top, arena.bottom)
        else:  # right
            x = arena.right + self.SPAWN_MARGIN
            y = self._rng.uniform(arena.top, arena.bottom)

        return Vector2(x, y)

    @property
    def current_wave(self) -> int:
        """Get current wave number."""
        return self._current_wave

    @property
    def is_wave_active(self) -> bool:
        """Check if a wave is currently active."""
        return (
            not self._director.is_idle
            or self._enemies_alive > 0
            or bool(self._warnings)
        )

    @property
    def enemies_remaining(self) -> int:
        """Get total remaining enemies (alive + not yet released)."""
        return self._enemies_alive + self._pending_in_wave + len(self._warnings)
