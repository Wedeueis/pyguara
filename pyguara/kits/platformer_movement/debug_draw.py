"""Debug drawing for the platformer's ground and wall probes.

Split from `pyguara.physics.debug_draw.ColliderDebugRenderer`, which drew
these alongside collider outlines and had to import `PlatformerController`
to do it. Core never imports a kit (see `pyguara.kits`), so the probe
drawing follows the component it reads.

Compose the two when debugging a platformer:

```python
self._debug = [
    ColliderDebugRenderer(self.entity_manager),
    PlatformerProbeDebugRenderer(self.entity_manager),
]
...
for drawer in self._debug:
    drawer.render(renderer, camera_offset)
```
"""

from __future__ import annotations

from pyguara.common.components import Transform
from pyguara.common.types import Color, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.protocols import IRenderer
from pyguara.kits.platformer_movement.controller import PlatformerController
from pyguara.physics.components import Collider

# Kept in step with `physics/debug_draw.py`'s palette rather than imported
# from it: these three are what this drawer needs, and importing the core
# module for its constants would tie a kit's look to a core module's
# private-ish colour table.
GROUNDED = Color(120, 255, 120)
AIRBORNE = Color(255, 110, 110)
WALL_PROBE = Color(255, 180, 60)


class PlatformerProbeDebugRenderer:
    """Draws each platformer's ground marker and wall probes.

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
        """Draw the probes for every entity with a `PlatformerController`.

        Args:
            renderer: Target renderer; only primitive draws are used.
            camera_offset: World-to-screen offset to subtract, matching
                whatever the scene applies to its own sprites.
        """
        offset = camera_offset if camera_offset is not None else Vector2.zero()

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
                WALL_PROBE,
                width=1,
            )
