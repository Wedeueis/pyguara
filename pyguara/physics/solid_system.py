"""System that carries/pushes actors for every MovingSolid, once a tick.

Belongs between whatever authors a solid's motion (a patrol script, a
tween -- anything that moves its Transform) and `PlatformerSystem`: a
character's own movement should be swept against solids at *this* tick's
positions, not last tick's, so this has to run after the solids move and
before the character does.
"""

from __future__ import annotations

from pyguara.common.components import Transform
from pyguara.ecs.manager import EntityManager
from pyguara.physics.components import CharacterBody, MovingSolid
from pyguara.physics.solid_mover import SolidMover


class SolidSystem:
    """Drives `SolidMover` over every `MovingSolid` entity, once a tick."""

    def __init__(self, entity_manager: EntityManager, solid_mover: SolidMover) -> None:
        """Store collaborators.

        Args:
            entity_manager: Source of solid and actor entities.
            solid_mover: Does the actual carrying/pushing.
        """
        self._entity_manager = entity_manager
        self._solid_mover = solid_mover

    def update(self, delta_time: float) -> None:
        """Move whatever each `MovingSolid` touched this tick.

        Args:
            delta_time: Unused; a solid's delta is read from how far its
                Transform already moved this tick, not derived from a
                velocity here.
        """
        # Riding is re-decided fresh from this tick's geometry, every tick,
        # for every solid -- never carried over as stale state from one a
        # character has since left.
        for actor in self._entity_manager.get_entities_with(CharacterBody):
            actor.get_component(CharacterBody).riding = None

        for solid in self._entity_manager.get_entities_with(MovingSolid, Transform):
            transform = solid.get_component(Transform)
            delta = transform.position - transform.previous_position
            if delta.x == 0.0 and delta.y == 0.0:
                continue
            self._solid_mover.move_solid(solid, delta)
