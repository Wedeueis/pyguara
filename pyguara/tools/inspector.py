"""Entity Inspector tool for ECS debugging."""

import pygame
from typing import Optional, Any

from pyguara.di.container import DIContainer
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.protocols import UIRenderer
from pyguara.common.types import Color, Vector2, Rect
from pyguara.tools.base import Tool


class EntityInspector(Tool):
    """Visualizes ECS entities and their components data.

    Allows cycling through active entities and inspecting their component states
    in real-time.
    """

    def __init__(self, container: DIContainer) -> None:
        """Initialize the inspector.

        Args:
            container: The global DI container.
        """
        super().__init__("entity_inspector", container)
        self._entity_manager: EntityManager = container.get(EntityManager)
        self._selected_index: int = 0
        self._selected_entity: Optional[Entity] = None

        # UI Layout
        self._panel_rect = Rect(10, 80, 300, 500)
        self._bg_color = Color(30, 30, 40, 230)
        self._text_color = Color(255, 255, 255)
        self._highlight_color = Color(100, 200, 255)

    def update(self, dt: float) -> None:
        """Update the entity list snapshot.

        Args:
            dt: Delta time.
        """
        # In a real engine, we might throttle this to save CPU
        pass

    def render(self, renderer: UIRenderer) -> None:
        """Render the inspector panel.

        Args:
            renderer: The UI renderer backend.
        """
        # Draw Background
        renderer.draw_rect(self._panel_rect, self._bg_color, 0)
        renderer.draw_rect(self._panel_rect, Color(100, 100, 100), 2)

        # Header
        renderer.draw_text(
            "Entity Inspector (TAB to Cycle)",
            Vector2(self._panel_rect.x + 10, self._panel_rect.y + 10),
            self._highlight_color,
            size=18,
        )

        # Get Entities (Privileged access for debugging)
        # Assuming EntityManager has an underlying dictionary or list
        if hasattr(self._entity_manager, "_entities"):
            entities = list(self._entity_manager._entities.values())
        else:
            return

        if not entities:
            renderer.draw_text(
                "No Entities Active",
                Vector2(self._panel_rect.x + 10, self._panel_rect.y + 40),
                Color(150, 150, 150),
                16,
            )
            return

        # Validate selection
        if self._selected_index >= len(entities):
            self._selected_index = 0
        self._selected_entity = entities[self._selected_index]

        # Draw Entity Info
        y_offset = 40
        self._render_entity_details(renderer, self._selected_entity, y_offset)

        # Footer
        footer_y = self._panel_rect.y + self._panel_rect.height - 30
        renderer.draw_text(
            f"Entity {self._selected_index + 1}/{len(entities)}",
            Vector2(self._panel_rect.x + 10, footer_y),
            Color(150, 150, 150),
            14,
        )

    def _render_entity_details(
        self, renderer: UIRenderer, entity: Entity, start_y: int
    ) -> None:
        """Render components of the selected entity.

        Args:
            renderer: UI Backend.
            entity: The entity to inspect.
            start_y: Local Y offset within panel.
        """
        x = self._panel_rect.x + 10
        y = self._panel_rect.y + start_y

        # Entity ID/Tag
        renderer.draw_text(f"ID: {entity.id}", Vector2(x, y), self._text_color, 16)
        y += 20
        tag_str = entity.tag if entity.tag else "[No Tag]"
        renderer.draw_text(f"Tag: {tag_str}", Vector2(x, y), self._text_color, 16)
        y += 30

        # Separator
        renderer.draw_line(
            Vector2(x, y),
            Vector2(x + self._panel_rect.width - 20, y),
            Color(100, 100, 100),
            1,
        )
        y += 10

        # Components
        for comp_type, component in entity.components.items():
            comp_name = comp_type.__name__
            renderer.draw_text(
                f"[{comp_name}]", Vector2(x, y), self._highlight_color, 16
            )
            y += 20

            # Inspect Component Data (Primitives only for brevity)
            for attr, value in component.__dict__.items():
                if attr.startswith("_"):
                    continue

                # Format value string
                val_str = str(value)
                if isinstance(value, float):
                    val_str = f"{value:.2f}"

                renderer.draw_text(
                    f"  {attr}: {val_str}", Vector2(x, y), self._text_color, 14
                )
                y += 16

            y += 10  # Spacing between components

    def process_event(self, event: Any) -> bool:
        """Handle cycling selection.

        Args:
            event: Pygame event.
        """
        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            # Cycle next
            if hasattr(self._entity_manager, "_entities"):
                count = len(self._entity_manager._entities)
                if count > 0:
                    self._selected_index = (self._selected_index + 1) % count
                    return True
        return False
