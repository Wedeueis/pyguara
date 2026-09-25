"""Protocolo Bandeira - ECS Components.

Pure data containers for the shooter game.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from pyguara.common.types import Color, Vector2
from pyguara.ecs.component import BaseComponent, pure_query

if TYPE_CHECKING:  # pragma: no cover -- import cycle: navigation imports nothing here
    from games.protocolo_bandeira.navigation import ChaserNavigator


class EntityTeam(Enum):
    """Team affiliation for combat."""

    PLAYER = auto()
    ENEMY = auto()
    NEUTRAL = auto()


class EnemyType(Enum):
    """Types of enemies."""

    CHASER = auto()  # Runs at player
    SHOOTER = auto()  # Stays at range and shoots
    BOMBER = auto()  # Explodes on contact


@dataclass
class Weapon(BaseComponent):
    """Weapon configuration for shooting entities."""

    fire_rate: float = 0.2  # Seconds between shots
    bullet_speed: float = 500.0
    bullet_damage: int = 1
    spread: float = 0.0  # Angle spread in degrees
    cooldown: float = 0.0  # Current cooldown timer

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()

    @pure_query
    def can_fire(self) -> bool:
        """Whether the cooldown has elapsed. Reads only its own field."""
        return self.cooldown <= 0


@dataclass
class EnemyAI(BaseComponent):
    """AI configuration for enemies."""

    enemy_type: EnemyType = EnemyType.CHASER
    detection_range: float = 300.0
    attack_range: float = 150.0
    move_speed: float = 100.0
    attack_cooldown: float = 1.0
    current_cooldown: float = 0.0

    # State tracking
    target_position: Vector2 | None = None
    is_alerted: bool = False

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class Movement(BaseComponent):
    """Movement data for entities."""

    velocity: Vector2 = field(default_factory=Vector2.zero)
    speed: float = 200.0
    facing_angle: float = 0.0  # Radians

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class Score(BaseComponent):
    """Player score tracking."""

    value: int = 0
    kills: int = 0
    wave: int = 1

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class ShooterSprite(BaseComponent):
    """Visual representation for shooter entities."""

    color: Color = field(default_factory=lambda: Color(200, 200, 200))
    size: float = 20.0  # Radius
    shape: str = "circle"  # "circle", "triangle", "square"

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class AIContext:
    """Context object passed to AI behavior trees.

    The behaviour tree's action nodes write their intent back here and
    `systems.EnemyAISystem` reads it after the tick -- so the two output
    fields below are declared rather than attached on the fly. They used
    to be bare attribute assignments inside `ai_behaviors.chase_player`,
    read back through `hasattr`, which meant a typo in either half was a
    silently motionless enemy.
    """

    entity_id: str
    position: Vector2
    player_position: Vector2 | None
    distance_to_player: float
    dt: float
    is_alerted: bool = False

    # --- what the tree decided, read back by the AI system ---
    move_direction: Vector2 | None = None
    should_attack: bool = False

    # Routes a chaser around the termite mounds when it cannot see the
    # player (`navigation.py`). None -- which is what every test building
    # a bare context gets -- falls back to the straight line this game
    # shipped with.
    navigator: "ChaserNavigator | None" = None

    # Copied off the enemy's own `EnemyAI` each tick. The condition nodes
    # used to hardcode 300/150 instead, which meant every per-type range
    # configured in `EnemyPool.spawn_enemy` was silently ignored -- a
    # shooter's 400 and a bomber's 350 both behaved as 300.
    detection_range: float = 300.0
    attack_range: float = 150.0

    def in_detection_range(self, detection_range: float) -> bool:
        """Check if player is in detection range."""
        return (
            self.player_position is not None
            and self.distance_to_player < detection_range
        )

    def in_attack_range(self, attack_range: float) -> bool:
        """Check if player is in attack range."""
        return (
            self.player_position is not None and self.distance_to_player < attack_range
        )


def fire(weapon: Weapon) -> None:
    """Start `weapon`'s cooldown, marking it as having just fired.

    A free function because it mutates: `can_fire` reads and stays a
    method, this writes and does not. Same split the engine uses for
    `Health`/`apply_damage`.

    Args:
        weapon: The weapon that fired.
    """
    weapon.cooldown = weapon.fire_rate


def add_kill(score: Score, points: int = 100) -> None:
    """Record one kill against `score`.

    Args:
        score: The score to credit.
        points: What the kill was worth.
    """
    score.kills += 1
    score.value += points
