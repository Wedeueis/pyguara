"""Scene management system."""

from typing import Dict, Optional

from pyguara.di.container import DIContainer
from pyguara.graphics.protocols import UIRenderer, IRenderer
from pyguara.scene.base import Scene


class SceneManager:
    """Coordinator for scene transitions and lifecycle."""

    def __init__(self) -> None:
        """Initialize Scene Manager."""
        self._scenes: Dict[str, Scene] = {}
        self._current_scene: Optional[Scene] = None
        self._container: Optional[DIContainer] = None  # Store container ref

    def set_container(self, container: DIContainer) -> None:
        """Receive the DI container from the Application."""
        self._container = container

    @property
    def current_scene(self) -> Optional[Scene]:
        """Get the currently active scene."""
        return self._current_scene

    def register(self, scene: Scene) -> None:
        """Add a scene to the manager and inject dependencies."""
        self._scenes[scene.name] = scene

        # Auto-wire the scene if we have the container
        if self._container:
            scene.resolve_dependencies(self._container)

    def switch_to(self, scene_name: str) -> None:
        """Transition to a new scene."""
        if scene_name not in self._scenes:
            raise ValueError(f"Scene '{scene_name}' not registered.")

        if self._current_scene:
            self._current_scene.on_exit()

        self._current_scene = self._scenes[scene_name]
        self._current_scene.on_enter()

    def update(self, dt: float) -> None:
        """Delegate update to current scene."""
        if self._current_scene:
            self._current_scene.update(dt)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Delegate render to current scene."""
        if self._current_scene:
            self._current_scene.render(world_renderer, ui_renderer)
