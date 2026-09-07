"""System responsible for syncing ECS entities with the Physics Engine."""

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.events import EntityDestroyed
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.protocols import IPhysicsBody, IPhysicsEngine
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
        self._pending_teardown: list[IPhysicsBody] = []

        if gravity is None:
            gravity = Vector2(0, 0)
        self._engine.initialize(gravity=gravity)

        self._dispatcher.subscribe(EntityDestroyed, self._on_entity_destroyed)

    def _on_entity_destroyed(self, event: EntityDestroyed) -> None:
        """Queue an entity's physics body for teardown, if it has one.

        Components are still intact at dispatch time, so the RigidBody is
        read directly off the event's entity rather than re-queried later.
        """
        if not event.entity.has_component(RigidBody):
            return
        rb = event.entity.get_component(RigidBody)
        if rb._body_handle is None:
            return
        self._pending_teardown.append(rb._body_handle)

    def update(self, dt: float) -> None:
        """
        Advance the physics simulation and sync transforms.

        Args:
            dt: Delta time in seconds.

        Note:
            P2-013: Refactored to Pull pattern. System queries entities internally.
        """
        # Drain pending teardowns before stepping, so destroyed bodies never
        # participate in this step's simulation.
        for handle in self._pending_teardown:
            self._engine.destroy_body(handle)
        self._pending_teardown.clear()

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
        # This transform is now stepped at the fixed physics rate, so the
        # renderer must draw it between ticks or motion stutters on any
        # display not locked to that rate. Opt in here rather than asking
        # every game to remember: the system that makes a transform
        # fixed-stepped is the one that knows it needs interpolating.
        transform.interpolate = True
        transform.previous_position = transform.position

        # 1. Create Body in the backend
        body_handle = self._engine.create_body(
            entity.id,
            rb.body_type,
            transform.position,
            rb.mass,
            fixed_rotation=rb.fixed_rotation,
            gravity_scale=rb.gravity_scale,
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
