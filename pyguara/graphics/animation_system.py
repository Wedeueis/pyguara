"""
Animation System for automatic animation updates.

This system automatically updates all Animator and AnimationStateMachine components
in the scene, eliminating the need for manual update() calls in game code.
"""

from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.components.animation import AnimationStateMachine, Animator
from pyguara.graphics.events import AnimationFrameEvent


class AnimationSystem:
    """
    System that automatically updates all animation components.

    Processes all entities with Animator or AnimationStateMachine components,
    calling their update() methods each frame.

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

    def update(self, dt: float) -> None:
        """
        Update all animation components.

        Args:
            dt: Delta time in seconds.
        """
        # Check for AnimationStateMachine first (higher-level)
        for entity in self._entity_manager.get_entities_with(AnimationStateMachine):
            fsm = entity.get_component(AnimationStateMachine)
            for name in fsm.update(dt):
                self._dispatch_frame_event(entity.id, fsm.current_state_name, name)

        # Update standalone Animators (those without AnimationStateMachine)
        for entity in self._entity_manager.get_entities_with(Animator):
            if not entity.has_component(AnimationStateMachine):
                animator = entity.get_component(Animator)
                for name in animator.update(dt):
                    self._dispatch_frame_event(
                        entity.id, animator.current_clip_name, name
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
