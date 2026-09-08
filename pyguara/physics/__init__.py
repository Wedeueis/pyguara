"""Physics subsystem."""

from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.collision_system import CollisionSystem
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.joint_system import JointSystem
from pyguara.physics.joints import (
    Joint,
    create_distance_joint,
    create_pin_joint,
    create_slider_joint,
    create_spring_joint,
)
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.trigger_system import TriggerSystem
from pyguara.physics.trigger_volume import EntityTags, TriggerVolume
from pyguara.physics.types import BodyType, CollisionLayer, PhysicsMaterial, ShapeType

__all__ = [
    "BodyType",
    "ShapeType",
    "CollisionLayer",
    "PhysicsMaterial",
    "RigidBody",
    "Collider",
    "PhysicsSystem",
    "PymunkEngine",
    "CollisionSystem",
    "Joint",
    "JointSystem",
    "create_pin_joint",
    "create_distance_joint",
    "create_spring_joint",
    "create_slider_joint",
    "TriggerVolume",
    "EntityTags",
    "TriggerSystem",
]
