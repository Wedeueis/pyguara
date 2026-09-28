"""Draw physics colliders on top of the world, to see what the solver sees.

A sprite and the collider under it are separate pieces of data that nothing
forces to agree. When they disagree, the symptom is visual -- a character
that looks like it is standing inside the floor, or floating above it -- and
no amount of reading component values tells you which of the two is wrong.
This draws the colliders so the two can be compared directly.

It draws outlines only, through `IRenderer`, so it works on any backend and
needs no debug support from one.
"""

from __future__ import annotations

from pyguara.common.components import Transform
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.protocols import IRenderer
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.types import BodyType, ShapeType

STATIC = Color(80, 220, 120)
DYNAMIC = Color(80, 200, 255)
KINEMATIC = Color(255, 180, 60)
SENSOR = Color(240, 230, 90)
ONE_WAY = Color(230, 120, 240)
GROUNDED = Color(120, 255, 120)
AIRBORNE = Color(255, 110, 110)


class ColliderDebugRenderer:
    """Draws collider outlines for every entity that has one.

    Genre-agnostic, and deliberately so: this used to also draw a
    platformer's ground and wall probes, which meant core importing
    `PlatformerController`. That component now lives in
    `kits.platformer_movement`, and core never imports a kit (see
    `pyguara.kits`). The probe drawing moved with it, to
    `PlatformerProbeDebugRenderer` -- compose the two when debugging a
    platformer.

    Attributes:
        entity_manager: Source of entities to draw.
    """

    def __init__(self, entity_manager: EntityManager) -> None:
        """Store the entity source.

        Args:
            entity_manager: The manager to query each frame.
        """
        self._entity_manager = entity_manager

    def render(self, renderer: IRenderer, camera_offset: Vector2 | None = None) -> None:
        """Draw an outline for every collider.

        Args:
            renderer: Target renderer; only primitive draws are used.
            camera_offset: World-to-screen offset to subtract, matching
                whatever the scene applies to its own sprites.
        """
        offset = camera_offset if camera_offset is not None else Vector2.zero()

        for entity in self._entity_manager.get_entities_with(Transform, Collider):
            transform = entity.get_component(Transform)
            collider = entity.get_component(Collider)
            position = transform.position - offset
            colour = self._colour(entity, collider)

            if collider.shape_type == ShapeType.CIRCLE:
                renderer.draw_circle(
                    position + collider.offset, collider.dimensions[0], colour, width=1
                )
            else:
                width, height = collider.dimensions[0], collider.dimensions[1]
                centre = position + collider.offset
                renderer.draw_rect(
                    Rect(
                        int(centre.x - width / 2),
                        int(centre.y - height / 2),
                        int(width),
                        int(height),
                    ),
                    colour,
                    width=1,
                )

    @staticmethod
    def _colour(entity: object, collider: Collider) -> Color:
        """Pick a colour conveying what kind of collider this is."""
        if collider.is_sensor:
            return SENSOR
        if collider.one_way:
            return ONE_WAY
        if entity.has_component(RigidBody):  # type: ignore[attr-defined]
            body_type = entity.get_component(RigidBody).body_type  # type: ignore[attr-defined]
            if body_type == BodyType.DYNAMIC:
                return DYNAMIC
            if body_type == BodyType.KINEMATIC:
                return KINEMATIC
        return STATIC
