"""Hierarchy panel: lists the active scene's entities and tracks a selection."""

from typing import Any

import pygame

from pyguara.common.components import Tag
from pyguara.common.types import Color, Rect, Vector2
from pyguara.di.container import DIContainer
from pyguara.ecs.entity import Entity
from pyguara.graphics.protocols import UIRenderer
from pyguara.tools.base import Tool

_ROW_HEIGHT = 18


class HierarchyTool(Tool):
    """Lists every entity in the current scene; click a row to select it.

    The selection is published as `selected_entity` for other tools to read.
    `EntityInspector` takes its subject from here when constructed with a
    selection provider (see `SandboxApplication`), so the two together behave
    like the hierarchy + inspector split of an editor. Replaces the ImGui
    `HierarchyPanel` that never executed.
    """

    def __init__(self, container: DIContainer) -> None:
        """Initialize the hierarchy panel.

        Args:
            container: The global DI container.
        """
        super().__init__("hierarchy", container)
        self.selected_entity: Entity | None = None

        self._panel_rect = Rect(10, 80, 260, 400)
        self._bg_color = Color(30, 30, 40, 230)
        self._text_color = Color(220, 220, 220)
        self._highlight_color = Color(100, 200, 255)

        # This frame's clickable rows: (row rect, entity id). Rebuilt every
        # render(), hit-tested in process_event().
        self._rows: list[tuple[Rect, str]] = []

    def update(self, dt: float) -> None:
        """Drop the selection if its entity has left the scene.

        Args:
            dt: Delta time.
        """
        if (
            self.selected_entity is not None
            and self._entity_manager.get_entity(self.selected_entity.id) is None
        ):
            self.selected_entity = None

    def render(self, renderer: UIRenderer) -> None:
        """Render the entity list.

        Args:
            renderer: The UI renderer backend.
        """
        self._rows = []

        renderer.draw_rect(self._panel_rect, self._bg_color, 0)
        renderer.draw_rect(self._panel_rect, Color(100, 100, 100), 2)

        x = self._panel_rect.x + 10
        y = self._panel_rect.y + 10
        renderer.draw_text("Hierarchy", Vector2(x, y), self._highlight_color, 18)
        y += 28

        entities = list(self._entity_manager.get_all_entities())
        if not entities:
            renderer.draw_text("No entities", Vector2(x, y), Color(150, 150, 150), 14)
            return

        selected_id = self.selected_entity.id if self.selected_entity else None
        max_y = self._panel_rect.y + self._panel_rect.height - _ROW_HEIGHT
        for entity in entities:
            if y > max_y:
                break
            is_selected = entity.id == selected_id
            color = self._highlight_color if is_selected else self._text_color
            renderer.draw_text(self._label_for(entity), Vector2(x, y), color, 14)
            self._rows.append(
                (
                    Rect(self._panel_rect.x, y, self._panel_rect.width, _ROW_HEIGHT),
                    entity.id,
                )
            )
            y += _ROW_HEIGHT

    @staticmethod
    def _label_for(entity: Entity) -> str:
        short = entity.id[:8]
        if entity.has_component(Tag):
            return f"{entity.get_component(Tag).name} ({short})"
        return short

    def process_event(self, event: Any) -> bool:
        """Select the entity whose row was clicked.

        Args:
            event: Pygame event.
        """
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            for rect, entity_id in self._rows:
                if (
                    rect.x <= mx <= rect.x + rect.width
                    and rect.y <= my <= rect.y + rect.height
                ):
                    self.selected_entity = self._entity_manager.get_entity(entity_id)
                    return True
        return False
