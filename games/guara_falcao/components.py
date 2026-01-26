"""Guará & Falcão - ECS Components.

Pure data containers for the platformer game.
"""

from dataclasses import dataclass, field
from enum import Enum, auto

from pyguara.ecs.component import BaseComponent
from pyguara.common.types import Vector2, Color


class PlayerAnimState(Enum):
    """Animation states for the player character."""

    IDLE = auto()
    RUN = auto()
    JUMP = auto()
    FALL = auto()
    WALL_SLIDE = auto()
    LAND = auto()


@dataclass
class PlayerState(BaseComponent):
    """Tracks player state for animation and logic."""

    current_state: PlayerAnimState = PlayerAnimState.IDLE
    facing_right: bool = True
    state_time: float = 0.0  # Time in current state

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()

    def set_state(self, new_state: PlayerAnimState) -> bool:
        """Change state and reset timer. Returns True if state changed."""
        if new_state != self.current_state:
            self.current_state = new_state
            self.state_time = 0.0
            return True
        return False


@dataclass
class Health(BaseComponent):
    """Entity health tracking."""

    current: int = 3
    max_health: int = 3
    invincible_time: float = 0.0  # Invincibility frames

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()

    def take_damage(self, amount: int = 1) -> bool:
        """Take damage. Returns True if still alive."""
        if self.invincible_time > 0:
            return True
        self.current = max(0, self.current - amount)
        self.invincible_time = 1.5  # Brief invincibility
        return self.current > 0

    def heal(self, amount: int = 1) -> None:
        """Heal up to max health."""
        self.current = min(self.max_health, self.current + amount)


@dataclass
class Collectible(BaseComponent):
    """Marks an entity as a collectible item."""

    value: int = 1
    collect_type: str = "coin"  # "coin", "health", "power"
    collected: bool = False

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class ZoneTrigger(BaseComponent):
    """Defines a zone that triggers events when entered."""

    zone_name: str = "checkpoint"
    spawn_point: Vector2 = field(default_factory=Vector2.zero)
    triggered: bool = False

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class PlatformSprite(BaseComponent):
    """Visual representation for platform entities."""

    color: Color = field(default_factory=lambda: Color(80, 80, 100))
    size: Vector2 = field(default_factory=lambda: Vector2(100, 20))

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class CharacterSprite(BaseComponent):
    """Visual representation for character entities."""

    color: Color = field(default_factory=lambda: Color(200, 100, 80))
    size: Vector2 = field(default_factory=lambda: Vector2(32, 48))
    offset: Vector2 = field(default_factory=Vector2.zero)

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class CameraTarget(BaseComponent):
    """Marks an entity as the camera follow target."""

    look_ahead: float = 50.0  # Pixels to look ahead in movement direction
    vertical_offset: float = -30.0  # Offset camera up slightly

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class Hazard(BaseComponent):
    """Marks an entity as a hazard that damages the player."""

    damage: int = 1
    knockback_force: float = 200.0

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class Score(BaseComponent):
    """Tracks player score."""

    value: int = 0
    coins_collected: int = 0

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()

    def add_coins(self, amount: int = 1) -> None:
        """Add coins and update score."""
        self.coins_collected += amount
        self.value += amount * 100
