"""Base scene abstraction."""

from abc import ABC, abstractmethod
from typing import Optional

from pyguara.ai.ai_system import AISystem
from pyguara.ai.steering_system import SteeringSystem
from pyguara.audio.audio_source_system import AudioSourceSystem
from pyguara.audio.audio_system import IAudioSystem
from pyguara.common.components import Transform
from pyguara.di.container import DIContainer  # Import Container
from pyguara.ecs.entity import Entity
from pyguara.ecs.events import EntityDestroyed
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.animation_system import AnimationSystem
from pyguara.graphics.components.animation import Animator, AnimationStateMachine
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.pipeline.render_system import RenderSystem
from pyguara.graphics.protocols import UIRenderer, IRenderer
from pyguara.prefabs.factory import PrefabFactory
from pyguara.prefabs.loader import PrefabCache
from pyguara.prefabs.registry import ComponentRegistry
from pyguara.resources.manager import ResourceManager
from pyguara.systems.manager import SystemManager

# Priority band reserved for engine-registered systems on a scene's
# SystemManager (SteeringSystem=150, AISystem=200, AudioSourceSystem=250,
# AnimationSystem=300). Game/scene systems should register at >=500.
ENGINE_SYSTEM_PRIORITY_MIN = 100
ENGINE_SYSTEM_PRIORITY_MAX = 399
GAME_SYSTEM_PRIORITY_MIN = 500


class Scene(ABC):
    """
    Abstract base class for all game scenes.

    Manages the lifecycle of a specific game state (Menu, Gameplay, etc).

    Owns its own world: `entity_manager` and `system_manager` are private to
    this scene, so a scene pushed over another (e.g. a pause menu) never sees
    or affects the entities/systems underneath it. `resolve_dependencies()`
    populates `system_manager` with the four engine systems (Steering, AI,
    AudioSource, Animation -- priority band 100-399) plus `camera` and
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
        self.camera: Optional[Camera2D] = None
        self.render_system: Optional[RenderSystem] = None
        self.prefab_factory: Optional[PrefabFactory] = None

        # New: Application will set this before on_enter
        self.container: Optional[DIContainer] = None

    def resolve_dependencies(self, container: DIContainer) -> None:
        """
        Call by the Application/SceneManager to inject the container.

        Builds this scene's engine systems, camera, render system, and
        prefab factory -- all live by the time this returns, before
        `on_enter()` runs. Override this if you want to grab additional
        services immediately; call `super().resolve_dependencies(container)`
        first so the engine defaults are in place.
        """
        self.container = container

        # EntityManager stays decoupled from the event system; wire its
        # removal hook to dispatch EntityDestroyed here instead.
        self.entity_manager._on_entity_removed = self._on_entity_removed

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
            AnimationSystem(self.entity_manager),
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

    def _on_entity_removed(self, entity: Entity) -> None:
        """Dispatch EntityDestroyed for an entity this scene just soft-removed.

        Wired onto `self.entity_manager._on_entity_removed` in
        `resolve_dependencies()`; fires synchronously from
        `EntityManager.remove_entity()`, components still intact.
        """
        self.event_dispatcher.dispatch(EntityDestroyed(entity=entity, source=self))

    def update_animations(self, dt: float) -> None:
        """
        Update all animation components in the scene.

        Automatically updates all Animator and AnimationStateMachine components.
        Call this in your scene's update() method to enable automatic animation updates.

        Args:
            dt (float): Delta time in seconds.

        Example:
            def update(self, dt: float) -> None:
                self.update_animations(dt)  # Update all animations
                # ... rest of scene logic
        """
        # Update AnimationStateMachine components (higher priority)
        for entity in self.entity_manager.get_entities_with(AnimationStateMachine):
            fsm = entity.get_component(AnimationStateMachine)
            fsm.update(dt)

        # Update standalone Animator components (if not controlled by FSM)
        for entity in self.entity_manager.get_entities_with(Animator):
            # Skip if entity also has AnimationStateMachine (FSM updates animator)
            if not entity.has_component(AnimationStateMachine):
                animator = entity.get_component(Animator)
                animator.update(dt)

    @abstractmethod
    def on_enter(self) -> None:
        """Lifecycle hook: Called when scene becomes active."""
        ...

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
        offset from it (`transform.position + sprite.position`), combined at
        submission time without ever writing back to `sprite.position` --
        preserving that offset instead of the sync silently destroying it
        every frame. An entity with only a `Sprite` submits at its own
        `position` unchanged (the standalone case). Override only to add
        extra manual draws (debug overlays, UI-adjacent world drawing),
        calling `super().render(world_renderer, ui_renderer)` first so the
        default submission still happens.
        """
        assert self.render_system is not None and self.camera is not None, (
            "Scene.render() called before resolve_dependencies() built "
            "render_system/camera"
        )

        for entity in self.entity_manager.get_entities_with(Sprite):
            sprite = entity.get_component(Sprite)
            if sprite.visible:
                if entity.has_component(Transform):
                    world_position = (
                        entity.get_component(Transform).position + sprite.position
                    )
                else:
                    world_position = sprite.position
                self.render_system.submit(sprite, position=world_position)

        self.render_system.flush(self.camera)
