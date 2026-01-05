"""Scene management system."""

from typing import Dict, Optional

from pyguara.graphics.protocols import UIRenderer
from pyguara.scene.base import Scene


class SceneManager:
    """
    Manages the lifecycle and transitions of scenes.

    Attributes:
        current_scene (Optional[Scene]): The currently active scene.
    """

    def __init__(self) -> None:
        """Initialize the scene manager."""
        self._scenes: Dict[str, Scene] = {}
        self.current_scene: Optional[Scene] = None

    def register(self, scene: Scene) -> None:
        """Register a scene instance.

        Args:
            scene: The scene to register.
        """
        self._scenes[scene.name] = scene

    def switch_to(self, scene_name: str) -> None:
        """Switch execution to a different scene.

        Calls on_exit() on the current scene and on_enter() on the new one.

        Args:
            scene_name: The name of the scene to switch to.

        Raises:
            KeyError: If the scene name is not registered.
        """
        if scene_name not in self._scenes:
            raise KeyError(f"Scene '{scene_name}' not registered.")

        new_scene = self._scenes[scene_name]

        if self.current_scene:
            self.current_scene.on_exit()
            self.current_scene.is_active = False

        self.current_scene = new_scene
        self.current_scene.is_active = True
        self.current_scene.on_enter()

    def update(self, dt: float) -> None:
        """Update the current scene.

        Args:
            dt: Delta time in seconds.
        """
        if self.current_scene and not self.current_scene.is_paused:
            self.current_scene.update(dt)

    def render(self, renderer: UIRenderer) -> None:
        """Render the current scene.

        Args:
            renderer: The graphics backend interface.
        """
        if self.current_scene:
            self.current_scene.render(renderer)
