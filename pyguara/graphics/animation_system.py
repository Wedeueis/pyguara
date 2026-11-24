"""Animation System for automatic animation updates.

This system automatically updates all Animator and AnimationStateMachine components
in the scene, eliminating the need for manual update() calls in game code.
"""

from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.components.animation import (
    AnimationStateMachine,
    Animator,
    advance_animators,
    advance_state_machine,
)
from pyguara.graphics.events import AnimationFrameEvent


class AnimationSystem:
    """System that automatically updates all animation components.

    Processes all entities with Animator or AnimationStateMachine components,
    advancing each one every frame. Both components are pure data; the
    advancing is `advance_state_machine` / `advance_animator`, the free
    functions that live beside them.

    Compatible with SystemManager's update(dt) signature.
    """

    def __init__(
        self, entity_manager: EntityManager, dispatcher: EventDispatcher
    ) -> None:
        """Initialize the animation system.

        Args:
            entity_manager: The entity manager to query for animated entities.
            dispatcher: Where `AnimationFrameEvent` is dispatched for every
                frame-event name a clip fires this update.
        """
        self._entity_manager = entity_manager
        self._dispatcher = dispatcher
        # Both run every frame, so both are worth the cache's bookkeeping.
        entity_manager.register_cached_query(Animator)
        entity_manager.register_cached_query(AnimationStateMachine)

    def update(self, dt: float) -> None:
        """Update all animation components.

        Args:
            dt: Delta time in seconds.
        """
        manager = self._entity_manager

        # State machines first: each advances its own animator.
        driven: set[str] = set()
        for entity in manager.get_entities_with_cached(AnimationStateMachine):
            driven.add(entity.id)
            fsm = entity.get_component(AnimationStateMachine)
            for name in advance_state_machine(fsm, dt):
                self._dispatch_frame_event(entity.id, fsm.current_state_name, name)

        # Then every animator no state machine drives, in one pass.
        animators = (
            entity.get_component(Animator)
            for entity in manager.get_entities_with_cached(Animator)
            if entity.id not in driven
        )
        for animator, names in advance_animators(animators, dt):
            # It came out of an entity's components, so it is attached.
            assert animator.entity is not None
            for name in names:
                self._dispatch_frame_event(
                    animator.entity.id, animator.current_clip_name, name
                )

    def _dispatch_frame_event(
        self, entity_id: str, clip_name: str | None, name: str
    ) -> None:
        self._dispatcher.dispatch(
            AnimationFrameEvent(
                entity_id=entity_id,
                clip_name=clip_name or "",
                name=name,
            )
        )
