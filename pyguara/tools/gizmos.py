"""Gizmo system for visual entity manipulation and debugging.

Provides visual handles for transform manipulation (position, rotation, scale)
and entity selection highlighting.
"""

import math
from enum import Enum, auto
from typing import Any, Optional

import pygame  # Only for event handling key constants

from pyguara.common.components import Transform
from pyguara.common.types import Color, Rect, Vector2
from pyguara.di.container import DIContainer
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.protocols import UIRenderer
from pyguara.tools.base import Tool


class GizmoMode(Enum):
    """Available gizmo operation modes."""

    TRANSLATE = auto()
    ROTATE = auto()
    SCALE = auto()


class GizmoColors:
    """Standard colors for gizmo rendering."""

    X_AXIS = Color(255, 80, 80)  # Red
    Y_AXIS = Color(80, 255, 80)  # Green
    ROTATION = Color(80, 80, 255)  # Blue
    SCALE = Color(255, 200, 80)  # Orange
    SELECTION = Color(255, 255, 0)  # Yellow
    HOVER = Color(255, 255, 255)  # White
    CENTER = Color(255, 255, 255)  # White


class TransformGizmo(Tool):
    """Visual handles for entity transform manipulation.

    Provides:
    - Position arrows (X/Y axes)
    - Rotation circle indicator
    - Scale handles at corners
    - Selection bounding box

    Toggle modes with Q (translate), W (rotate), E (scale).
    Click entities to select them.
    """

    def __init__(self, container: DIContainer) -> None:
        """Initialize the transform gizmo.

        Args:
            container: DI Container for resolving dependencies.
        """
        super().__init__("transform_gizmo", container)
        self._entity_manager: EntityManager = container.get(EntityManager)

        self._selected_entity: Optional[Entity] = None
        self._mode = GizmoMode.TRANSLATE

        # Gizmo visual settings
        self._arrow_length = 60
        self._arrow_head_size = 12
        self._rotation_radius = 50
        self._scale_handle_size = 8
        self._selection_padding = 4
        self._line_width = 2

    @property
    def selected_entity(self) -> Optional[Entity]:
        """Get the currently selected entity."""
        return self._selected_entity

    @selected_entity.setter
    def selected_entity(self, entity: Optional[Entity]) -> None:
        """Set the selected entity."""
        self._selected_entity = entity

    @property
    def mode(self) -> GizmoMode:
        """Get the current gizmo mode."""
        return self._mode

    @mode.setter
    def mode(self, mode: GizmoMode) -> None:
        """Set the gizmo mode."""
        self._mode = mode

    def select_at_position(self, screen_pos: Vector2) -> Optional[Entity]:
        """Select an entity at the given screen position.

        Args:
            screen_pos: Screen coordinates to check.

        Returns:
            The selected entity, or None if nothing was hit.
        """
        # Simple hit test against all entities with transforms
        for entity in self._entity_manager.get_entities_with(Transform):
            transform = entity.get_component(Transform)
            pos = transform.position

            # Simple bounding box check (assumes 32x32 default size)
            half_size = 16
            if (
                pos.x - half_size <= screen_pos.x <= pos.x + half_size
                and pos.y - half_size <= screen_pos.y <= pos.y + half_size
            ):
                self._selected_entity = entity
                return entity

        self._selected_entity = None
        return None

    def update(self, dt: float) -> None:
        """Update gizmo state.

        Args:
            dt: Delta time in seconds.
        """
        # Validate selection still exists
        if self._selected_entity is not None:
            try:
                if not self._selected_entity.has_component(Transform):
                    self._selected_entity = None
            except (KeyError, AttributeError):
                self._selected_entity = None

    def render(self, renderer: UIRenderer) -> None:
        """Render the gizmo overlays.

        Args:
            renderer: UI Renderer for drawing primitives (backend-agnostic).
        """
        if self._selected_entity is None:
            return

        try:
            transform = self._selected_entity.get_component(Transform)
        except KeyError:
            self._selected_entity = None
            return

        pos = transform.position
        center = Vector2(pos.x, pos.y)

        # Draw selection highlight
        self._draw_selection_box(renderer, transform)

        # Draw mode-specific gizmo
        if self._mode == GizmoMode.TRANSLATE:
            self._draw_translate_gizmo(renderer, center)
        elif self._mode == GizmoMode.ROTATE:
            self._draw_rotate_gizmo(renderer, center, transform.rotation)
        elif self._mode == GizmoMode.SCALE:
            self._draw_scale_gizmo(renderer, center, transform.scale)

    def _draw_selection_box(self, renderer: UIRenderer, transform: Transform) -> None:
        """Draw a selection bounding box around the entity."""
        pos = transform.position
        scale = transform.scale

        # Default size with scale applied
        half_w = 16 * scale.x + self._selection_padding
        half_h = 16 * scale.y + self._selection_padding

        rect = Rect(
            int(pos.x - half_w),
            int(pos.y - half_h),
            int(half_w * 2),
            int(half_h * 2),
        )

        renderer.draw_rect(rect, GizmoColors.SELECTION, width=1)

    def _draw_translate_gizmo(self, renderer: UIRenderer, center: Vector2) -> None:
        """Draw position manipulation arrows."""
        x, y = int(center.x), int(center.y)

        # X axis arrow (right)
        end_x = Vector2(x + self._arrow_length, y)
        renderer.draw_line(center, end_x, GizmoColors.X_AXIS, self._line_width)
        self._draw_arrow_head(
            renderer, (int(end_x.x), int(end_x.y)), 0, GizmoColors.X_AXIS
        )

        # Y axis arrow (down, since Y increases downward in screen space)
        end_y = Vector2(x, y + self._arrow_length)
        renderer.draw_line(center, end_y, GizmoColors.Y_AXIS, self._line_width)
        self._draw_arrow_head(
            renderer, (int(end_y.x), int(end_y.y)), 90, GizmoColors.Y_AXIS
        )

        # Center dot
        renderer.draw_circle(center, 4, GizmoColors.CENTER)

    def _draw_arrow_head(
        self,
        renderer: UIRenderer,
        tip: tuple[int, int],
        angle_deg: float,
        color: Color,
    ) -> None:
        """Draw an arrowhead at the given position."""
        angle = math.radians(angle_deg)
        size = self._arrow_head_size

        # Calculate the three points of the triangle
        back_angle = math.radians(150)
        p1 = tip
        p2 = (
            int(tip[0] + size * math.cos(angle + back_angle)),
            int(tip[1] + size * math.sin(angle + back_angle)),
        )
        p3 = (
            int(tip[0] + size * math.cos(angle - back_angle)),
            int(tip[1] + size * math.sin(angle - back_angle)),
        )

        renderer.draw_polygon([p1, p2, p3], color)

    def _draw_rotate_gizmo(
        self, renderer: UIRenderer, center: Vector2, rotation: float
    ) -> None:
        """Draw rotation manipulation circle."""
        # Draw rotation circle
        renderer.draw_circle(
            center, self._rotation_radius, GizmoColors.ROTATION, self._line_width
        )

        # Draw current rotation indicator
        angle_rad = math.radians(rotation)
        indicator_x = int(center.x + self._rotation_radius * math.cos(angle_rad))
        indicator_y = int(center.y + self._rotation_radius * math.sin(angle_rad))
        indicator = Vector2(indicator_x, indicator_y)

        renderer.draw_line(center, indicator, GizmoColors.ROTATION, self._line_width)
        renderer.draw_circle(indicator, 5, GizmoColors.CENTER)

        # Center dot
        renderer.draw_circle(center, 4, GizmoColors.CENTER)

    def _draw_scale_gizmo(
        self, renderer: UIRenderer, center: Vector2, scale: Vector2
    ) -> None:
        """Draw scale manipulation handles."""
        x, y = int(center.x), int(center.y)

        # Calculate corner positions based on current scale
        half_w = int(40 * scale.x)
        half_h = int(40 * scale.y)

        corners = [
            (x - half_w, y - half_h),  # Top-left
            (x + half_w, y - half_h),  # Top-right
            (x + half_w, y + half_h),  # Bottom-right
            (x - half_w, y + half_h),  # Bottom-left
        ]

        # Draw connecting lines
        for i in range(4):
            start = Vector2(corners[i][0], corners[i][1])
            end = Vector2(corners[(i + 1) % 4][0], corners[(i + 1) % 4][1])
            renderer.draw_line(start, end, GizmoColors.SCALE, 1)

        # Draw diagonal lines to center
        for corner in corners:
            renderer.draw_line(
                center, Vector2(corner[0], corner[1]), GizmoColors.SCALE, 1
            )

        # Draw handle squares at corners
        handle_size = self._scale_handle_size
        for corner in corners:
            rect = Rect(
                corner[0] - handle_size // 2,
                corner[1] - handle_size // 2,
                handle_size,
                handle_size,
            )
            renderer.draw_rect(rect, GizmoColors.SCALE)

        # Center dot
        renderer.draw_circle(center, 4, GizmoColors.CENTER)

    def process_event(self, event: Any) -> bool:
        """Process input events for gizmo interaction.

        Args:
            event: Raw pygame event.

        Returns:
            True if the event was consumed, False otherwise.
        """
        if not hasattr(event, "type"):
            return False

        # Mode switching with Q, W, E keys
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_q:
                self._mode = GizmoMode.TRANSLATE
                return True
            elif event.key == pygame.K_w:
                self._mode = GizmoMode.ROTATE
                return True
            elif event.key == pygame.K_e:
                self._mode = GizmoMode.SCALE
                return True
            elif event.key == pygame.K_ESCAPE:
                self._selected_entity = None
                return True

        # Entity selection on mouse click
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_pos = Vector2(event.pos[0], event.pos[1])
            self.select_at_position(mouse_pos)
            # Don't consume - let the click propagate

        return False
