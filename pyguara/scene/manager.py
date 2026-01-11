"""Scene management system."""

from typing import Dict, Optional, List

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

        # Scene stack for overlays (pause menus, etc.)
        self._scene_stack: List[Scene] = []
        self._pause_below_flags: List[bool] = []

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

        # Clear scene stack when switching scenes
        self._scene_stack.clear()
        self._pause_below_flags.clear()

    def push_scene(
        self,
        scene_name: str,
        pause_below: bool = True,
        transition: Optional[Transition] = None,
    ) -> None:
        """Push a new scene onto the stack.

        Args:
            scene_name: Name of scene to push
            pause_below: If True, scenes below this one won't update
            transition: Optional transition effect

        Raises:
            ValueError: If scene_name is not registered
        """
        if scene_name not in self._scenes:
            raise ValueError(f"Scene '{scene_name}' not registered.")

        target_scene = self._scenes[scene_name]

        # Pause current scene if it exists
        if self._current_scene:
            self._current_scene.on_pause()
            self._scene_stack.append(self._current_scene)
            self._pause_below_flags.append(pause_below)

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
            # Immediate push
            self._current_scene = target_scene
            self._current_scene.on_enter()

    def pop_scene(self, transition: Optional[Transition] = None) -> Optional[Scene]:
        """Pop the top scene off the stack.

        Returns:
            The scene that was popped, or None if stack is empty

        Args:
            transition: Optional transition effect
        """
        if not self._scene_stack:
            # No scenes to pop back to
            return None

        popped_scene = self._current_scene

        # Exit current scene
        if self._current_scene:
            self._current_scene.on_exit()

        # Get previous scene
        previous_scene = self._scene_stack.pop()
        self._pause_below_flags.pop()

        if transition:
            # Use transition
            def on_complete() -> None:
                self._current_scene = previous_scene
                if self._current_scene:
                    self._current_scene.on_resume()

            self._transition_manager.start_transition(
                transition, self._current_scene, previous_scene, on_complete
            )
        else:
            # Immediate pop
            self._current_scene = previous_scene
            if self._current_scene:
                self._current_scene.on_resume()

        return popped_scene

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

        # Update scenes based on pause flags
        if not self.is_transitioning():
            # Find which scenes should update based on pause_below flags
            scenes_to_update = []
            if self._current_scene:
                scenes_to_update.append(self._current_scene)

            # Work backwards through stack to see which scenes should update
            for i in range(len(self._scene_stack) - 1, -1, -1):
                # Check if the scene above this one pauses below
                if i == len(self._scene_stack) - 1:
                    # This is the scene just below current
                    # Check if current scene (or the transition) pauses below
                    if self._pause_below_flags and self._pause_below_flags[-1]:
                        break  # Stop updating scenes below
                else:
                    # Check if scene above this one pauses below
                    if self._pause_below_flags[i + 1]:
                        break

                scenes_to_update.append(self._scene_stack[i])

            # Update all active scenes (in order)
            for scene in reversed(scenes_to_update):
                scene.update(dt)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render current scene and transition effects.

        Args:
            world_renderer: World rendering interface
            ui_renderer: UI rendering interface
        """
        if self.is_transitioning():
            # Transition manager handles rendering during transition
            self._transition_manager.render(world_renderer, ui_renderer)
        else:
            # Render all scenes in the stack (bottom to top)
            for scene in self._scene_stack:
                scene.render(world_renderer, ui_renderer)

            # Render current scene on top
            if self._current_scene:
                self._current_scene.render(world_renderer, ui_renderer)
