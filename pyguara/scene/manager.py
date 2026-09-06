"""Scene management system."""

from collections.abc import Callable
from dataclasses import dataclass

from pyguara.common.components import Transform
from pyguara.di.container import DIContainer
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.log import get_logger
from pyguara.scene.base import Scene
from pyguara.scene.transitions import Transition, TransitionManager

logger = get_logger(__name__)


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
        """Receive the DI container and wire every scene with it.

        Scenes registered before the container arrived are wired here.
        Without this, `register()` silently skipped `resolve_dependencies()`
        and left the scene live but with no camera, render system or engine
        systems -- surfacing much later as an assertion inside `render()`.

        Args:
            container: The application's DI container.
        """
        self._container = container
        for scene in self._scenes.values():
            if scene.container is None:
                scene.resolve_dependencies(container)

    @property
    def current_scene(self) -> Scene | None:
        """Get the currently active scene."""
        return self._current_scene

    def register(self, scene: Scene) -> None:
        """Add a scene under its name, wiring it if the container is available.

        Registering before `set_container()` is fine: the scene is wired when
        the container arrives.

        Args:
            scene: The scene to register. Replaces any scene already
                registered under the same name, which is logged since the
                displaced scene becomes unreachable.
        """
        existing = self._scenes.get(scene.name)
        if existing is not None and existing is not scene:
            logger.warning(
                f"Replacing the scene already registered as '{scene.name}'. "
                f"The previous one is now unreachable by name."
            )

        self._scenes[scene.name] = scene

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
        """Replace the whole scene stack with one scene.

        Every scene currently on the stack is exited, top-down, before the new
        one is activated. A switch requested while a transition is already
        running is ignored, so the in-flight one finishes rather than leaving
        a half-entered scene behind.

        Args:
            scene_name: Name of the scene to switch to.
            transition: Optional transition effect. Switches immediately when
                None.

        Raises:
            ValueError: If `scene_name` is not registered.
        """
        if scene_name not in self._scenes:
            raise ValueError(f"Scene '{scene_name}' not registered.")

        if self._reject_during_transition(f"switch to '{scene_name}'"):
            return

        target_scene = self._scenes[scene_name]
        from_scene = self._current_scene

        # The stack is unwound as part of leaving, LIFO, after the current
        # scene exits. A bare `.clear()` abandoned every scene underneath --
        # still holding its EntityManager, systems and physics bodies --
        # without ever calling on_exit(), the exact leak cleanup() was
        # written to avoid.
        def leave_everything() -> None:
            if from_scene is not None:
                self._exit_scene(from_scene)
            self._unwind_stack()

        if transition:
            # Use transition
            self._pending_scene = scene_name

            # Deferred to on_from_hidden so a fade-out still has the outgoing
            # scene alive to render.
            on_from_hidden: Callable[[], None] | None = leave_everything

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
            leave_everything()

            self._current_scene = target_scene
            self._current_pause_below = False
            self._current_scene.on_enter()

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
            ValueError: If `scene_name` is not registered.
        """
        if scene_name not in self._scenes:
            raise ValueError(f"Scene '{scene_name}' not registered.")

        if self._reject_during_transition(f"push '{scene_name}'"):
            return

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
        """Return to the scene beneath the current one.

        A pop requested while a transition is already running is ignored.

        Args:
            transition: Optional transition effect. Pops immediately when None.

        Returns:
            The scene that was popped, or None if the stack was empty or a
            transition was already in flight.
        """
        if not self._stack:
            # No scenes to pop back to
            return None

        if self._reject_during_transition("pop"):
            return None

        popped_scene = self._current_scene
        entry = self._stack[-1]
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
                # Only now drop the entry. Popping it up front left the
                # previous scene both off the stack and not yet current, so a
                # cleanup() during the transition never exited it.
                if self._stack and self._stack[-1] is entry:
                    self._stack.pop()
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
            self._stack.pop()
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
        """Tear down every live scene, LIFO, exiting each exactly once.

        The current scene goes first (entered last), then the stack top-down.
        A scene that a transition has started entering but not yet made
        current is included too, so an application shutting down mid-fade does
        not leave it holding its world.
        """
        exited: set[int] = set()

        for scene in (self._current_scene, self._transition_target()):
            if scene is not None and id(scene) not in exited:
                exited.add(id(scene))
                self._exit_scene(scene)
        self._current_scene = None

        for entry in reversed(self._stack):
            if id(entry.scene) not in exited:
                exited.add(id(entry.scene))
                self._exit_scene(entry.scene)

        self._stack.clear()

    def _transition_target(self) -> Scene | None:
        """Return the scene an in-flight transition is moving to, if any.

        Returns:
            The pending scene, or None when nothing is transitioning.
        """
        if self._pending_scene is None:
            return None
        return self._scenes.get(self._pending_scene)

    def _unwind_stack(self) -> None:
        """Exit and discard every stacked scene, top-down."""
        for entry in reversed(self._stack):
            self._exit_scene(entry.scene)
        self._stack.clear()

    def _reject_during_transition(self, action: str) -> bool:
        """Refuse a stack change while a transition is running.

        Letting a second request through replaced the pending scene, so the
        first target was skipped without ever receiving `on_enter()` while its
        predecessor had already been exited.

        Args:
            action: Human-readable description, for the log message.

        Returns:
            True if the caller should return without doing anything.
        """
        if not self.is_transitioning():
            return False
        logger.warning(
            f"Ignoring request to {action}: a scene transition is already in "
            f"progress. Wait for is_transitioning() to return False."
        )
        return True

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
