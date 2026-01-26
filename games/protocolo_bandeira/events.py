"""Protocolo Bandeira - Game Events.

Custom events for shooter game logic.
"""

from dataclasses import dataclass
from pyguara.common.types import Vector2

from games.protocolo_bandeira.components import EntityTeam


@dataclass
class BulletFiredEvent:
    """Fired when a bullet is shot."""

    position: Vector2
    direction: Vector2
    team: EntityTeam
    damage: int


@dataclass
class EnemyKilledEvent:
    """Fired when an enemy is killed."""

    position: Vector2
    points: int


@dataclass
class PlayerDamagedEvent:
    """Fired when player takes damage."""

    damage: int
    remaining_health: int


@dataclass
class PlayerDeathEvent:
    """Fired when player dies."""

    final_score: int
    total_kills: int


@dataclass
class WaveStartEvent:
    """Fired when a new wave begins."""

    wave_number: int
    enemy_count: int


@dataclass
class WaveCompleteEvent:
    """Fired when all enemies in a wave are defeated."""

    wave_number: int


@dataclass
class SpawnEnemyEvent:
    """Request to spawn an enemy."""

    position: Vector2
    enemy_type: str
