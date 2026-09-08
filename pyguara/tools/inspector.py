"""Entity Inspector tool for ECS debugging."""

from typing import Any

import pygame

from pyguara.common.components import Tag
from pyguara.common.types import Color, Rect, Vector2
from pyguara.di.container import DIContainer
from pyguara.ecs.entity import Entity
from pyguara.graphics.protocols import UIRenderer
from pyguara.tools.base import Tool
from pyguara.tools.tweakable import (
    TweakableLeaf,
    apply_click,
    collect_tweakable_leaves,
    render_tweakable_leaves,
)


class EntityInspector(Tool):
    """Visualizes ECS entities and their components data.

    Allows cycling through active entities and inspecting their component
    states in real-time. Editable-typed fields (bool/int/float/Enum/Vector2,
    or a nested dataclass of those) are click-to-edit, writing straight back
    onto the live component -- see `pyguara.tools.tweakable`.
    """

    def __init__(self, container: DIContainer) -> None:
        """Initialize the inspector.

        Args:
            container: The global DI container.
        """
        super().__init__("entity_inspector", container)
        self._selected_index: int = 0
        self._selected_entity: Entity | None = None

        # UI Layout
        self._panel_rect = Rect(10, 80, 300, 500)
        self._bg_color = Color(30, 30, 40, 230)
        self._text_color = Color(255, 255, 255)
        self._highlight_color = Color(100, 200, 255)

        # This frame's clickable field rows, recomputed every render() and
        # hit-tested against in process_event().
        self._tweakable_rows: list[tuple[Rect, TweakableLeaf]] = []

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
        self._tweakable_rows = []

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

        entities = list(self._entity_manager.get_all_entities())

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
        tag_str = entity.tag.name if entity.has_component(Tag) else "[No Tag]"
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

        for component in entity.get_all_components():
            comp_name = type(component).__name__
            renderer.draw_text(
                f"[{comp_name}]", Vector2(x, y), self._highlight_color, 16
            )
            y += 20

            # Inspect and, for editable-typed fields, edit component data.
            leaves = collect_tweakable_leaves(component)
            rows = render_tweakable_leaves(
                renderer,
                leaves,
                x=x + 10,
                y=y,
                row_width=self._panel_rect.width - 20,
                row_height=16,
                text_color=self._text_color,
                font_size=14,
            )
            self._tweakable_rows.extend(rows)
            y += len(leaves) * 16

            y += 10  # Spacing between components

    def process_event(self, event: Any) -> bool:
        """Handle cycling selection and clicks on editable field rows.

        Args:
            event: Pygame event.
        """
        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            # Cycle next
            count = sum(1 for _ in self._entity_manager.get_all_entities())
            if count > 0:
                self._selected_index = (self._selected_index + 1) % count
                return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            for rect, leaf in self._tweakable_rows:
                if (
                    rect.x <= mx <= rect.x + rect.width
                    and rect.y <= my <= rect.y + rect.height
                ):
                    apply_click(leaf, local_x=mx - rect.x, row_width=rect.width)
                    return True

        return False
