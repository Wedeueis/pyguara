"""Platformer controller component for 2D character movement.

This module provides a complete platformer movement solution with features like
ground detection, jump mechanics, coyote time, jump buffering, wall sliding,
and wall jumping. It's designed for responsive, game-feel-oriented character
control in 2D platformer games.

Movement/jump logic lives in `PlatformerSystem`; this component only carries
data plus a small set of side-effect-free query predicates
(`can_jump()`/`can_wall_jump()`/`is_wall_sliding()`).

Usage:
    from pyguara.physics.platformer_controller import PlatformerController, PlatformerInput

    # Add controller to player entity
    player.add_component(PlatformerController(
        move_speed=200.0,
        jump_force=400.0,
        coyote_time=0.15,
        jump_buffer=0.1
    ))

    # In your input-to-system code, submit this tick's intent
    controller = player.get_component(PlatformerController)
    controller.pending_input = PlatformerInput(move=-1.0, jump=True)
"""

from dataclasses import dataclass, field
from enum import Enum, auto

from pyguara.ecs.component import BaseComponent


class PlatformerState(Enum):
    """States for platformer character."""

    GROUNDED = auto()
    AIRBORNE = auto()
    WALL_SLIDE = auto()


@dataclass
class PlatformerInput:
    """One tick's movement/jump intent, submitted by an input-to-system caller.

    Consumed and reset by `PlatformerSystem.update()` each fixed tick -- not
    read by anything else.
    """

    move: float = 0.0
    jump: bool = False


@dataclass
class PlatformerController(BaseComponent):
    """Component for 2D platformer character movement.

    The PlatformerController provides responsive platformer movement with
    modern game-feel features. It handles ground detection, jumping, coyote
    time, jump buffering, wall sliding, and wall jumping.

    The controller requires a RigidBody component to apply movement forces
    and velocities. Ground detection is performed via raycasting.

    Note:
        Pure data plus side-effect-free query predicates
        (`can_jump()`/`can_wall_jump()`/`is_wall_sliding()`). Movement/jump
        logic lives in `PlatformerSystem`, driven by `pending_input`.

    Attributes:
        move_speed: Horizontal movement speed in pixels/second.
        jump_force: Upward force applied when jumping.
        max_fall_speed: Maximum falling velocity (terminal velocity).
        acceleration: How quickly character reaches move_speed (0-1, 1=instant).
        air_control: Movement control in air (0-1, 1=full control).

        coyote_time: Grace period to jump after leaving ground (seconds).
        jump_buffer: Time window to buffer early jump input (seconds).

        wall_slide_enabled: Whether wall sliding is enabled.
        wall_slide_speed: Falling speed when sliding on wall.
        wall_jump_enabled: Whether wall jumping is enabled.
        wall_jump_force_x: Horizontal force for wall jump.
        wall_jump_force_y: Vertical force for wall jump.

        wall_check_distance: Clearance beyond each side probed for a wall.
            Ground has no equivalent: `CharacterMover.probe()` checks
            exactly one pixel below, Celeste's model, not a configurable
            distance.

        current_state: Current movement state (internal).
        is_grounded: Whether character is on ground (internal).
        on_wall_left: Whether character is touching left wall (internal).
        on_wall_right: Whether character is touching right wall (internal).
        coyote_timer: Time since leaving ground (internal).
        jump_buffer_timer: Time jump was buffered (internal).
        facing_right: Direction character is facing (internal).
        move_input: Current horizontal movement input -1/0/1 (internal).
    """

    _allow_methods: bool = field(default=True, repr=False, init=False)

    # Movement parameters
    move_speed: float = 200.0
    jump_force: float = 400.0
    max_fall_speed: float = 500.0
    acceleration: float = 0.15  # Lower = more gradual acceleration
    air_control: float = 0.7  # Reduced control in air

    # Jump feel parameters
    coyote_time: float = 0.15  # Grace period to jump after leaving ledge
    jump_buffer: float = 0.1  # Buffer early jump inputs

    # Wall mechanics
    wall_slide_enabled: bool = True
    wall_slide_speed: float = 50.0  # Slow falling on walls
    wall_jump_enabled: bool = True
    wall_jump_force_x: float = 300.0
    wall_jump_force_y: float = 350.0

    # Detection parameters
    wall_check_distance: float = 5.0  # Clearance beyond each side

    # Internal state (managed by PlatformerSystem)
    current_state: PlatformerState = field(default=PlatformerState.AIRBORNE, init=False)
    is_grounded: bool = field(default=False, init=False)
    on_wall_left: bool = field(default=False, init=False)
    on_wall_right: bool = field(default=False, init=False)
    coyote_timer: float = field(default=0.0, init=False)
    jump_buffer_timer: float = field(default=0.0, init=False)
    facing_right: bool = field(default=True, init=False)
    move_input: float = field(default=0.0, init=False)

    # Jump state
    _jump_requested: bool = field(default=False, init=False, repr=False)
    _can_double_jump: bool = field(default=False, init=False, repr=False)
    _jump_used: bool = field(
        default=False, init=False, repr=False
    )  # Prevents air jumps

    # This tick's movement/jump intent (written by an input-to-system caller,
    # consumed and reset by PlatformerSystem.update() every fixed tick)
    pending_input: PlatformerInput = field(default_factory=PlatformerInput, init=False)

    def __post_init__(self) -> None:
        """Initialize base component state."""
        super().__init__()

    def can_jump(self) -> bool:
        """Check if character can currently jump.

        Returns:
            True if jump is possible (grounded or in coyote time, and haven't jumped yet).
        """
        # Can't jump if we've already used our jump (prevents air jumps)
        if self._jump_used:
            return False
        return self.is_grounded or self.coyote_timer > 0

    def can_wall_jump(self) -> bool:
        """Check if character can wall jump.

        Returns:
            True if wall jump is possible.
        """
        return self.wall_jump_enabled and (self.on_wall_left or self.on_wall_right)

    def is_wall_sliding(self) -> bool:
        """Check if character is wall sliding.

        Returns:
            True if currently wall sliding.
        """
        return self.current_state == PlatformerState.WALL_SLIDE
