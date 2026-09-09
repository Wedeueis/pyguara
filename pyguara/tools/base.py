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
        # Reused across accesses during the no-scene window (see below) so a
        # tool that reads the world twice in one frame sees one manager, not
        # two fresh empties.
        self._fallback_entity_manager: EntityManager | None = None

    @property
    def _entity_manager(self) -> EntityManager:
        """The active scene's EntityManager.

        There's no global EntityManager to resolve from the container -- each
        scene owns its own world (see Scene-owned world and SystemManager).
        Resolved on every access (not cached at construction time, which runs
        before any scene is registered/active) so tools always see whichever
        scene is currently on top, same as `editor/layer.py`'s
        `scene_manager.current_scene.entity_manager` pattern.

        Before the first scene switch there is no world, so this returns a
        single throwaway empty manager (reused across accesses, not a new one
        each time). A tool that *mutates* the world in that window is writing
        into an orphan that no scene will ever see -- read-only use only until
        a scene is active.
        """
        from pyguara.scene.manager import SceneManager

        current_scene = self._container.get(SceneManager).current_scene
        if current_scene is not None:
            return current_scene.entity_manager
        if self._fallback_entity_manager is None:
            self._fallback_entity_manager = EntityManager()
        return self._fallback_entity_manager

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
        """Process one engine input event.

        Override this to intercept inputs (e.g., stopping a click from
        reaching the game world).

        Args:
            event: An engine input event (`pyguara.events.input` /
                `pyguara.events.lifecycle`), never a raw SDL struct.

        Returns:
            True if the event was consumed by the tool, False otherwise.
        """
        return False

    def on_removed(self) -> None:
        """Release anything acquired in ``__init__`` (subscriptions, handles).

        Called by :meth:`ToolManager.unregister_tool`. The default is a no-op;
        a tool that subscribes to the ``EventDispatcher`` (or holds any other
        resource that outlives it) must override this to undo that, or the
        handler keeps firing against a dead tool.
        """
