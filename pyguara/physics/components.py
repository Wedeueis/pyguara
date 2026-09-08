"""ECS components for physics."""

from dataclasses import dataclass, field

from pyguara.common.types import Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.physics.protocols import IPhysicsBody
from pyguara.physics.types import BodyType, CollisionLayer, PhysicsMaterial, ShapeType


@dataclass
class Collider(BaseComponent):
    """
    Component defining the collision shape.

    Attributes:
        shape_type: Geometric shape.
        dimensions: Dimensions [radius] for circle, or [width, height] for box.
        offset: Local offset from the RigidBody center.
        one_way: Solid from one side only. A character jumping from below
            passes through and then lands on top -- the drop-through platform
            every 2D platformer has. Chipmunk has no notion of this; the
            contact is rejected per step when the other body is on the
            pass-through side.
        one_way_normal: Which side is solid, in world space. Defaults to
            `(0, -1)`: up the screen, i.e. a platform you land on from above.
            Ignored unless `one_way` is set.
    """

    shape_type: ShapeType = ShapeType.BOX
    dimensions: list[float] = field(default_factory=lambda: [32.0, 32.0])
    offset: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    material: PhysicsMaterial = field(default_factory=PhysicsMaterial)
    layer: CollisionLayer = field(default_factory=CollisionLayer)
    is_sensor: bool = False
    one_way: bool = False
    one_way_normal: Vector2 = field(default_factory=lambda: Vector2(0, -1))

    def __post_init__(self) -> None:
        """Initialize base component state."""
        super().__init__()


@dataclass
class RigidBody(BaseComponent):
    """
    Component representing a physical object.

    Attributes:
        mass: The mass of the body (default 1.0).
        body_type: Static, Dynamic, or Kinematic.
        fixed_rotation: If True, physics won't rotate the object.
        gravity_scale: Scale factor for gravity applied to this body.
    """

    # Dataclass fields
    mass: float = 1.0
    body_type: BodyType = BodyType.DYNAMIC
    fixed_rotation: bool = False
    gravity_scale: float = 1.0

    # Internal handle (injected by system)
    _body_handle: IPhysicsBody | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize base component state."""
        super().__init__()

    @property
    def handle(self) -> IPhysicsBody | None:
        """Access the underlying physics body interface."""
        return self._body_handle


@dataclass
class CharacterBody(BaseComponent):
    """A character moved by `CharacterMover`, not the Chipmunk solver.

    Replaces `RigidBody` for a platformer character: there is no shape
    registered with the physics engine at all, so the character cannot
    detect its own collider (the self-detection bug class this audit found
    for ground rays becomes structurally impossible rather than guarded
    against) and Chipmunk friction is never asked to carry or push it --
    `SolidSystem`/`SolidMover` do that explicitly instead.

    Attributes:
        velocity: Current velocity in pixels/second. `PlatformerSystem`
            integrates gravity into this itself, since nothing else does
            for an entity with no physics body.
        grounded: Whether the character is currently resting on something.
            Set every tick from `CharacterMover.probe()`, not from
            `MoveResult.grounded` -- a resting character often has zero
            vertical velocity, and a move of zero distance never attempts
            a step to report blocked.
        riding: Entity id of the `MovingSolid` currently carrying this
            character, or None. Lets `SolidSystem` recognise the same
            platform across ticks rather than re-detecting a rider fresh
            every frame.
        squished: Set when a solid pushed this character somewhere with no
            free space at all. The game decides what that means; nothing
            here clears it automatically.
        external_velocity: A knockback velocity overriding normal input
            control while `external_velocity_timer` is running.
        external_velocity_timer: Seconds remaining on the current
            knockback. Ticks down to zero in `PlatformerSystem.update()`.
    """

    velocity: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    grounded: bool = field(default=False, init=False)
    riding: int | str | None = field(default=None, init=False)
    squished: bool = field(default=False, init=False)

    external_velocity: Vector2 = field(
        default_factory=lambda: Vector2(0, 0), init=False
    )
    external_velocity_timer: float = field(default=0.0, init=False)

    # Celeste-style sub-pixel accumulator, round-tripped through
    # CharacterMover.move() every tick. Never read by game code.
    _remainder: Vector2 = field(default_factory=lambda: Vector2(0, 0), repr=False)

    def __post_init__(self) -> None:
        """Initialize base component state."""
        super().__init__()


@dataclass
class MovingSolid(BaseComponent):
    """Marks an entity whose motion should carry and push actors.

    A `MovingSolid` is still an ordinary `RigidBody`/`Collider` as far as
    Chipmunk is concerned (so genuinely dynamic bodies -- debris, ragdolls
    -- keep colliding with it normally); `SolidSystem` additionally moves
    any `CharacterBody` resting on or in the way of it by the same delta
    each tick it moves, using `SolidMover`.
    """

    def __post_init__(self) -> None:
        """Initialize base component state."""
        super().__init__()


@dataclass
class Pushable(BaseComponent):
    """Marks a `MovingSolid` a character can shove, not just ride or block on.

    When `CharacterMover` finds its sweep blocked by a `Pushable` entity,
    it asks `SolidMover` to move that entity by the remaining delta first:
    if the pushable can move, the character continues behind it; if the
    pushable is itself blocked, the character stops too.
    """

    def __post_init__(self) -> None:
        """Initialize base component state."""
        super().__init__()
