"""System picking each character's clip from the way it is moving.

The hand-written version of this appears in every top-down game, which is
why it is here. It does three things, and the second and third are the
ones that are easy to get wrong:

1. Derive a facing from the character's velocity.
2. Leave the facing alone when the velocity is zero, so a character that
   has stopped keeps facing where it last faced instead of snapping to a
   default.
3. Ask for the clip every frame, relying on `play_clip()` ignoring a
   re-request for the clip already playing -- so walking in a straight
   line does not restart the walk cycle sixty times a second.
"""

from __future__ import annotations

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.animation import Animator, play_clip
from pyguara.kits.topdown_movement.body import TopDownBody
from pyguara.kits.topdown_movement.facing import (
    DirectionalAnimator,
    facing_from_vector,
)


class DirectionalAnimationSystem:
    """Keeps each `DirectionalAnimator` pointing where its body is going.

    Reads velocity from `TopDownBody` when the entity has one, because that
    is the kit's own mover; otherwise from the distance the `Transform`
    moved since the last tick, so a character driven by a tween, a
    pathfinder or a script still faces the right way.

    An entity with a `DirectionalAnimator` and no `Animator` is skipped
    rather than treated as an error: a game may well attach the facing to
    something it draws itself.
    """

    def __init__(self, entity_manager: EntityManager) -> None:
        """Initialise the system.

        Args:
            entity_manager: The scene's entity manager.
        """
        self._entity_manager = entity_manager
        self._last_positions: dict[str, tuple[float, float]] = {}

    def update(self, dt: float) -> None:
        """Update every directional animator's facing and clip.

        Args:
            dt: Seconds since the last call. Unused -- a facing is derived
                from direction, which a delta does not change -- and kept
                for the `SystemManager` signature.
        """
        for entity in self._entity_manager.get_entities_with(DirectionalAnimator):
            directional = entity.get_component(DirectionalAnimator)
            velocity = self._velocity_of(entity)

            facing = facing_from_vector(velocity, directional.clips.ways)
            if facing is not None:
                directional.facing = facing

            if entity.has_component(Animator):
                play_clip(
                    entity.get_component(Animator),
                    directional.clips.clip_name(directional.action, directional.facing),
                )

    def _velocity_of(self, entity: Entity) -> Vector2:
        """Return the direction an entity is moving in.

        Args:
            entity: The entity to measure.

        Returns:
            The body's velocity, or the per-tick `Transform` delta for an
            entity without one -- so a character driven by a tween, a
            pathfinder or a script still faces where it is going.
        """
        if entity.has_component(TopDownBody):
            body = entity.get_component(TopDownBody)
            return body.velocity

        if not entity.has_component(Transform):
            return Vector2(0, 0)

        transform = entity.get_component(Transform)
        current = (float(transform.position.x), float(transform.position.y))
        previous = self._last_positions.get(entity.id)
        self._last_positions[entity.id] = current
        if previous is None:
            return Vector2(0, 0)
        return Vector2(current[0] - previous[0], current[1] - previous[1])
