"""Physics and spatial debugger tool."""

import pygame

from pyguara.di.container import DIContainer
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.protocols import UIRenderer
from pyguara.common.components import Transform
from pyguara.physics.components import Collider
from pyguara.common.types import Color
from pyguara.tools.base import Tool


class PhysicsDebugger(Tool):
    """Visualizes physics boundaries and colliders overlay."""

    def __init__(self, container: DIContainer) -> None:
        """Initialize the debugger.

        Args:
            container: DI Container.
        """
        super().__init__("physics_debugger", container)
        self._entity_manager: EntityManager = container.get(EntityManager)
        self._collider_color = Color(0, 255, 0)
        self._trigger_color = Color(255, 255, 0)

    def update(self, dt: float) -> None:
        """No update logic needed for pure visualization."""
        pass

    def render(self, renderer: UIRenderer) -> None:
        """Draw wireframes over entities with colliders.

        Args:
            renderer: UI Renderer.
        """
        # We need access to the raw surface to draw lines/shapes easily
        # Assuming renderer exposes a surface or primitive methods
        if not hasattr(renderer, "_surface"):
            return

        surface = renderer._surface

        entities = self._entity_manager.get_entities_with(Transform, Collider)

        for entity in entities:
            transform = entity.get_component(Transform)
            collider = entity.get_component(Collider)

            pos = transform.position
            dims = collider.dimensions

            color = (
                self._trigger_color
                if getattr(collider, "is_trigger", False)
                else self._collider_color
            )

            # Draw based on shape type (Simplified logic)
            if len(dims) == 2:  # Box
                rect = pygame.Rect(
                    int(pos.x - dims[0] / 2),
                    int(pos.y - dims[1] / 2),
                    int(dims[0]),
                    int(dims[1]),
                )
                pygame.draw.rect(surface, (color.r, color.g, color.b), rect, 1)

            elif len(dims) == 1:  # Circle
                pygame.draw.circle(
                    surface,
                    (color.r, color.g, color.b),
                    (int(pos.x), int(pos.y)),
                    int(dims[0]),
                    1,
                )

            # Draw Center Point
            pygame.draw.circle(surface, (255, 0, 0), (int(pos.x), int(pos.y)), 2)
