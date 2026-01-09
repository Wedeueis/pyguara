"""Keyboard shortcuts reference panel."""

from pyguara.di.container import DIContainer
from pyguara.graphics.protocols import UIRenderer
from pyguara.common.types import Color, Vector2, Rect
from pyguara.tools.base import Tool


class ShortcutsPanel(Tool):
    """Displays a list of available tool shortcuts."""

    def __init__(self, container: DIContainer) -> None:
        """Initialize the shortcuts panel.

        Args:
            container: DI Container.
        """
        super().__init__("shortcuts_panel", container)
        # Centered Panel (approximate)
        self._rect = Rect(300, 200, 400, 300)

        self._shortcuts = [
            ("F1", "Performance Monitor"),
            ("F2", "Entity Inspector"),
            ("F3", "Event Monitor"),
            ("F4", "Physics Debugger"),
            ("F5", "Robust ImGui Editor"),
            ("F8", "Shortcuts Panel (This)"),
            ("F12", "Toggle ALL Tools"),
        ]

    def update(self, dt: float) -> None:
        pass

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

        for key, desc in self._shortcuts:
            # Key Column
            renderer.draw_text(key, Vector2(x, y), Color(100, 255, 100), 18)
            # Desc Column
            renderer.draw_text(desc, Vector2(x + 80, y), Color(255, 255, 255), 18)
            y += 30

        y += 20
        renderer.draw_text("Press F8 to Close", Vector2(x, y), Color(150, 150, 150), 16)
