"""
Animation System for automatic animation updates.

This system automatically updates all Animator and AnimationStateMachine components
in the scene, eliminating the need for manual update() calls in game code.
"""

from typing import List
from pyguara.ecs.entity import Entity
from pyguara.graphics.components.animation import Animator, AnimationStateMachine


class AnimationSystem:
    """
    System that automatically updates all animation components.

    Processes all entities with Animator or AnimationStateMachine components,
    calling their update() methods each frame.
    """

    def update(self, entities: List[Entity], dt: float) -> None:
        """
        Update all animation components.

        Args:
            entities (List[Entity]): Entities to process.
            dt (float): Delta time in seconds.
        """
        for entity in entities:
            # Check for AnimationStateMachine first (higher-level)
            if entity.has_component(AnimationStateMachine):
                fsm = entity.get_component(AnimationStateMachine)
                fsm.update(dt)
            # Otherwise check for standalone Animator
            elif entity.has_component(Animator):
                animator = entity.get_component(Animator)
                animator.update(dt)
