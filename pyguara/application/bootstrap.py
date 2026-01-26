"""Application setup and dependency wiring."""

from pyguara.application.application import Application
from pyguara.config.manager import ConfigManager
from pyguara.config.types import RenderingBackend
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.backends.pygame.pygame_window import PygameWindow
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.graphics.pipeline.framebuffer import FramebufferManager
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.protocols import UIRenderer, IRenderer, TextureFactory
from pyguara.graphics.window import Window, WindowConfig
from pyguara.input.manager import InputManager
from pyguara.log.manager import LogManager
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.collision_system import CollisionSystem
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.resources.loaders.data_loader import JsonLoader
from pyguara.resources.manager import ResourceManager
from pyguara.scene.manager import SceneManager
from pyguara.scene.serializer import SceneSerializer
from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.migration import MigrationManager, get_global_registry
from pyguara.persistence.storage import FileStorageBackend
from pyguara.prefabs.registry import ComponentRegistry, get_component_registry
from pyguara.prefabs.factory import PrefabFactory
from pyguara.prefabs.loader import PrefabLoader, PrefabCache
from pyguara.ui.manager import UIManager
from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem
from pyguara.audio.backends.pygame.loaders import PygameSoundLoader
from pyguara.audio.manager import AudioManager
from pyguara.audio.audio_source_system import AudioSourceSystem
from pyguara.graphics.animation_system import AnimationSystem
from pyguara.ecs.manager import EntityManager
from pyguara.systems.manager import SystemManager
from pyguara.ai.ai_system import AISystem
from pyguara.ai.steering_system import SteeringSystem
from pyguara.scripting.coroutines import CoroutineManager
from .sandbox import SandboxApplication


def create_application() -> Application:
    """
    Construct and configure the Application instance.

    This factory function handles the Dependency Injection wiring:
    1. Creates the container.
    2. Loads configuration.
    3. Setup logging.
    4. Initializes the Window based on config.
    5., 6., 7. ... Registers all core subsystems (Input, Physics, UI, Resources).

    Returns:
        A fully configured Application ready to run.
    """
    container = _setup_container()
    return Application(container)


def create_sandbox_application() -> SandboxApplication:
    """
    Construct and configure the SandboxApplication instance.

    Includes developer tools.
    """
    container = _setup_container()
    return SandboxApplication(container)


def _setup_container() -> DIContainer:
    """Configure common dependencies internally."""
    # 1. Event System (Core)
    event_dispatcher = EventDispatcher()

    # 2. Configuration System
    config_manager = ConfigManager(event_dispatcher=event_dispatcher)
    config_manager.load()  # Loads from disk or defaults

    # 3. Logging System
    debug_cfg = config_manager.config.debug
    log_manager = LogManager(event_dispatcher=event_dispatcher)
    log_manager.configure(
        level=debug_cfg.log_level,
        console=debug_cfg.console_logging,
        dispatcher=event_dispatcher,
        log_file=debug_cfg.log_file_path if debug_cfg.log_to_file else None,
    )

    # 3.2 Setup bootrap temp logger
    logger = log_manager.get_logger("Bootstrap")
    logger.info("Core services (Events, Config, Log) initialized.")

    # Initialize the container to register the core services
    container = DIContainer()

    container.register_instance(EventDispatcher, event_dispatcher)
    container.register_instance(ConfigManager, config_manager)
    container.register_instance(LogManager, log_manager)

    logger.debug("Core instances registered in DI Container.")

    # 4. Window System
    # Extract settings from loaded config
    disp_cfg = config_manager.config.display

    win_config = WindowConfig(
        title="Pyguara Game",  # Could add title to GameConfig if missing
        screen_width=disp_cfg.screen_width,
        screen_height=disp_cfg.screen_height,
        fullscreen=disp_cfg.fullscreen,
        vsync=disp_cfg.vsync,
        backend=disp_cfg.backend,
    )

    # Select backend based on configuration
    gl_texture_loader = None
    if disp_cfg.backend == RenderingBackend.MODERNGL:
        # ModernGL backend with hardware instancing
        from pyguara.graphics.backends.moderngl import (
            PygameGLWindow,
            ModernGLRenderer,
            GLTextureLoader,
            GLTextureFactory,
            GLUIRenderer,
        )

        gl_window_backend = PygameGLWindow()
        window = Window(win_config, gl_window_backend)
        window.create()
        container.register_instance(Window, window)

        # Get the ModernGL context from the window
        ctx = gl_window_backend.get_screen()

        # World Renderer (GPU-accelerated)
        gl_renderer = ModernGLRenderer(
            ctx, disp_cfg.screen_width, disp_cfg.screen_height
        )
        container.register_instance(IRenderer, gl_renderer)  # type: ignore[type-abstract]

        # UI Renderer (hybrid: pygame surface composited via OpenGL)
        gl_ui_renderer = GLUIRenderer(
            ctx, disp_cfg.screen_width, disp_cfg.screen_height
        )
        container.register_instance(UIRenderer, gl_ui_renderer)  # type: ignore[type-abstract]

        # Texture Factory (for SpriteSheet and other texture creation)
        gl_texture_factory = GLTextureFactory(ctx)
        container.register_instance(TextureFactory, gl_texture_factory)  # type: ignore[type-abstract]

        # Render Pipeline (FBO management and render graph)
        from pyguara.graphics.pipeline.passes import WorldPass, FinalPass

        fbo_manager = FramebufferManager(
            ctx, disp_cfg.screen_width, disp_cfg.screen_height
        )
        container.register_instance(FramebufferManager, fbo_manager)

        render_graph = RenderGraph(ctx, disp_cfg.screen_width, disp_cfg.screen_height)

        # Setup default render passes
        world_pass = WorldPass(gl_renderer)
        final_pass = FinalPass(ctx, input_fbo_name="world")

        render_graph.add_pass(world_pass)
        render_graph.add_pass(final_pass)

        container.register_instance(RenderGraph, render_graph)
        container.register_instance(WorldPass, world_pass)

        # Store texture loader for later registration
        gl_texture_loader = GLTextureLoader(ctx)
    else:
        # Default Pygame backend
        from pyguara.graphics.backends.pygame.types import PygameTextureFactory

        pygame_window_backend = PygameWindow()
        window = Window(win_config, pygame_window_backend)
        window.create()
        container.register_instance(Window, window)

        # World Renderer
        pygame_renderer = PygameBackend(window.native_handle)
        container.register_instance(IRenderer, pygame_renderer)  # type: ignore[type-abstract]

        # UI Renderer
        pygame_ui_renderer = PygameUIRenderer(window.native_handle)
        container.register_instance(UIRenderer, pygame_ui_renderer)  # type: ignore[type-abstract]

        # Texture Factory (for SpriteSheet and other texture creation)
        pygame_texture_factory = PygameTextureFactory()
        container.register_instance(TextureFactory, pygame_texture_factory)  # type: ignore[type-abstract]

    # 5. Core Subsystems
    container.register_singleton(InputManager, InputManager)
    container.register_singleton(SceneManager, SceneManager)
    container.register_singleton(UIManager, UIManager)

    # 5.1 ECS Core
    entity_manager = EntityManager()
    container.register_instance(EntityManager, entity_manager)

    # 5.1.1 Prefab System
    component_registry = get_component_registry()
    _register_core_components(component_registry)
    container.register_instance(ComponentRegistry, component_registry)

    prefab_cache = PrefabCache()
    container.register_instance(PrefabCache, prefab_cache)

    prefab_factory = PrefabFactory(
        entity_manager,
        component_registry,
        prefab_resolver=prefab_cache.load,
    )
    container.register_instance(PrefabFactory, prefab_factory)

    # 5.2 System Manager for orchestrating game systems
    system_manager = SystemManager()
    container.register_instance(SystemManager, system_manager)

    # Register systems with priorities (lower priority = runs first)
    # SteeringSystem priority 150: runs after physics, before AI
    steering_system = SteeringSystem(entity_manager)
    system_manager.register(steering_system, priority=150, system_type=SteeringSystem)
    container.register_instance(SteeringSystem, steering_system)

    # AISystem priority 200: runs after steering
    ai_system = AISystem(entity_manager)
    system_manager.register(ai_system, priority=200, system_type=AISystem)
    container.register_instance(AISystem, ai_system)

    # AnimationSystem priority 300: runs after AI updates
    animation_system = AnimationSystem(entity_manager)
    system_manager.register(animation_system, priority=300, system_type=AnimationSystem)
    container.register_instance(AnimationSystem, animation_system)

    # 5.3 Coroutine Manager for scripted sequences
    coroutine_manager = CoroutineManager()
    container.register_instance(CoroutineManager, coroutine_manager)

    # 6. Audio System
    audio_system = PygameAudioSystem()
    container.register_instance(IAudioSystem, audio_system)  # type: ignore[type-abstract]
    container.register_singleton(AudioManager, AudioManager)

    # 7. Resources & Physics
    res_manager = ResourceManager()
    res_manager.register_loader(JsonLoader())
    res_manager.register_loader(PygameSoundLoader())  # Register audio loader

    # Register appropriate texture loader based on backend
    if gl_texture_loader is not None:
        res_manager.register_loader(gl_texture_loader)
    else:
        from pyguara.graphics.backends.pygame.loaders import PygameImageLoader

        res_manager.register_loader(PygameImageLoader())

    container.register_instance(ResourceManager, res_manager)

    # AudioSourceSystem priority 250: runs after AI, before animation
    audio_source_system = AudioSourceSystem(entity_manager, audio_system, res_manager)
    system_manager.register(
        audio_source_system, priority=250, system_type=AudioSourceSystem
    )
    container.register_instance(AudioSourceSystem, audio_source_system)

    # Physics Engine
    physics_engine = PymunkEngine()
    container.register_instance(IPhysicsEngine, physics_engine)  # type: ignore[type-abstract]

    # Collision System (bridges pymunk callbacks to PyGuara events)
    collision_system = CollisionSystem(event_dispatcher)
    container.register_instance(CollisionSystem, collision_system)

    # Wire collision system to physics engine
    physics_engine.set_collision_system(collision_system)

    # 8. Persistence
    storage = FileStorageBackend(base_path="saves")

    # Migration Manager for schema versioning
    migration_manager = MigrationManager(current_version=1)
    # Register any globally defined migrations
    get_global_registry().register_all(migration_manager)
    container.register_instance(MigrationManager, migration_manager)

    component_registry = ComponentRegistry()
    container.register_instance(ComponentRegistry, component_registry)

    persistence = PersistenceManager(storage, migration_manager)
    container.register_instance(PersistenceManager, persistence)
    container.register_singleton(SceneSerializer, SceneSerializer)

    # Register prefab loader with resource manager
    res_manager.register_loader(PrefabLoader())

    logger.info("Engine bootstrap complete. Handing over to Application.")

    return container


def _register_core_components(registry: ComponentRegistry) -> None:
    """Register core engine components with the component registry.

    Args:
        registry: ComponentRegistry to register components with.
    """
    # Common components
    from pyguara.common.components import Tag, Transform, ResourceLink

    registry.register(Tag)
    registry.register(Transform)
    registry.register(ResourceLink)

    # Physics components
    from pyguara.physics.components import RigidBody, Collider
    from pyguara.physics.joints import Joint
    from pyguara.physics.trigger_volume import TriggerVolume, EntityTags
    from pyguara.physics.platformer_controller import PlatformerController

    registry.register(RigidBody)
    registry.register(Collider)
    registry.register(Joint)
    registry.register(TriggerVolume)
    registry.register(EntityTags)
    registry.register(PlatformerController)

    # AI components
    from pyguara.ai.components import AIComponent, SteeringAgent, Navigator

    registry.register(AIComponent)
    registry.register(SteeringAgent)
    registry.register(Navigator)

    # Animation components
    from pyguara.graphics.components.animation import Animator, AnimationStateMachine

    registry.register(Animator)
    registry.register(AnimationStateMachine)

    # Prefab metadata
    from pyguara.prefabs.types import PrefabInstance

    registry.register(PrefabInstance)

    # Audio components
    from pyguara.audio.components import AudioSource, AudioListener, AudioEmitter

    registry.register(AudioSource)
    registry.register(AudioListener)
    registry.register(AudioEmitter)
