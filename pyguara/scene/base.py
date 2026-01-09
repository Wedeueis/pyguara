"""Base scene abstraction."""

from abc import ABC, abstractmethod
from typing import Optional

from pyguara.di.container import DIContainer  # Import Container
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import UIRenderer, IRenderer


class Scene(ABC):
    """
    Abstract base class for all game scenes.

    Manages the lifecycle of a specific game state (Menu, Gameplay, etc).
    """

    def __init__(self, name: str, event_dispatcher: EventDispatcher) -> None:
        """Initialize the scene."""
        self.name = name
        self.event_dispatcher = event_dispatcher
        self.entity_manager = EntityManager()

        # New: Application will set this before on_enter
        self.container: Optional[DIContainer] = None

    def resolve_dependencies(self, container: DIContainer) -> None:
        """
        Call by the Application/SceneManager to inject the container.

        Override this if you want to grab specific services immediately,
        or just use self.container.get() in on_enter().
        """
        self.container = container

    @abstractmethod
    def on_enter(self) -> None:
        """Lifecycle hook: Called when scene becomes active."""
        ...

    @abstractmethod
    def on_exit(self) -> None:
        """Lifecycle hook: Called when scene is removed/swapped."""
        ...

    @abstractmethod
    def update(self, dt: float) -> None:
        """Frame update logic."""
        ...

    @abstractmethod
    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Frame render logic."""
        ...
