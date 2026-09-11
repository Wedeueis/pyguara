"""Protocolo Bandeira - Game Events.

Custom events for shooter game logic.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from games.protocolo_bandeira.components import EntityTeam
from pyguara.common.types import Vector2


@dataclass
class BulletFiredEvent:
    """Fired when a bullet is shot."""

    position: Vector2
    direction: Vector2
    team: EntityTeam
    damage: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class EnemyKilledEvent:
    """Fired when an enemy is killed."""

    position: Vector2
    points: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class PlayerDamagedEvent:
    """Fired when player takes damage."""

    damage: int
    remaining_health: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class PlayerDeathEvent:
    """Fired when player dies."""

    final_score: int
    total_kills: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class WaveStartEvent:
    """Fired when a new wave begins."""

    wave_number: int
    enemy_count: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class WaveCompleteEvent:
    """Fired when all enemies in a wave are defeated."""

    wave_number: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class SpawnEnemyEvent:
    """Request to spawn an enemy."""

    position: Vector2
    enemy_type: str
    timestamp: float = field(default_factory=time.time)
    source: Any = None
