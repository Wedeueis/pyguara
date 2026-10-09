"""Base scene abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Generator
from typing import TYPE_CHECKING, Any

from pyguara.ai.ai_system import AISystem
from pyguara.ai.steering_system import SteeringSystem
from pyguara.animation.tweener import TweenSystem
from pyguara.audio.audio_source_system import AudioSourceSystem
from pyguara.audio.audio_system import IAudioSystem
from pyguara.common.components import Transform
from pyguara.di.container import DIContainer, DIScope  # Import Container

if TYPE_CHECKING:
    from pyguara.scripting.coroutines import Coroutine
from pyguara.ecs.entity import Entity
from pyguara.ecs.events import EntityDestroyed
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.animation_system import AnimationSystem
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.pipeline.render_system import RenderSystem
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.log import get_logger
from pyguara.prefabs.factory import PrefabFactory
from pyguara.prefabs.loader import PrefabCache
from pyguara.prefabs.registry import ComponentRegistry
from pyguara.resources.manager import ResourceManager
from pyguara.systems.manager import SystemManager

# Priority band reserved for engine-registered systems on a scene's
# SystemManager (TweenSystem=120, SteeringSystem=150, AISystem=200,
# AudioSourceSystem=250, AnimationSystem=300). Game/scene systems should
# register at >=500.
ENGINE_SYSTEM_PRIORITY_MIN = 100
ENGINE_SYSTEM_PRIORITY_MAX = 399
GAME_SYSTEM_PRIORITY_MIN = 500


logger = get_logger(__name__)


class Scene(ABC):
    """

    Abstract base class for all game scenes.

    Manages the lifecycle of a specific game state (Menu, Gameplay, etc).

    Owns its own world: `entity_manager` and `system_manager` are private to
    this scene, so a scene pushed over another (e.g. a pause menu) never sees
    or affects the entities/systems underneath it. `resolve_dependencies()`
    populates `system_manager` with the five engine systems (Tween, Steering,
    AI, AudioSource, Animation -- priority band 100-399) plus `camera` and
    `render_system`, all live before `on_enter()` ever runs.
    """

    def __init__(self, name: str, event_dispatcher: EventDispatcher) -> None:
        """Initialize the scene."""
        self.name = name
        self.event_dispatcher = event_dispatcher
        self.entity_manager = EntityManager()
        self.system_manager = SystemManager()

        # Built in resolve_dependencies(), which needs the DI container for
        # AudioSourceSystem's dependencies and the active IRenderer backend.
        self.camera: Camera2D | None = None
        self.render_system: RenderSystem | None = None
        self.prefab_factory: PrefabFactory | None = None

        # New: Application will set this before on_enter
        self.container: DIContainer | None = None

        # Built in resolve_dependencies(): one DIScope per scene instance,
        # disposed by SceneManager._exit_scene() when this scene exits. For
        # a scope spanning multiple scenes -- a roguelike run outliving its
        # floor transitions -- see DIContainer.run_scope instead.
        self.scope: DIScope | None = None

        # Set by SceneManager.render() immediately before this scene's own
        # render() runs each frame. 1.0 = fully at the current fixed step --
        # a sane default before the first real render() call.
        self.render_alpha: float = 1.0

        # Callbacks registered through `on_teardown()`, run by
        # `SceneManager._exit_scene()`.
        self._teardown_callbacks: list[Callable[[], None]] = []

    def resolve_dependencies(self, container: DIContainer) -> None:
        """
        Call by the Application/SceneManager to inject the container.

        Builds this scene's engine systems, camera, render system, prefab
        factory, and DI scope (`self.scope`, for resolving `SCOPED`
        registrations tied to this scene's lifetime) -- all live by the time
        this returns, before `on_enter()` runs. Override this if you want to
        grab additional services immediately; call
        `super().resolve_dependencies(container)` first so the engine
        defaults are in place.
        """
        self.container = container
        self.scope = container.create_scope()

        # EntityManager stays decoupled from the event system; this scene
        # subscribes to its removals and republishes them as EntityDestroyed.
        self.entity_manager.subscribe_entity_removed(self._dispatch_entity_destroyed)

        # First in the band: a tween driving `transform.position` must be
        # applied before steering, AI or the scene's own update reads a
        # position this tick, or every reader is one frame behind the
        # animation they can see on screen.
        self.system_manager.register(
            TweenSystem(self.entity_manager),
            priority=120,
            system_type=TweenSystem,
        )
        self.system_manager.register(
            SteeringSystem(self.entity_manager),
            priority=150,
            system_type=SteeringSystem,
        )
        self.system_manager.register(
            AISystem(self.entity_manager), priority=200, system_type=AISystem
        )
        self.system_manager.register(
            AudioSourceSystem(
                self.entity_manager,
                container.get(IAudioSystem),  # type: ignore[type-abstract]
                container.get(ResourceManager),
            ),
            priority=250,
            system_type=AudioSourceSystem,
        )
        self.system_manager.register(
            AnimationSystem(self.entity_manager, self.event_dispatcher),
            priority=300,
            system_type=AnimationSystem,
        )
        self.system_manager.initialize()

        backend = container.get(IRenderer)  # type: ignore[type-abstract]
        self.camera = Camera2D(backend.width, backend.height)
        self.render_system = RenderSystem(backend)

        self.prefab_factory = PrefabFactory(
            self.entity_manager,
            container.get(ComponentRegistry),
            prefab_resolver=container.get(PrefabCache).load,
        )

    def on_teardown(self, callback: Callable[[], None]) -> None:
        """Register a callback to run when this scene exits.

        The symmetric half of `resolve_dependencies()`. Everything that
        builds something scene-lived -- a coroutine, a spawned entity, an
        audio channel, a subscription on a dispatcher the scene does not
        own -- otherwise re-invents "remember what I made, undo it in
        `on_exit`", and each re-invention is a place to forget one.

        Run by `SceneManager._exit_scene()`, not by `on_exit()`: scenes
        override `on_exit()` without calling `super()`, so a callback
        registered here would otherwise fire only for the well-behaved
        ones. They run in reverse registration order, like nested
        context managers, so a later callback can still rely on what an
        earlier one set up.

        A callback that raises is logged and the rest still run: teardown
        that gives up halfway is how a scene leaks the very things this
        exists to release.

        Args:
            callback: Takes nothing, returns nothing. Called exactly once.
        """
        self._teardown_callbacks.append(callback)

    def run_teardown(self) -> None:
        """Run and drop every `on_teardown()` callback.

        Called by `SceneManager._exit_scene()`. Idempotent: the list is
        cleared first, so a scene re-entered after exiting starts empty
        rather than running the previous visit's callbacks again.
        """
        callbacks = self._teardown_callbacks
        self._teardown_callbacks = []

        for callback in reversed(callbacks):
            try:
                callback()
            except Exception as error:
                logger.exception(
                    error,
                    f"A teardown callback for scene '{self.name}' raised; "
                    "the remaining callbacks still run.",
                )

    def _dispatch_entity_destroyed(self, entity: Entity) -> None:
        """Republish a soft-removed entity as an `EntityDestroyed` event.

        Subscribed to `self.entity_manager` in `resolve_dependencies()`; fires
        synchronously from `EntityManager.remove_entity()` with the entity's
        components still intact.

        Args:
            entity: The entity that was just removed.
        """
        self.event_dispatcher.dispatch(EntityDestroyed(entity=entity, source=self))

    @abstractmethod
    def on_enter(self) -> None:
        """Lifecycle hook: Called when scene becomes active."""
        ...

    def start_coroutine(self, generator: Generator[Any, None, None]) -> Coroutine:
        """Start a scripted sequence owned by this scene.

        Tagged with the scene, so `SceneManager` stops it on exit. That
        matters because `CoroutineManager` is an app-global singleton:
        a sequence started through it directly keeps ticking after the scene
        is gone, against entities that no longer exist (#55).

        Prefer this over reaching for `CoroutineManager` from the container
        -- an untagged coroutine is never caught by the scene teardown, and
        the failure is invisible until something touches a dead entity.

        Args:
            generator: The generator to run.

        Returns:
            The `Coroutine`, for `stop()` or `on_complete()`.

        Raises:
            RuntimeError: If called before `resolve_dependencies()`, since
                there is no container to find the manager in.
        """
        if self.container is None:
            raise RuntimeError(
                f"Scene {self.name!r} cannot start a coroutine before "
                "resolve_dependencies() has run -- there is no container yet. "
                "Start sequences in on_enter() or later."
            )
        from pyguara.scripting.coroutines import CoroutineManager

        manager = self.container.get(CoroutineManager)
        return manager.start_coroutine(generator, owner=self)

    @abstractmethod
    def on_exit(self) -> None:
        """Lifecycle hook: Called when scene is removed/swapped."""
        ...

    def on_pause(self) -> None:
        """Lifecycle hook: Called when scene is covered by another scene.

        Override this to pause game logic, music, etc. when the scene is no longer
        the top of the stack. By default, disables this scene's own system_manager
        (a second, independent gate alongside SceneManager's pause_below skip).
        """
        self.system_manager.set_enabled(False)

    def on_resume(self) -> None:
        """Lifecycle hook: Called when scene becomes top of stack again.

        Override this to resume game logic, music, etc. when returning to this scene
        after a scene above it is popped. By default, re-enables this scene's own
        system_manager.
        """
        self.system_manager.set_enabled(True)

    def fixed_update(self, fixed_dt: float) -> None:
        """Fixed-rate update for physics and deterministic game logic.

        Called at a fixed rate (default 60 Hz) regardless of display framerate.
        Override this method to implement physics, collision detection, and
        game logic that must behave consistently regardless of frame rate.

        Args:
            fixed_dt: Fixed delta time in seconds (e.g., 1/60 for 60 Hz physics).

        Example:
            def fixed_update(self, fixed_dt: float) -> None:
                # Physics updates at consistent rate
                self.physics_system.update(fixed_dt)
                # AI decisions at fixed rate for determinism
                self.ai_system.update(fixed_dt)
        """
        pass  # Default: no fixed update logic

    @abstractmethod
    def update(self, dt: float) -> None:
        """Variable-rate update for animations and visual effects.

        Called once per frame at display framerate. Use this for:
        - Smooth animations and tweens
        - Camera smoothing
        - Particle effects
        - Audio updates

        For physics and game logic, use fixed_update() instead.

        Args:
            dt: Variable delta time in seconds (frame time).
        """
        ...

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Frame render logic.

        Default implementation: submits every entity carrying a visible
        `Sprite` component to `self.render_system`, then flushes. When the
        entity also carries a `Transform`, `Sprite.position` is treated as an
        offset from it, combined at submission time without ever writing back
        to `sprite.position` -- preserving that offset instead of the sync
        silently destroying it every frame. If that `Transform` has
        `interpolate=True`, the position used is `lerp(previous_position,
        position, self.render_alpha)` instead of `position` directly,
        smoothing over the gap between fixed steps at display framerate; every
        other `Transform` uses `position` directly, unaffected. An entity with
        only a `Sprite` submits at its own `position` unchanged (the
        standalone case). Override only to add extra manual draws (debug
        overlays, UI-adjacent world drawing), calling
        `super().render(world_renderer, ui_renderer)` first so the default
        submission still happens.
        """
        assert self.render_system is not None and self.camera is not None, (
            "Scene.render() called before resolve_dependencies() built "
            "render_system/camera"
        )

        for entity in self.entity_manager.get_entities_with(Sprite):
            sprite = entity.get_component(Sprite)
            if sprite.visible:
                if entity.has_component(Transform):
                    transform = entity.get_component(Transform)
                    if transform.interpolate:
                        base_position = transform.previous_position.lerp(
                            transform.position, self.render_alpha
                        )
                    else:
                        base_position = transform.position
                    world_position = base_position + sprite.position
                else:
                    world_position = sprite.position
                self.render_system.submit(sprite, position=world_position)

        self.render_system.flush(self.camera)
