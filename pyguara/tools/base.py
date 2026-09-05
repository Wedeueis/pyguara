"""Base abstractions for the developer tool system."""

from abc import ABC, abstractmethod
from typing import Any

from pyguara.di.container import DIContainer
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.protocols import UIRenderer


class Tool(ABC):
    """Abstract base class for all developer tools.

    Provides lifecycle management and access to the engine's service container.
    """

    def __init__(self, name: str, container: DIContainer) -> None:
        """Initialize the tool.

        Args:
            name: The unique identifier for this tool.
            container: The global dependency injection container.
        """
        self.name = name
        self._container = container
        self._is_visible: bool = True
        self._is_active: bool = True

    @property
    def _entity_manager(self) -> EntityManager:
        """The active scene's EntityManager.

        There's no global EntityManager to resolve from the container -- each
        scene owns its own world (see Scene-owned world and SystemManager).
        Fetched fresh on every access (not cached at construction time, which
        runs before any scene is registered/active) so tools always see
        whichever scene is currently on top, same as `editor/layer.py`'s
        `scene_manager.current_scene.entity_manager` pattern. Falls back to a
        throwaway empty manager if no scene is active yet (e.g. a tool
        rendering during the brief window before the first scene switch).
        """
        from pyguara.scene.manager import SceneManager

        current_scene = self._container.get(SceneManager).current_scene
        if current_scene is not None:
            return current_scene.entity_manager
        return EntityManager()

    @property
    def is_visible(self) -> bool:
        """Return True if the tool should render."""
        return self._is_visible

    @property
    def is_active(self) -> bool:
        """Return True if the tool should update and process events."""
        return self._is_active

    def show(self) -> None:
        """Make the tool visible."""
        self._is_visible = True

    def hide(self) -> None:
        """Make the tool invisible."""
        self._is_visible = False

    def toggle(self) -> None:
        """Toggle the visibility state."""
        self._is_visible = not self._is_visible

    @abstractmethod
    def update(self, dt: float) -> None:
        """Update tool logic.

        Args:
            dt: Delta time in seconds.
        """
        ...

    @abstractmethod
    def render(self, renderer: UIRenderer) -> None:
        """Render the tool's interface.

        Args:
            renderer: The UI renderer backend.
        """
        ...

    def process_event(self, event: Any) -> bool:
        """Process a raw input event.

        Override this to intercept inputs (e.g., stopping a click from
        reaching the game world).

        Args:
            event: The raw event (e.g., pygame.event.Event).

        Returns:
            True if the event was consumed by the tool, False otherwise.
        """
        return False
