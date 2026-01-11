"""Physics joint components and utilities.

This module provides joint/constraint components that connect RigidBodies and
constrain their relative motion. Joints are essential for creating complex
physical systems like ragdolls, vehicles, rope chains, and mechanical contraptions.

Usage:
    from pyguara.physics.joints import Joint, create_pin_joint, create_spring_joint

    # Create a pin joint (revolute)
    entity_a.add_component(create_pin_joint(
        target_entity_id=entity_b.id,
        anchor_a=Vector2(0, 10),
        anchor_b=Vector2(0, -10)
    ))

    # Create a spring joint
    entity_a.add_component(create_spring_joint(
        target_entity_id=entity_b.id,
        rest_length=100.0,
        stiffness=500.0,
        damping=20.0
    ))
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from pyguara.common.types import Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.physics.types import JointType


@dataclass
class Joint(BaseComponent):
    """Physics joint component connecting two RigidBodies.

    A Joint connects this entity's RigidBody to another entity's RigidBody,
    constraining their relative motion according to the joint type.

    The joint is created by the PhysicsSystem when both entities have RigidBody
    components. The joint will be automatically destroyed when either entity is
    removed or loses its RigidBody component.

    Attributes:
        joint_type: Type of constraint (PIN, DISTANCE, SPRING, SLIDER, GEAR, MOTOR).
        target_entity_id: ID of the entity to connect to.
        anchor_a: Local anchor point on this entity's body.
        anchor_b: Local anchor point on target entity's body.
        min_distance: Minimum distance (for DISTANCE/SLIDER joints).
        max_distance: Maximum distance (for DISTANCE/SLIDER joints).
        stiffness: Spring stiffness coefficient (for SPRING joints).
        damping: Spring damping coefficient (for SPRING joints).
        max_force: Maximum force the joint can apply (0 = infinite).
        collide_connected: Whether connected bodies can collide with each other.
        _joint_handle: Internal physics engine handle (managed by PhysicsSystem).
    """

    joint_type: JointType = JointType.PIN
    target_entity_id: str = ""
    anchor_a: Vector2 = field(default_factory=Vector2.zero)
    anchor_b: Vector2 = field(default_factory=Vector2.zero)

    # Distance/Slider constraints
    min_distance: float = 0.0
    max_distance: float = 100.0

    # Spring parameters
    stiffness: float = 100.0
    damping: float = 10.0

    # General parameters
    max_force: float = 0.0  # 0 = infinite force
    collide_connected: bool = False

    # Internal handle (injected by PhysicsSystem)
    _joint_handle: Optional[Any] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize base component state."""
        super().__init__()


# Factory functions for common joint types


def create_pin_joint(
    target_entity_id: str,
    anchor_a: Optional[Vector2] = None,
    anchor_b: Optional[Vector2] = None,
    max_force: float = 0.0,
    collide_connected: bool = False,
) -> Joint:
    """Create a pin/revolute joint connecting two bodies at anchor points.

    Pin joints allow free rotation around a shared pivot point but prevent
    translation. Useful for hinges, doors, pendulums, and rotating platforms.

    Args:
        target_entity_id: Entity ID to connect to.
        anchor_a: Local anchor point on first body (default: origin).
        anchor_b: Local anchor point on second body (default: origin).
        max_force: Maximum force limit (0 = infinite).
        collide_connected: Allow connected bodies to collide.

    Returns:
        Joint component configured as a pin joint.

    Example:
        # Create a door hinge
        door.add_component(create_pin_joint(
            target_entity_id=wall.id,
            anchor_a=Vector2(-32, 0),  # Left edge of door
            anchor_b=Vector2(0, 0)     # Wall attachment point
        ))
    """
    return Joint(
        joint_type=JointType.PIN,
        target_entity_id=target_entity_id,
        anchor_a=anchor_a or Vector2.zero(),
        anchor_b=anchor_b or Vector2.zero(),
        max_force=max_force,
        collide_connected=collide_connected,
    )


def create_distance_joint(
    target_entity_id: str,
    distance: float,
    anchor_a: Optional[Vector2] = None,
    anchor_b: Optional[Vector2] = None,
    max_force: float = 0.0,
    collide_connected: bool = False,
) -> Joint:
    """Create a distance joint maintaining fixed distance between bodies.

    Distance joints keep two anchor points at a constant distance apart.
    Useful for rigid connections, suspension systems, and distance constraints.

    Args:
        target_entity_id: Entity ID to connect to.
        distance: Fixed distance to maintain between anchor points.
        anchor_a: Local anchor point on first body (default: origin).
        anchor_b: Local anchor point on second body (default: origin).
        max_force: Maximum force limit (0 = infinite).
        collide_connected: Allow connected bodies to collide.

    Returns:
        Joint component configured as a distance joint.

    Example:
        # Create a rigid rod connecting two objects
        object_a.add_component(create_distance_joint(
            target_entity_id=object_b.id,
            distance=100.0
        ))
    """
    return Joint(
        joint_type=JointType.DISTANCE,
        target_entity_id=target_entity_id,
        anchor_a=anchor_a or Vector2.zero(),
        anchor_b=anchor_b or Vector2.zero(),
        min_distance=distance,
        max_distance=distance,
        max_force=max_force,
        collide_connected=collide_connected,
    )


def create_spring_joint(
    target_entity_id: str,
    rest_length: float,
    stiffness: float = 100.0,
    damping: float = 10.0,
    anchor_a: Optional[Vector2] = None,
    anchor_b: Optional[Vector2] = None,
    max_force: float = 0.0,
    collide_connected: bool = False,
) -> Joint:
    """Create a spring-damper joint with elastic behavior.

    Spring joints apply forces to maintain a rest length, allowing elastic
    compression and extension. Useful for suspension, bungee cords, and
    soft constraints.

    Args:
        target_entity_id: Entity ID to connect to.
        rest_length: Natural length of the spring (no force applied).
        stiffness: Spring stiffness (higher = stiffer, typically 50-500).
        damping: Damping coefficient (higher = less oscillation, typically 5-50).
        anchor_a: Local anchor point on first body (default: origin).
        anchor_b: Local anchor point on second body (default: origin).
        max_force: Maximum force limit (0 = infinite).
        collide_connected: Allow connected bodies to collide.

    Returns:
        Joint component configured as a spring joint.

    Example:
        # Create a suspension spring
        wheel.add_component(create_spring_joint(
            target_entity_id=chassis.id,
            rest_length=50.0,
            stiffness=200.0,
            damping=20.0
        ))
    """
    return Joint(
        joint_type=JointType.SPRING,
        target_entity_id=target_entity_id,
        anchor_a=anchor_a or Vector2.zero(),
        anchor_b=anchor_b or Vector2.zero(),
        min_distance=rest_length,
        max_distance=rest_length,
        stiffness=stiffness,
        damping=damping,
        max_force=max_force,
        collide_connected=collide_connected,
    )


def create_slider_joint(
    target_entity_id: str,
    min_distance: float = 0.0,
    max_distance: float = 100.0,
    anchor_a: Optional[Vector2] = None,
    anchor_b: Optional[Vector2] = None,
    max_force: float = 0.0,
    collide_connected: bool = False,
) -> Joint:
    """Create a slider/prismatic joint allowing linear motion within limits.

    Slider joints constrain bodies to move along a line with optional distance
    limits. Useful for pistons, sliding doors, and linear actuators.

    Args:
        target_entity_id: Entity ID to connect to.
        min_distance: Minimum allowed distance between anchors.
        max_distance: Maximum allowed distance between anchors.
        anchor_a: Local anchor point on first body (default: origin).
        anchor_b: Local anchor point on second body (default: origin).
        max_force: Maximum force limit (0 = infinite).
        collide_connected: Allow connected bodies to collide.

    Returns:
        Joint component configured as a slider joint.

    Example:
        # Create a sliding door
        door.add_component(create_slider_joint(
            target_entity_id=track.id,
            min_distance=0.0,
            max_distance=200.0  # Can slide up to 200 units
        ))
    """
    return Joint(
        joint_type=JointType.SLIDER,
        target_entity_id=target_entity_id,
        anchor_a=anchor_a or Vector2.zero(),
        anchor_b=anchor_b or Vector2.zero(),
        min_distance=min_distance,
        max_distance=max_distance,
        max_force=max_force,
        collide_connected=collide_connected,
    )


def create_rope_chain(
    entity_manager: Any,
    start_position: Vector2,
    segment_count: int,
    segment_length: float,
    segment_mass: float = 1.0,
    link_stiffness: float = 10000.0,
    link_damping: float = 100.0,
) -> list:
    """Create a rope/chain made of connected segments.

    This is a utility function that creates multiple entities connected by
    distance or spring joints, forming a flexible rope or rigid chain.

    Args:
        entity_manager: EntityManager to create entities in.
        start_position: Starting position of the rope (top/anchor point).
        segment_count: Number of segments in the rope.
        segment_length: Length of each segment.
        segment_mass: Mass of each segment.
        link_stiffness: Stiffness of spring links (higher = more rigid).
        link_damping: Damping of spring links (higher = less swing).

    Returns:
        List of created rope segment entities.

    Example:
        # Create a hanging rope with 10 segments
        from pyguara.physics.components import RigidBody, Collider
        from pyguara.physics.types import BodyType, ShapeType

        rope_segments = create_rope_chain(
            entity_manager=manager,
            start_position=Vector2(400, 100),
            segment_count=10,
            segment_length=20.0,
            segment_mass=0.5
        )

        # Attach first segment to a static anchor
        # (create anchor entity separately)
    """
    from pyguara.common.components import Transform
    from pyguara.physics.components import Collider, RigidBody
    from pyguara.physics.types import BodyType, ShapeType

    segments = []

    for i in range(segment_count):
        # Create segment entity
        segment = entity_manager.create_entity()

        # Position segment
        y_offset = i * segment_length
        segment.add_component(Transform(position=start_position + Vector2(0, y_offset)))

        # Add physics
        segment.add_component(
            RigidBody(
                mass=segment_mass, body_type=BodyType.DYNAMIC, fixed_rotation=False
            )
        )

        # Add collider (small circle)
        segment.add_component(
            Collider(shape_type=ShapeType.CIRCLE, dimensions=[segment_length / 4])
        )

        segments.append(segment)

        # Connect to previous segment
        if i > 0:
            segments[i - 1].add_component(
                create_spring_joint(
                    target_entity_id=segment.id,
                    rest_length=segment_length,
                    stiffness=link_stiffness,
                    damping=link_damping,
                )
            )

    return segments
