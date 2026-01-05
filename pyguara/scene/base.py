"""Base scene definitions."""

from abc import ABC, abstractmethod

from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import UIRenderer


class Scene(ABC):
    """
    Abstract base class for all game scenes.

    A Scene represents a distinct state of the game (e.g., Main Menu, Level 1,
    Inventory Screen). It acts as a container for the ECS World (EntityManager)
    and the Systems that operate on it.

    Attributes:
        name (str): Unique name of the scene.
        entity_manager (EntityManager): The ECS database for this scene.
        event_dispatcher (EventDispatcher): Local or global event bus.
    """

    def __init__(self, name: str, event_dispatcher: EventDispatcher) -> None:
        """Initialize the scene.

        Args:
            name: Unique name for this scene.
            event_dispatcher: Reference to the engine's event dispatcher.
        """
        self.name = name
        self.event_dispatcher = event_dispatcher

        # Each scene gets its own isolated Entity World
        self.entity_manager = EntityManager()

        # State flags
        self.is_active: bool = False
        self.is_paused: bool = False

    @abstractmethod
    def on_enter(self) -> None:
        """Call when the scene becomes active.

        Use this to:
        1. Create initial entities (Player, Map, UI).
        2. Initialize Systems (Physics, Rendering).
        3. Subscribe to events.
        """
        pass

    @abstractmethod
    def on_exit(self) -> None:
        """Call when the scene is removed or swapped.

        Use this to:
        1. Clean up resources.
        2. Unsubscribe from events.
        """
        pass

    @abstractmethod
    def update(self, dt: float) -> None:
        """Call all update logic for the scene.

        This is where you query the EntityManager and pass entities to your Systems.

        Args:
            dt: Delta time in seconds.
        """
        pass

    @abstractmethod
    def render(self, renderer: UIRenderer) -> None:
        """Call all render methods for the scene.

        Args:
            renderer: The graphics backend interface.
        """
        pass
