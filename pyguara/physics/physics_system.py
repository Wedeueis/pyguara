"""System responsible for syncing ECS entities with the Physics Engine."""

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.physics.types import BodyType


class PhysicsSystem:
    """
    The bridge between the ECS world and the Physics Backend (Pymunk).

    It synchronizes the state of ECS 'Transform' components with the
    underlying physics simulation bodies.

    Architecture: Self-Sufficient System (Pull Pattern)
    - Queries entities internally via EntityManager
    - Compatible with SystemManager orchestration
    """

    def __init__(
        self,
        engine: IPhysicsEngine,
        entity_manager: EntityManager,
        event_dispatcher: EventDispatcher,
        gravity: Vector2 | None = None,
    ) -> None:
        """
        Initialize the physics system.

        Args:
            engine: The physics engine backend.
            entity_manager: The entity manager for querying physics entities.
            event_dispatcher: The global event dispatcher.
            gravity: World gravity vector. Defaults to (0, 0) for top-down games.
                     Use (0, 800) or similar for side-scrollers.
        """
        self._engine = engine
        self._entity_manager = entity_manager
        self._dispatcher = event_dispatcher

        if gravity is None:
            gravity = Vector2(0, 0)
        self._engine.initialize(gravity=gravity)

    def update(self, dt: float) -> None:
        """
        Advance the physics simulation and sync transforms.

        Args:
            dt: Delta time in seconds.

        Note:
            P2-013: Refactored to Pull pattern. System queries entities internally.
        """
        # Query physics entities (Pull pattern)
        entities = list(self._entity_manager.get_entities_with(Transform, RigidBody))

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
            entity.id, rb.body_type, transform.position, rb.mass
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

    def cleanup(self) -> None:
        """Cleanup physics resources to prevent CFFI errors at exit."""
        if hasattr(self._engine, "cleanup"):
            self._engine.cleanup()
