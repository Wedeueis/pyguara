"""System that turns ``Joint`` components into live physics constraints.

``Joint`` is a plain data component; on its own it does nothing. ``JointSystem``
is what reads it, asks the physics engine to create the matching constraint
once both connected bodies exist, and tears the constraint down again when
either entity -- or the ``Joint`` component itself -- goes away.

Like ``PhysicsSystem``, this is an opt-in system: a game that uses joints
creates one and ticks it each fixed step, after ``PhysicsSystem.update()`` so
that both bodies have been registered with the backend.

Usage:
    joint_system = JointSystem(engine, entity_manager, event_dispatcher)

    def fixed_update(self, fixed_dt: float) -> None:
        self.physics_system.update(fixed_dt)
        self.joint_system.update(fixed_dt)
"""

from typing import Any

from pyguara.ecs.events import EntityDestroyed
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.log import get_logger
from pyguara.physics.components import RigidBody
from pyguara.physics.joints import Joint
from pyguara.physics.protocols import IPhysicsEngine

logger = get_logger(__name__)


class JointSystem:
    """Creates and destroys physics constraints for ``Joint`` components.

    A ``Joint`` lives on one entity (call it the owner) and names a second
    entity by id. The constraint is created only once both entities have a
    ``RigidBody`` whose backend body exists; until then the joint is left
    pending and retried on the next ``update()``. This makes the system
    order-independent with respect to body creation -- a joint added the
    same tick as its bodies simply links up one tick later.

    The backend handle is stored on ``Joint._joint_handle`` (so the same
    component is never built twice) and mirrored in an internal table keyed
    by owner id, which is what teardown and reconciliation walk.

    Attributes:
        _engine: The physics engine backend.
        _entity_manager: EntityManager for resolving the target entity.
        _dispatcher: EventDispatcher, subscribed for ``EntityDestroyed``.
        _handles: Owner entity id -> backend joint handle, for live joints.
    """

    def __init__(
        self,
        engine: IPhysicsEngine,
        entity_manager: EntityManager,
        event_dispatcher: EventDispatcher,
    ) -> None:
        """Initialise the joint system and subscribe to entity destruction.

        Args:
            engine: The physics engine backend.
            entity_manager: EntityManager to resolve target entities.
            event_dispatcher: EventDispatcher to observe ``EntityDestroyed``.
        """
        self._engine = engine
        self._entity_manager = entity_manager
        self._dispatcher = event_dispatcher
        self._handles: dict[str, Any] = {}

        self._dispatcher.subscribe(EntityDestroyed, self._on_entity_destroyed)

    def update(self, delta_time: float) -> None:
        """Create pending constraints and drop ones whose component is gone.

        Args:
            delta_time: Fixed timestep in seconds (unused; the constraint,
                once created, is stepped by the engine).
        """
        live_owners: set[str] = set()

        for entity in self._entity_manager.get_entities_with(Joint):
            joint = entity.get_component(Joint)
            live_owners.add(entity.id)

            if joint._joint_handle is not None:
                # Already built. Keep the mirror table in sync in case this
                # system was constructed after the joint was created.
                self._handles.setdefault(entity.id, joint._joint_handle)
                continue

            self._try_create(entity.id, joint)

        # Reconcile: a handle we still track whose owner no longer carries a
        # matching live Joint (component removed, or entity gone without an
        # EntityDestroyed we saw) must be released.
        for owner_id in list(self._handles):
            if owner_id in live_owners:
                owner = self._entity_manager.get_entity(owner_id)
                if (
                    owner is not None
                    and owner.has_component(Joint)
                    and owner.get_component(Joint)._joint_handle
                    is self._handles[owner_id]
                ):
                    continue
            self._destroy(owner_id)

    def _try_create(self, owner_id: str, joint: Joint) -> None:
        """Build the constraint if both bodies are ready; otherwise defer.

        Args:
            owner_id: Id of the entity carrying the ``Joint``.
            joint: The joint component to realise.
        """
        if not joint.target_entity_id:
            return  # Unconfigured joint; nothing to connect to yet.

        if joint.target_entity_id == owner_id:
            logger.warning("Joint on entity %s targets itself; ignoring.", owner_id)
            return

        owner = self._entity_manager.get_entity(owner_id)
        target = self._entity_manager.get_entity(joint.target_entity_id)
        if owner is None or target is None:
            return

        body_a = self._body_of(owner)
        body_b = self._body_of(target)
        if body_a is None or body_b is None:
            return  # Bodies not created yet -- retry next tick.

        handle = self._engine.create_joint(
            body_a,
            body_b,
            joint.joint_type,
            joint.anchor_a,
            joint.anchor_b,
            joint.min_distance,
            joint.max_distance,
            joint.stiffness,
            joint.damping,
            joint.max_force,
            joint.collide_connected,
        )
        if handle is None:
            return

        joint._joint_handle = handle
        self._handles[owner_id] = handle

    @staticmethod
    def _body_of(entity: Any) -> Any | None:
        """Return the backend body handle for an entity, or None.

        Args:
            entity: The entity to inspect.

        Returns:
            The ``RigidBody._body_handle`` if present and created, else None.
        """
        if not entity.has_component(RigidBody):
            return None
        return entity.get_component(RigidBody)._body_handle

    def _destroy(self, owner_id: str) -> None:
        """Remove a tracked constraint and forget it.

        Args:
            owner_id: Owner entity id whose joint handle should be released.
        """
        handle = self._handles.pop(owner_id, None)
        if handle is not None:
            self._engine.destroy_joint(handle)

        entity = self._entity_manager.get_entity(owner_id)
        if entity is not None and entity.has_component(Joint):
            entity.get_component(Joint)._joint_handle = None

    def _on_entity_destroyed(self, event: EntityDestroyed) -> None:
        """Release any constraint that touched the destroyed entity.

        Covers both directions: the destroyed entity owning a joint, and
        other entities whose joint named the destroyed one as its target.

        Args:
            event: The destruction event; components are still readable here.
        """
        dead_id = event.entity.id

        if event.entity.has_component(Joint):
            joint = event.entity.get_component(Joint)
            handle = self._handles.pop(dead_id, joint._joint_handle)
            if handle is not None:
                self._engine.destroy_joint(handle)
            joint._joint_handle = None

        for owner_id, handle in list(self._handles.items()):
            owner = self._entity_manager.get_entity(owner_id)
            if owner is None or not owner.has_component(Joint):
                continue
            joint = owner.get_component(Joint)
            if joint.target_entity_id == dead_id:
                self._engine.destroy_joint(handle)
                self._handles.pop(owner_id, None)
                joint._joint_handle = None

    def cleanup(self) -> None:
        """Destroy every constraint this system created.

        Mirrors ``PhysicsSystem.cleanup()``; call it when tearing a scene
        down so no constraint outlives its space.
        """
        for handle in self._handles.values():
            self._engine.destroy_joint(handle)
        self._handles.clear()
