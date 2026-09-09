"""Keyboard shortcuts reference panel."""

import pygame

from pyguara.common.types import Color, Rect, Vector2
from pyguara.di.container import DIContainer
from pyguara.graphics.protocols import UIRenderer
from pyguara.tools.base import Tool
from pyguara.tools.manager import ToolManager

# Keys a tool handles internally (not global toggles), so they never appear in
# ToolManager's shortcut map. Kept as a short static list rather than left
# undocumented.
_IN_TOOL_KEYS = [
    ("TAB", "Entity Inspector: cycle entities (when standalone)"),
    ("S", "Config Inspector: save"),
    ("Q / W / E", "Transform Gizmo: translate / rotate / scale"),
    ("ESC", "Transform Gizmo: clear selection (when standalone)"),
]


class ShortcutsPanel(Tool):
    """Lists the live tool shortcuts, read from the `ToolManager` itself.

    The toggle table is built from `ToolManager.iter_shortcuts()` at render
    time, so it cannot drift from what `SandboxApplication` actually
    registered. Falls back to just F12 if no `ToolManager` is in the
    container.
    """

    def __init__(self, container: DIContainer) -> None:
        """Initialize the shortcuts panel.

        Args:
            container: DI Container.
        """
        super().__init__("shortcuts_panel", container)
        # Centered Panel (approximate)
        self._rect = Rect(300, 180, 440, 400)
        try:
            self._manager: ToolManager | None = container.get(ToolManager)
        except Exception:  # noqa: BLE001 -- ToolManager not registered (bare tests)
            self._manager = None

    def update(self, dt: float) -> None:
        """No-op -- this panel has nothing to update per frame."""

    def _toggle_rows(self) -> list[tuple[str, str]]:
        rows = [("F12", "Toggle ALL Tools")]
        if self._manager is None:
            return rows
        for key_code, tool_name in self._manager.iter_shortcuts():
            label = pygame.key.name(key_code).upper()
            rows.append((label, tool_name.replace("_", " ").title()))
        return rows

    def render(self, renderer: UIRenderer) -> None:
        """Render the help overlay.

        Args:
            renderer: UI Renderer.
        """
        # Semi-transparent dark background
        renderer.draw_rect(self._rect, Color(10, 10, 20, 240), 0)
        renderer.draw_rect(self._rect, Color(255, 255, 255), 2)

        x = self._rect.x + 40
        y = self._rect.y + 30

        renderer.draw_text("Developer Tools", Vector2(x, y), Color(255, 255, 0), 24)
        y += 40

        for key, desc in self._toggle_rows():
            renderer.draw_text(key, Vector2(x, y), Color(100, 255, 100), 18)
            renderer.draw_text(desc, Vector2(x + 90, y), Color(255, 255, 255), 18)
            y += 28

        y += 16
        renderer.draw_text("In-tool keys", Vector2(x, y), Color(255, 255, 0), 16)
        y += 24
        for key, desc in _IN_TOOL_KEYS:
            renderer.draw_text(key, Vector2(x, y), Color(100, 200, 255), 14)
            renderer.draw_text(desc, Vector2(x + 90, y), Color(200, 200, 200), 14)
            y += 20
