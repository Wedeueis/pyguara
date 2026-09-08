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
from pyguara.physics.platformer_controller import PlatformerController
from pyguara.physics.types import BodyType, ShapeType

STATIC = Color(80, 220, 120)
DYNAMIC = Color(80, 200, 255)
KINEMATIC = Color(255, 180, 60)
SENSOR = Color(240, 230, 90)
ONE_WAY = Color(230, 120, 240)
GROUNDED = Color(120, 255, 120)
AIRBORNE = Color(255, 110, 110)


class ColliderDebugRenderer:
    """Draws collider outlines, and the rays the platformer casts.

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
        """Draw every collider, and each platformer's ground and wall rays.

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

        for entity in self._entity_manager.get_entities_with(
            Transform, Collider, PlatformerController
        ):
            self._draw_probe_rays(renderer, entity, offset)

    def _draw_probe_rays(
        self, renderer: IRenderer, entity: object, offset: Vector2
    ) -> None:
        """Draw the wall probes, and a marker at the ground probe's pixel.

        Ground detection is a one-pixel overlap test now (Celeste's model),
        not a variable-length ray, so there is no length to draw -- the
        marker sits exactly on the pixel `CharacterMover.probe()` checks.
        Colour is where a grounding bug shows itself: green while the
        character floats reads as a false positive just as clearly as a
        ray drawn too long used to.
        """
        transform = entity.get_component(Transform)  # type: ignore[attr-defined]
        collider = entity.get_component(Collider)  # type: ignore[attr-defined]
        controller = entity.get_component(PlatformerController)  # type: ignore[attr-defined]

        half_height = collider.dimensions[1] / 2
        half_width = collider.dimensions[0] / 2
        position = transform.position - offset

        colour = GROUNDED if controller.is_grounded else AIRBORNE
        foot = position + Vector2(0, half_height)
        renderer.draw_line(foot + Vector2(-4, 1), foot + Vector2(4, 1), colour, width=2)

        for direction in (-1.0, 1.0):
            side_start = position + Vector2(direction * (half_width + 2), -10)
            renderer.draw_line(
                side_start,
                side_start + Vector2(direction * controller.wall_check_distance, 0),
                KINEMATIC,
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
