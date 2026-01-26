"""Protocolo Bandeira - ECS Components.

Pure data containers for the shooter game.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from pyguara.ecs.component import BaseComponent
from pyguara.common.types import Vector2, Color


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

    def can_fire(self) -> bool:
        """Check if weapon can fire."""
        return self.cooldown <= 0

    def fire(self) -> None:
        """Fire the weapon, starting cooldown."""
        self.cooldown = self.fire_rate


@dataclass
class Bullet(BaseComponent):
    """Bullet projectile data."""

    damage: int = 1
    owner_team: EntityTeam = EntityTeam.PLAYER
    velocity: Vector2 = field(default_factory=Vector2.zero)
    lifetime: float = 3.0  # Seconds before despawn
    active: bool = True

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


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
    target_position: Optional[Vector2] = None
    is_alerted: bool = False

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class Health(BaseComponent):
    """Entity health."""

    current: int = 3
    max_health: int = 3
    invincible_time: float = 0.0

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()

    def take_damage(self, amount: int = 1) -> bool:
        """Take damage. Returns True if still alive."""
        if self.invincible_time > 0:
            return True
        self.current = max(0, self.current - amount)
        return self.current > 0


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
class Poolable(BaseComponent):
    """Marker for pooled entities."""

    pool_name: str = "default"
    is_active: bool = False

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

    def add_kill(self, points: int = 100) -> None:
        """Add a kill and points."""
        self.kills += 1
        self.value += points


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
    """Context object passed to AI behavior trees."""

    entity_id: str
    position: Vector2
    player_position: Optional[Vector2]
    distance_to_player: float
    dt: float
    is_alerted: bool = False

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
