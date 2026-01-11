"""Physics domain types and enumerations."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Union

from pyguara.common.types import Vector2


class BodyType(Enum):
    """
    Defines how a physics body behaves.

    Attributes:
        DYNAMIC: Fully simulated, affected by forces and collisions.
        KINEMATIC: Moved manually by code, pushes dynamic objects, infinite mass.
        STATIC: Immovable (walls, terrain).
    """

    DYNAMIC = auto()
    KINEMATIC = auto()
    STATIC = auto()


class ShapeType(Enum):
    """Available geometric shapes for colliders."""

    CIRCLE = auto()
    BOX = auto()
    SEGMENT = auto()
    POLYGON = auto()


class JointType(Enum):
    """Types of physics joints/constraints.

    Joints connect two RigidBodies and constrain their relative motion.

    Attributes:
        PIN: Revolute/pivot joint - allows rotation around a shared point.
        DISTANCE: Maintains fixed distance between two points on bodies.
        SPRING: Spring-damper joint - connects bodies with elastic force.
        SLIDER: Prismatic joint - allows sliding along a fixed axis.
        GEAR: Links the rotation of two bodies.
        MOTOR: Applies continuous rotational or linear force.
    """

    PIN = auto()
    DISTANCE = auto()
    SPRING = auto()
    SLIDER = auto()
    GEAR = auto()
    MOTOR = auto()


@dataclass
class CollisionLayer:
    """
    Configuration for collision filtering.

    Args:
        category: Bitmask representing what this object IS.
        mask: Bitmask representing what this object COLLIDES WITH.
        group: Group index (objects in same non-zero group don't collide).
    """

    category: int = 1
    mask: int = 0xFFFFFFFF
    group: int = 0


@dataclass
class PhysicsMaterial:
    """
    Physical properties of a surface.

    Args:
        friction: Coefficient of friction (0.0 = slippery, 1.0 = sticky).
        restitution: Bounciness (0.0 = no bounce, 1.0 = perfect bounce).
        density: Used to calculate mass from shape size.
    """

    friction: float = 0.5
    restitution: float = 0.0
    density: float = 1.0


@dataclass
class RaycastHit:
    """
    Result of a raycast query.

    Args:
        position: World coordinates of the hit point.
        normal: Surface normal at the hit point.
        distance: Distance from ray origin to hit point.
        entity_id: ID of the hit entity (if available).
    """

    position: Vector2
    normal: Vector2
    distance: float
    entity_id: Optional[Union[int, str]] = None
