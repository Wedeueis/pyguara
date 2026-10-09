"""The scene viewport: the rendered frame, with editing on top of it.

`panel` is the ImGui panel -- pan, zoom, grid, selection, marquee -- shown
over the render graph's own framebuffer, so what the viewport shows is by
construction what the game shows.

`picking` is the geometry underneath it, deliberately free of GL, ImGui
and any window, so it can be tested against a real world directly.
"""

from pyguara.studio.viewport.gizmo import Axis, GizmoMode, TransformGizmo
from pyguara.studio.viewport.panel import (
    MAX_ZOOM,
    MIN_ZOOM,
    ViewportOverlay,
    ViewportPanel,
    ViewportState,
)
from pyguara.studio.viewport.picking import (
    Pick,
    fallback_bounds,
    iter_pickable,
    marquee_rect,
    pick_at,
    pick_in_region,
    screen_to_world,
    sprite_bounds,
    world_to_panel,
)

__all__ = [
    "MAX_ZOOM",
    "MIN_ZOOM",
    "Axis",
    "GizmoMode",
    "Pick",
    "TransformGizmo",
    "ViewportOverlay",
    "ViewportPanel",
    "ViewportState",
    "fallback_bounds",
    "iter_pickable",
    "marquee_rect",
    "pick_at",
    "pick_in_region",
    "screen_to_world",
    "sprite_bounds",
    "world_to_panel",
]
