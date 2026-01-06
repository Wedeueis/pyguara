"""System responsible for syncing ECS entities with the Physics Engine."""

from typing import List

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.physics.types import BodyType


class PhysicsSystem:
    """
    The bridge between the ECS world and the Physics Backend (Pymunk).

    It synchronizes the state of ECS 'Transform' components with the
    underlying physics simulation bodies.
    """

    def __init__(
        self, engine: IPhysicsEngine, event_dispatcher: EventDispatcher
    ) -> None:
        """
        Initialize the physics system.

        Args:
            engine: The physics engine backend.
            event_dispatcher: The global event dispatcher.
        """
        self._engine = engine
        self._dispatcher = event_dispatcher

        # We use (0,0) for top-down games. Use (0, 980) for side-scrollers.
        self._engine.initialize(gravity=Vector2(0, 0))

    def update(self, entities: List[Entity], dt: float) -> None:
        """
        Advance the physics simulation and sync transforms.

        Args:
            entities: List of entities that have both RigidBody and Transform.
            dt: Delta time in seconds.
        """
        # 1. Sync ECS -> Physics Engine
        for entity in entities:
            # OPTIMIZATION: Use get_component instead of attribute access
            transform = entity.get_component(Transform)
            rb = entity.get_component(RigidBody)

            # If the body hasn't been created in the engine yet, create it
            # FIX: Check backing field directly
            if rb._body_handle is None:
                self._create_physics_entity(entity, transform, rb)

            # Sync Transform -> Physics (Kinematic or manual overrides)
            # If we move a kinematic body in game, we must update physics engine
            # FIX: Use backing field
            if rb.body_type == BodyType.KINEMATIC and rb._body_handle:
                rb._body_handle.position = transform.position
                rb._body_handle.rotation = transform.rotation

        # 2. Step the Simulation
        # FIX: Protocol defines this as 'update', not 'step'
        self._engine.update(dt)

        # 3. Sync Physics Engine -> ECS
        for entity in entities:
            transform = entity.get_component(Transform)
            rb = entity.get_component(RigidBody)

            # If physics moved the object, update the game transform
            # FIX: Use backing field
            if rb._body_handle and rb.body_type == BodyType.DYNAMIC:
                transform.position = rb._body_handle.position
                transform.rotation = rb._body_handle.rotation

    def _create_physics_entity(
        self, entity: Entity, transform: Transform, rb: RigidBody
    ) -> None:
        """
        Register ECS entity with the physics backend.

        Internal helper that handles the specific sequence of body creation
        and shape attachment.
        """
        # 1. Create Body in the backend
        body_handle = self._engine.create_body(
            entity.id, rb.body_type, transform.position
        )
        body_handle.rotation = transform.rotation

        # FIX: Assign to backing field (handle is read-only property)
        rb._body_handle = body_handle

        # 2. Add Collider if present (Optimized Check)
        if entity.has_component(Collider):
            col = entity.get_component(Collider)

            self._engine.add_shape(
                body_handle,
                col.shape_type,
                col.dimensions,
                col.offset,
                col.material,
                col.layer,
                col.is_sensor,
            )
