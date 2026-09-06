"""Scene management system."""

from collections.abc import Callable
from dataclasses import dataclass

from pyguara.common.components import Transform
from pyguara.di.container import DIContainer
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.scene.base import Scene
from pyguara.scene.transitions import Transition, TransitionManager


@dataclass
class StackEntry:
    """A scene retained on the stack, plus the pause_below it was pushed with."""

    scene: Scene
    pause_below: bool


class SceneManager:
    """Coordinator for scene transitions and lifecycle."""

    def __init__(self) -> None:
        """Initialize Scene Manager."""
        self._scenes: dict[str, Scene] = {}
        self._current_scene: Scene | None = None
        self._container: DIContainer | None = None  # Store container ref
        self._transition_manager = TransitionManager()
        self._pending_scene: str | None = None

        # Scene stack for overlays (pause menus, etc.). `_current_pause_below`
        # tracks the pause_below the *current* scene was activated with
        # (False for the base scene); each StackEntry carries the
        # pause_below that applied when that scene was itself current.
        self._stack: list[StackEntry] = []
        self._current_pause_below: bool = False

    def set_container(self, container: DIContainer) -> None:
        """Receive the DI container from the Application."""
        self._container = container

    @property
    def current_scene(self) -> Scene | None:
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

    def switch_to(self, scene_name: str, transition: Transition | None = None) -> None:
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
        from_scene = self._current_scene

        if transition:
            # Use transition
            self._pending_scene = scene_name

            on_from_hidden: Callable[[], None] | None = None
            if from_scene is not None:
                captured_from_scene = from_scene
                on_from_hidden = lambda: self._exit_scene(captured_from_scene)  # noqa: E731

            def on_complete() -> None:
                self._current_scene = target_scene
                self._current_pause_below = False
                self._pending_scene = None

            self._transition_manager.start_transition(
                transition,
                from_scene,
                target_scene,
                on_complete,
                on_from_hidden=on_from_hidden,
                on_to_shown=target_scene.on_enter,
            )
        else:
            # Immediate switch
            if from_scene is not None:
                self._exit_scene(from_scene)

            self._current_scene = target_scene
            self._current_pause_below = False
            self._current_scene.on_enter()

        # Clear scene stack when switching scenes
        self._stack.clear()

    def push_scene(
        self,
        scene_name: str,
        pause_below: bool = True,
        transition: Transition | None = None,
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

        # Pause current scene if it exists -- happens synchronously
        # regardless of transition, since the scene underneath stays alive
        # either way; only the incoming scene's enter is transition-gated.
        if self._current_scene is not None:
            self._pause_scene(self._current_scene)
            self._stack.append(
                StackEntry(self._current_scene, self._current_pause_below)
            )

        if transition:
            # Use transition
            self._pending_scene = scene_name

            def on_complete() -> None:
                self._current_scene = target_scene
                self._current_pause_below = pause_below
                self._pending_scene = None

            self._transition_manager.start_transition(
                transition,
                self._current_scene,
                target_scene,
                on_complete,
                on_from_hidden=None,
                on_to_shown=target_scene.on_enter,
            )
        else:
            # Immediate push
            self._current_scene = target_scene
            self._current_pause_below = pause_below
            self._current_scene.on_enter()

    def pop_scene(self, transition: Transition | None = None) -> Scene | None:
        """Pop the top scene off the stack.

        Returns:
            The scene that was popped, or None if stack is empty

        Args:
            transition: Optional transition effect
        """
        if not self._stack:
            # No scenes to pop back to
            return None

        popped_scene = self._current_scene
        entry = self._stack.pop()
        previous_scene = entry.scene
        previous_pause_below = entry.pause_below

        if transition:
            # Use transition. The popped scene's exit -- and the previous
            # scene's resume -- fire through the transition's callbacks
            # rather than synchronously, so a fade-out still has the
            # outgoing scene alive to render.
            on_from_hidden: Callable[[], None] | None = None
            if popped_scene is not None:
                captured_popped_scene = popped_scene
                on_from_hidden = lambda: self._exit_scene(captured_popped_scene)  # noqa: E731

            def on_to_shown() -> None:
                self._resume_scene(previous_scene)

            def on_complete() -> None:
                self._current_scene = previous_scene
                self._current_pause_below = previous_pause_below

            self._transition_manager.start_transition(
                transition,
                popped_scene,
                previous_scene,
                on_complete,
                on_from_hidden=on_from_hidden,
                on_to_shown=on_to_shown,
            )
        else:
            # Immediate pop
            if popped_scene is not None:
                self._exit_scene(popped_scene)
            self._current_scene = previous_scene
            self._current_pause_below = previous_pause_below
            self._resume_scene(previous_scene)

        return popped_scene

    def is_transitioning(self) -> bool:
        """Check if a scene transition is in progress.

        Returns:
            True if transition is active
        """
        return self._transition_manager.is_transitioning()

    def fixed_update(self, fixed_dt: float) -> None:
        """Fixed-rate update for physics and deterministic game logic.

        Called at a fixed rate (e.g., 60 Hz) regardless of display framerate.
        Snapshots `previous_position` for every `Transform.interpolate=True`
        entity first, before any system runs this tick -- a single
        centralized point every current and future position-mutating system
        (Steering, Physics, the platformer controller) runs after, rather
        than each needing its own snapshot logic. Ticks each active scene's
        own SystemManager (the four engine systems: Steering, AI,
        AudioSource, Animation) before the scene's own fixed_update() --
        there's no global SystemManager anymore, each scene owns and ticks
        its own. Flushes each scene's own EntityManager at the end of its
        fixed-update work (the frame boundary the ECS lifecycle contract
        defers physical index cleanup to) -- there's no global EntityManager
        either, so this can't happen in Application anymore.

        Args:
            fixed_dt: Fixed delta time in seconds.
        """
        if self.is_transitioning():
            return

        # Find which scenes should update based on pause_below flags
        scenes_to_update = self._get_active_scenes()

        for scene in scenes_to_update:
            for entity in scene.entity_manager.get_entities_with(Transform):
                transform = entity.get_component(Transform)
                if transform.interpolate:
                    transform.previous_position = transform.position

        # Fixed update all active scenes (in order, bottom to top)
        for scene in reversed(scenes_to_update):
            scene.system_manager.update(fixed_dt)
            scene.fixed_update(fixed_dt)
            scene.entity_manager.flush_pending_removals()

    def update(self, dt: float) -> None:
        """Variable-rate update for UI and smooth animations.

        Called once per frame at display framerate.

        Args:
            dt: Delta time in seconds (variable).
        """
        # Update transition
        self._transition_manager.update(dt)

        if self.is_transitioning():
            return

        # Update all active scenes (in order, bottom to top)
        scenes_to_update = self._get_active_scenes()
        for scene in reversed(scenes_to_update):
            scene.update(dt)

    def _get_active_scenes(self) -> list[Scene]:
        """Get list of scenes that should receive updates.

        Uniform walk, no index arithmetic: start at the current scene with
        its own pause_below as the gate; walk the stack top-down, stopping
        as soon as the gate is True, otherwise including that entry's scene
        and updating the gate to *that entry's own* pause_below.

        Returns:
            List of active scenes based on pause_below flags.
        """
        scenes_to_update: list[Scene] = []
        if self._current_scene is None:
            return scenes_to_update

        scenes_to_update.append(self._current_scene)
        gate = self._current_pause_below

        for entry in reversed(self._stack):
            if gate:
                break
            scenes_to_update.append(entry.scene)
            gate = entry.pause_below

        return scenes_to_update

    def render(
        self, world_renderer: IRenderer, ui_renderer: UIRenderer, alpha: float = 1.0
    ) -> None:
        """Render current scene and transition effects.

        Args:
            world_renderer: World rendering interface
            ui_renderer: UI rendering interface
            alpha: How far the current frame sits between the last two fixed
                steps (`accumulator / fixed_dt`), for `Transform.interpolate`
                entities. Set on each scene as `render_alpha` immediately
                before that scene's `render()` runs, rather than threaded as
                a `Scene.render()` parameter -- every one of the 9 demos
                already overrides that exact two-parameter signature, so
                adding a third would force a mechanical change across all of
                them for a value only the base default combination uses.
        """
        if self.is_transitioning():
            # Transition manager handles rendering during transition
            self._transition_manager.render(world_renderer, ui_renderer)
        else:
            # Render all scenes in the stack (bottom to top)
            for entry in self._stack:
                entry.scene.render_alpha = alpha
                entry.scene.render(world_renderer, ui_renderer)

            # Render current scene on top
            if self._current_scene:
                self._current_scene.render_alpha = alpha
                self._current_scene.render(world_renderer, ui_renderer)

    def cleanup(self) -> None:
        """Cleanup resources, unwinding every scene ever entered, LIFO.

        `on_exit()` on the current scene first (entered last), then the
        stack top-to-bottom -- every scene that was ever entered gets torn
        down exactly once, rather than leaking whatever's still on the
        stack past a bare `.clear()`.
        """
        if self._current_scene is not None:
            self._exit_scene(self._current_scene)
            self._current_scene = None

        for entry in reversed(self._stack):
            self._exit_scene(entry.scene)

        self._stack.clear()

    def _exit_scene(self, scene: Scene) -> None:
        """Run a scene's exit hook and guarantee its SystemManager is cleaned up.

        Calls `scene.system_manager.cleanup()` directly rather than relying on
        `scene.on_exit()` to do it: existing scenes already override
        `on_exit()` without calling `super()`, so a base-class default there
        wouldn't reliably fire.
        """
        scene.on_exit()
        scene.system_manager.cleanup()

    def _pause_scene(self, scene: Scene) -> None:
        """Run a scene's pause hook and guarantee its SystemManager is disabled.

        Same reasoning as `_exit_scene()`: calls `set_enabled(False)` directly
        rather than trusting every `on_pause()` override to call `super()`.
        """
        scene.on_pause()
        scene.system_manager.set_enabled(False)

    def _resume_scene(self, scene: Scene) -> None:
        """Run a scene's resume hook and guarantee its SystemManager is re-enabled.

        Same reasoning as `_exit_scene()`: calls `set_enabled(True)` directly
        rather than trusting every `on_resume()` override to call `super()`.
        """
        scene.on_resume()
        scene.system_manager.set_enabled(True)
