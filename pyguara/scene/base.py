"""Base scene abstraction."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator
from typing import TYPE_CHECKING, Any, TypeVar

from pyguara.ai.ai_system import AISystem
from pyguara.ai.steering_system import SteeringSystem
from pyguara.animation.tweener import TweenSystem
from pyguara.audio.audio_source_system import AudioSourceSystem
from pyguara.audio.audio_system import IAudioSystem
from pyguara.common.components import Transform
from pyguara.di.container import DIContainer, DIScope  # Import Container

if TYPE_CHECKING:
    from pyguara.application.application import Application
    from pyguara.i18n import Translator
    from pyguara.input.manager import InputManager
    from pyguara.scene.manager import SceneManager
    from pyguara.scripting.coroutines import Coroutine
    from pyguara.ui.manager import UIManager
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

_T = TypeVar("_T")


class SceneNotReadyError(RuntimeError):
    """A scene asked for an engine service before it was given a container.

    The container arrives in `Scene.resolve_dependencies()`, which runs when
    the scene is registered with a `SceneManager`, so a service is there from
    `on_enter()` onwards and never in `__init__`.
    """


class Scene(ABC):
    """Abstract base class for all game scenes.

    Manages the lifecycle of a specific game state (Menu, Gameplay, etc).

    Owns its own world: `entity_manager` and `system_manager` are private to
    this scene, so a scene pushed over another (e.g. a pause menu) never sees
    or affects the entities/systems underneath it. `resolve_dependencies()`
    populates `system_manager` with the five engine systems (Tween, Steering,
    AI, AudioSource, Animation -- priority band 100-399) plus `camera` and
    `render_system`, all live before `on_enter()` ever runs.
    """

    def __init__(
        self,
        name: str | None = None,
        event_dispatcher: EventDispatcher | None = None,
    ) -> None:
        """Initialize the scene.

        Args:
            name: What the `SceneManager` registers the scene under. Defaults
                to the class name.
            event_dispatcher: The dispatcher to publish and subscribe on.
                When omitted, the engine supplies the application's own in
                `resolve_dependencies()`, so it is there from `on_enter()`.
        """
        self.name = name if name is not None else type(self).__name__
        self._event_dispatcher = event_dispatcher
        self.entity_manager = EntityManager()
        self.system_manager = SystemManager()

        # Built in resolve_dependencies(), which needs the DI container for
        # AudioSourceSystem's dependencies and the active IRenderer backend.
        #
        # **The camera this scene renders with.** Not "a camera the base
        # class happens to provide": everything that has to turn a world
        # position into a screen one from outside the frame reads this --
        # Studio's viewport, its picking, and the transform gizmo. A scene
        # that overrides `render()` and draws with a camera of its own must
        # assign it here, or those draw in the wrong place while the frame
        # itself looks right, which is a confusing way to find out.
        self.camera: Camera2D | None = None
        self.render_system: RenderSystem | None = None

        # Whether `render()` skips sprites wholly outside the camera's view.
        # Off for a scene whose materials draw beyond a sprite's own box.
        self.cull_sprites = True
        self.prefab_factory: PrefabFactory | None = None

        # New: Application will set this before on_enter
        self.container: DIContainer | None = None

        # Built in resolve_dependencies(): one DIScope per visit, disposed by
        # SceneManager._exit_scene() when this scene exits, and built again
        # if it is entered again. For
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
        self._republishing_removals = False

    def resolve_dependencies(self, container: DIContainer) -> None:
        """Call by the Application/SceneManager to inject the container.

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
        if self._event_dispatcher is None:
            self._event_dispatcher = container.get(EventDispatcher)

        # EntityManager stays decoupled from the event system; this scene
        # subscribes to its removals and republishes them as EntityDestroyed.
        # Once only: a scene entered again after exiting is wired again, and
        # a second subscription would report every removal twice.
        if not self._republishing_removals:
            self.entity_manager.subscribe_entity_removed(
                self._dispatch_entity_destroyed
            )
            self._republishing_removals = True

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

        For anything scene-lived that needs undoing: a spawned entity, an
        audio channel, a subscription on a dispatcher the scene does not own.

        Run by `SceneManager`, not by `on_exit()`, so a scene that overrides
        `on_exit()` without calling `super()` still gets them. Callbacks run
        in reverse registration order. One that raises is logged and the rest
        still run.

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

        Tagged with the scene, so `SceneManager` stops it on exit. A sequence
        started on `CoroutineManager` directly is untagged, and keeps ticking
        after the scene is gone.

        Args:
            generator: The generator to run.

        Returns:
            The `Coroutine`, for `stop()` or `on_complete()`.

        Raises:
            SceneNotReadyError: If called before `resolve_dependencies()`,
                since there is no container to find the manager in.
        """
        from pyguara.scripting.coroutines import CoroutineManager

        manager = self._service(CoroutineManager, "start a coroutine")
        return manager.start_coroutine(generator, owner=self)

    # -- The engine's common services ------------------------------------
    #
    # The sanctioned way for a scene to reach them (ADR 0012). Anything not
    # listed here is `self.container.get(T)`, the escape hatch. Each is a
    # lookup, not a cached attribute: the container is the one place a test
    # substitutes a service, and a copy taken at resolve time would miss it.

    @property
    def event_dispatcher(self) -> EventDispatcher:
        """The dispatcher this scene publishes and subscribes on.

        The one passed to the constructor, or else the application's own,
        which arrives with the container.

        Raises:
            SceneNotReadyError: If none was passed to the constructor and
                `resolve_dependencies()` has not run yet.
        """
        if self._event_dispatcher is None:
            raise SceneNotReadyError(
                f"Scene {self.name!r} has no event dispatcher before "
                "resolve_dependencies() has run. Subscribe in on_enter() or "
                "later, or pass a dispatcher to the constructor."
            )
        return self._event_dispatcher

    @event_dispatcher.setter
    def event_dispatcher(self, dispatcher: EventDispatcher) -> None:
        self._event_dispatcher = dispatcher

    @property
    def application(self) -> Application:
        """The running `Application`: step hooks, time scale, quitting.

        Raises:
            SceneNotReadyError: Before `resolve_dependencies()` has run.
        """
        from pyguara.application.application import Application

        return self._service(Application, "reach the application")

    @property
    def scene_manager(self) -> SceneManager:
        """The `SceneManager` this scene is registered with.

        Raises:
            SceneNotReadyError: Before `resolve_dependencies()` has run.
        """
        from pyguara.scene.manager import SceneManager

        return self._service(SceneManager, "reach the scene manager")

    @property
    def ui_manager(self) -> UIManager:
        """The `UIManager` that owns the HUD and overlay layers.

        Raises:
            SceneNotReadyError: Before `resolve_dependencies()` has run.
        """
        from pyguara.ui.manager import UIManager

        return self._service(UIManager, "reach the UI manager")

    @property
    def input_manager(self) -> InputManager:
        """The `InputManager`: actions, bindings and contexts.

        Raises:
            SceneNotReadyError: Before `resolve_dependencies()` has run.
        """
        from pyguara.input.manager import InputManager

        return self._service(InputManager, "reach the input manager")

    @property
    def translator(self) -> Translator:
        """The `Translator` for the game's locales; see `tr()`.

        Raises:
            SceneNotReadyError: Before `resolve_dependencies()` has run.
            RuntimeError: If the game has no locales folder, so none was
                registered.
        """
        from pyguara.i18n import Translator

        if self.container is not None and not self.container.is_registered(Translator):
            raise RuntimeError(
                "No translator: the game has no locales folder (config "
                "i18n.directory, 'locales' by default) holding an en.json, "
                "so there is no text to look keys up in."
            )
        return self._service(Translator, "translate text")

    def tr(self, key: str, /, **values: Any) -> str:
        """Return `key`'s text in the player's language.

        `self.tr("hud.salvage", count=3)`. See `pyguara.i18n.Translator`.

        Raises:
            SceneNotReadyError: Before `resolve_dependencies()` has run.
            RuntimeError: If the game has no locales folder.
            MissingStringError: If the source locale has no such key.
        """
        return self.translator(key, **values)

    def _service(self, service_type: type[_T], purpose: str) -> _T:
        """Look `service_type` up in this scene's container, or say when to ask.

        Raises:
            SceneNotReadyError: If the scene has no container yet.
        """
        if self.container is None:
            raise SceneNotReadyError(
                f"Scene {self.name!r} cannot {purpose} before "
                "resolve_dependencies() has run -- there is no container yet. "
                "Ask in on_enter() or later."
            )
        return self.container.get(service_type)

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

        The default submits every entity carrying a visible `Sprite` to
        `self.render_system`, then flushes. With a `Transform`,
        `Sprite.position` is an offset from it, lerped by `render_alpha`
        when the `Transform` has `interpolate=True`. A sprite wholly outside
        the camera's view is skipped unless `cull_sprites` is off; its box
        is taken as large as any turn of it could be.

        Override to add manual draws, calling
        `super().render(world_renderer, ui_renderer)` first.
        """
        assert self.render_system is not None and self.camera is not None, (
            "Scene.render() called before resolve_dependencies() built "
            "render_system/camera"
        )

        cull = self.cull_sprites
        view = self.camera.get_view_bounds()
        # A pixel of slack: the bounds are whole pixels, the camera is not.
        left, top = view.x - 1, view.y - 1
        right, bottom = view.x + view.width + 1, view.y + view.height + 1

        for entity in self.entity_manager.get_entities_with(Sprite):
            sprite = entity.get_component(Sprite)
            if not sprite.visible:
                continue
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
            if cull:
                # The sprite's box starts at its position, so one starting
                # inside the view is drawn without asking its size. Turned,
                # the box bounds the turned image and is never wider than
                # the diagonal, which is the bound for any turn.
                x, y = world_position.x, world_position.y
                if x > right or y > bottom:
                    continue
                if x < left or y < top:
                    texture, scale = sprite.texture, sprite.scale
                    extent = math.hypot(
                        texture.width * scale.x, texture.height * scale.y
                    )
                    if x + extent < left or y + extent < top:
                        continue
            self.render_system.submit(sprite, position=world_position)

        self.render_system.flush(self.camera)
