"""
Animation System for automatic animation updates.

This system automatically updates all Animator and AnimationStateMachine components
in the scene, eliminating the need for manual update() calls in game code.
"""

from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.animation import Animator, AnimationStateMachine


class AnimationSystem:
    """
    System that automatically updates all animation components.

    Processes all entities with Animator or AnimationStateMachine components,
    calling their update() methods each frame.

    Compatible with SystemManager's update(dt) signature.
    """

    def __init__(self, entity_manager: EntityManager) -> None:
        """Initialize the animation system.

        Args:
            entity_manager: The entity manager to query for animated entities.
        """
        self._entity_manager = entity_manager

    def update(self, dt: float) -> None:
        """
        Update all animation components.

        Args:
            dt: Delta time in seconds.
        """
        # Check for AnimationStateMachine first (higher-level)
        for entity in self._entity_manager.get_entities_with(AnimationStateMachine):
            fsm = entity.get_component(AnimationStateMachine)
            fsm.update(dt)

        # Update standalone Animators (those without AnimationStateMachine)
        for entity in self._entity_manager.get_entities_with(Animator):
            if not entity.has_component(AnimationStateMachine):
                animator = entity.get_component(Animator)
                animator.update(dt)
