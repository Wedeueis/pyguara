"""Scene management system."""

from typing import Dict, Optional

from pyguara.di.container import DIContainer
from pyguara.graphics.protocols import UIRenderer, IRenderer
from pyguara.scene.base import Scene
from pyguara.scene.transitions import TransitionManager, Transition


class SceneManager:
    """Coordinator for scene transitions and lifecycle."""

    def __init__(self) -> None:
        """Initialize Scene Manager."""
        self._scenes: Dict[str, Scene] = {}
        self._current_scene: Optional[Scene] = None
        self._container: Optional[DIContainer] = None  # Store container ref
        self._transition_manager = TransitionManager()
        self._pending_scene: Optional[str] = None

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

    def set_screen_size(self, width: int, height: int) -> None:
        """Set screen dimensions for transitions.

        Args:
            width: Screen width in pixels
            height: Screen height in pixels
        """
        self._transition_manager.set_screen_size(width, height)

    def switch_to(
        self, scene_name: str, transition: Optional[Transition] = None
    ) -> None:
        """Transition to a new scene.

        Args:
            scene_name: Name of scene to switch to
            transition: Optional transition effect. If None, switches immediately.

        Raises:
            ValueError: If scene_name is not registered
        """
        if scene_name not in self._scenes:
            raise ValueError(f"Scene '{scene_name}' not registered.")

        target_scene = self._scenes[scene_name]

        if transition:
            # Use transition
            self._pending_scene = scene_name

            def on_complete() -> None:
                self._current_scene = target_scene
                self._pending_scene = None

            self._transition_manager.start_transition(
                transition, self._current_scene, target_scene, on_complete
            )
        else:
            # Immediate switch
            if self._current_scene:
                self._current_scene.on_exit()

            self._current_scene = target_scene
            self._current_scene.on_enter()

    def is_transitioning(self) -> bool:
        """Check if a scene transition is in progress.

        Returns:
            True if transition is active
        """
        return self._transition_manager.is_transitioning()

    def update(self, dt: float) -> None:
        """Update current scene and transitions.

        Args:
            dt: Delta time in seconds
        """
        # Update transition
        self._transition_manager.update(dt)

        # Update current scene if not transitioning
        if not self.is_transitioning() and self._current_scene:
            self._current_scene.update(dt)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render current scene and transition effects.

        Args:
            world_renderer: World rendering interface
            ui_renderer: UI rendering interface
        """
        if self.is_transitioning():
            # Transition manager handles rendering during transition
            self._transition_manager.render(world_renderer, ui_renderer)
        elif self._current_scene:
            # Normal scene rendering
            self._current_scene.render(world_renderer, ui_renderer)
