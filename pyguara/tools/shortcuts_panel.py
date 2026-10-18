"""Keyboard shortcuts reference panel."""

from pyguara.common.types import Color, Rect, Vector2
from pyguara.di.container import DIContainer
from pyguara.graphics.protocols import UIRenderer
from pyguara.input.keys import key_name
from pyguara.tools.base import Tool
from pyguara.tools.manager import ToolManager

# There is deliberately no "in-tool keys" section any more. It listed four
# bindings -- the inspector's TAB, the config editor's S, the gizmo's
# Q/W/E and ESC -- and all four belonged to tools that are now Studio's.
# No overlay tool handles a key of its own today, so the section would be
# an empty heading, and a heading that is sometimes empty is how a stale
# one goes unnoticed. If a tool grows an internal key, it should say so
# itself rather than through a list here that nothing checks: that list
# was hand-maintained precisely because `ToolManager` cannot see those
# keys, which is also why it could drift.


class ShortcutsPanel(Tool):
    """Lists the live tool shortcuts, read from the `ToolManager` itself.

    The toggle table is built from `ToolManager.iter_shortcuts()` at render
    time, so it cannot drift from what `SandboxApplication` actually
    registered -- which is the only reason this panel survived the overlay
    losing five of its tools without needing an edit. Falls back to just
    F12 if no `ToolManager` is in the container.

    One line is hard-coded, and deliberately: that authoring lives in
    PyGuara Studio. Someone reaching for F2 or F9 out of habit opens this
    panel next, and an overlay that simply no longer lists them leaves
    them looking for a key that was removed rather than moved.
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
            label = key_name(key_code).upper()
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
        renderer.draw_text(
            "Authoring is PyGuara Studio (ModernGL)",
            Vector2(x, y),
            Color(160, 160, 170),
            14,
        )
