"""The editor panel contract.

A panel is a pure function of the world plus the editor's selection: it
reads `PanelContext` and issues ImGui calls. It owns no GL resources and
holds no reference to the scene between frames, which is what makes a panel
testable headlessly -- `imgui.create_context()` needs no GL, so a test can
run `new_frame()`, call `draw()`, and assert on what the panel did to the
selection without a window anywhere.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pyguara.ecs.manager import EntityManager
from pyguara.editor.selection import Selection
from pyguara.log import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PanelContext:
    """Everything a panel is allowed to read, rebuilt each frame.

    Attributes:
        entity_manager: The active scene's world, or None when no scene is
            active yet. Panels must render something sensible for None
            rather than assume a world: between `run()` and the first
            scene switch there genuinely is no world, and the previous
            editor's habit of substituting an empty throwaway one made
            "no scene" indistinguishable from "empty scene".
        selection: The shared selection, which panels may read *and* set.
    """

    entity_manager: EntityManager | None
    selection: Selection


class EditorPanel(ABC):
    """A dockable ImGui panel over live engine state."""

    def __init__(self, title: str, *, visible: bool = True) -> None:
        """Initialize the panel.

        Args:
            title: The window title, also its identity in the layer.
            visible: Whether it draws from the first frame.
        """
        self._title = title
        self._visible = visible
        # Set by the layer when the panel is added. None while the panel
        # stands alone, which is how the tests drive it.
        self.toasts: Any = None

    def report(self, message: str, *, level: str = "error") -> None:
        """Say something to the person at the keyboard.

        A panel that refuses an edit has to say so *on screen*. A log line
        is not a report: the person sees the control accept a value and
        nothing happen, which is indistinguishable from a control that
        does not work -- and is how it was reported.

        Args:
            message: What to say.
            level: "info", "warning" or "error".
        """
        if self.toasts is None:
            logger.info(f"{self.title}: {message}")
            return
        from pyguara.editor.toasts import Level

        self.toasts.push(message, Level(level))

    @property
    def title(self) -> str:
        """The panel's window title."""
        return self._title

    @property
    def visible(self) -> bool:
        """Whether this panel draws."""
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        """Show or hide the panel."""
        self._visible = value

    def toggle(self) -> None:
        """Flip visibility."""
        self._visible = not self._visible

    @abstractmethod
    def draw(self, context: PanelContext) -> None:
        """Issue this panel's ImGui calls for one frame.

        Called between `imgui.new_frame()` and `imgui.render()`, and only
        when `visible`.

        Args:
            context: The world and selection to read.
        """
        ...
