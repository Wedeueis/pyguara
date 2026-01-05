"""Physics system handling simulation and synchronization."""

from typing import Any, List

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.components.rigid_body import RigidBody
from pyguara.physics.components.collider import Collider
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.physics.types import BodyType


class PhysicsSystem:
    """
    Synchronizes ECS entities with the physics backend.

    Responsibilities:
    1. Initialize RigidBodies for entities that have them.
    2. Sync Transform -> PhysicsBody (for Kinematic/Teleport).
    3. Step the Physics Engine.
    4. Sync PhysicsBody -> Transform (for Dynamic).
    5. Dispatch collision events.
    """

    def __init__(
        self, engine: IPhysicsEngine, event_dispatcher: EventDispatcher
    ) -> None:
        """Initialize the physics system."""
        self.engine = engine
        self.dispatcher = event_dispatcher
        self.engine.initialize(gravity=Vector2(0, 0))  # Default top-down gravity

    def update(self, entities: List[Any], dt: float) -> None:
        """Run the main physics loop.

        Args:
            entities: List of entities with (Transform, RigidBody, Collider).
            dt: Delta time in seconds.
        """
        # 1. Initialization & Sync (Input to Physics)
        for entity in entities:
            transform: Transform = entity.transform
            rb: RigidBody = entity.rigidbody

            # Create body if missing
            if rb._body_handle is None:
                self._create_physics_entity(entity, transform, rb)

            # Sync Transform -> Physics (Kinematic or manual overrides)
            if rb.body_type == BodyType.KINEMATIC:
                if rb._body_handle:
                    rb._body_handle.position = transform.position
                    rb._body_handle.rotation = transform.rotation

        # 2. Simulation Step
        self.engine.update(dt)

        # 3. Sync (Output from Physics)
        for entity in entities:
            rb_sync = entity.rigidbody

            if rb_sync.body_type == BodyType.DYNAMIC and rb_sync._body_handle:
                transform_sync = entity.transform
                transform_sync.position = rb_sync._body_handle.position
                transform_sync.rotation = rb_sync._body_handle.rotation

    def _create_physics_entity(
        self, entity: Any, transform: Transform, rb: RigidBody
    ) -> None:
        """Register ECS entity with the physics backend."""
        # Create Body
        body_handle = self.engine.create_body(
            entity.id, rb.body_type, transform.position
        )
        body_handle.rotation = transform.rotation
        rb._body_handle = body_handle

        # Add Collider if present
        if hasattr(entity, "collider"):
            col: Collider = entity.collider
            self.engine.add_shape(
                body_handle,
                col.shape_type,
                col.dimensions,
                col.offset,
                col.material,
                col.layer,
                col.is_sensor,
            )
