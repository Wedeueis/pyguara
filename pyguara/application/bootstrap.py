"""Application setup and dependency wiring."""

from pyguara.application.application import Application
from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.backends.pygame.loaders import PygameSoundLoader
from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem
from pyguara.audio.manager import AudioManager
from pyguara.config.manager import ConfigManager
from pyguara.config.types import RenderingBackend
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.graphics.backends.pygame.pygame_window import PygameWindow
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.graphics.pipeline.framebuffer import FramebufferManager
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.protocols import IRenderer, TextureFactory, UIRenderer
from pyguara.graphics.window import Window
from pyguara.input.backends.pygame_backend import PygameInputBackend
from pyguara.input.manager import InputManager
from pyguara.input.protocols import IInputBackend
from pyguara.log import LogManager, default_log_manager
from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.migration import MigrationManager, get_global_registry
from pyguara.persistence.storage import FileStorageBackend
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.collision_system import CollisionSystem
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.prefabs.loader import PrefabCache, PrefabLoader
from pyguara.prefabs.registry import ComponentRegistry, get_component_registry
from pyguara.resources.loaders.data_loader import JsonLoader
from pyguara.resources.manager import ResourceManager
from pyguara.scene.manager import SceneManager
from pyguara.scene.serializer import SceneSerializer
from pyguara.scripting.coroutines import CoroutineManager
from pyguara.ui.manager import UIManager

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


def create_headless_application() -> Application:
    """Construct an Application wired onto the headless graphics backend.

    Test-only entry point: swaps the window/renderer/UI-renderer/texture-
    factory quartet for their no-op `pyguara.graphics.backends.
    headless_renderer` equivalents, which never touch `pygame.display` (or
    any other SDL video call). Everything else -- ECS, physics, audio,
    persistence -- wires up exactly as `create_application()` does.

    Not a third shipped rendering backend (the engine still ships pygame and
    ModernGL only) -- this exists so the integration suite can boot a real
    `Application` without an SDL video driver, dummy or otherwise.
    """
    container = _setup_container(headless=True)
    return Application(container)


def create_headless_sandbox_application() -> SandboxApplication:
    """Construct a SandboxApplication wired onto the headless graphics backend.

    Test-only entry point; see `create_headless_application()`.
    """
    container = _setup_container(headless=True)
    return SandboxApplication(container)


def _setup_container(headless: bool = False) -> DIContainer:
    """Configure common dependencies internally.

    Args:
        headless: Test-only override. When True, wires the no-op headless
            window/renderer/UI-renderer/texture-factory quartet instead of
            whatever `config.display.backend` says, regardless of its value.
            See `create_headless_application()`.
    """
    # 1. Event System (Core)
    event_dispatcher = EventDispatcher()

    # 2. Configuration System
    config_manager = ConfigManager(event_dispatcher=event_dispatcher)
    config_manager.load()  # Loads from disk or defaults

    # 3. Logging System
    debug_cfg = config_manager.config.debug
    log_manager = default_log_manager
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

    win_config = disp_cfg

    # Select backend based on configuration
    gl_texture_loader = None
    if headless:
        from pyguara.graphics.backends.headless_renderer import (
            HeadlessBackend,
            HeadlessTextureFactory,
            HeadlessUIRenderer,
            HeadlessWindowBackend,
        )

        # Nothing renders, so real-time frame pacing only slows the test down:
        # Clock.tick(0) (see Application.run()) skips its sleep entirely.
        disp_cfg.fps_target = 0

        headless_window_backend = HeadlessWindowBackend()
        window = Window(win_config, headless_window_backend)
        window.create()
        container.register_instance(Window, window)

        headless_renderer = HeadlessBackend(
            disp_cfg.screen_width, disp_cfg.screen_height
        )
        container.register_instance(IRenderer, headless_renderer)  # type: ignore[type-abstract]

        headless_ui_renderer = HeadlessUIRenderer()
        container.register_instance(UIRenderer, headless_ui_renderer)  # type: ignore[type-abstract]

        headless_texture_factory = HeadlessTextureFactory()
        container.register_instance(TextureFactory, headless_texture_factory)  # type: ignore[type-abstract]

        # No RenderGraph registered: Application's lookup gracefully falls
        # back to `_render_direct()` when the container has none at all,
        # which is exactly the single-pass path a headless test wants.
    elif disp_cfg.backend == RenderingBackend.MODERNGL:
        # ModernGL backend with hardware instancing
        from pyguara.graphics.backends.moderngl import (
            GLTextureFactory,
            GLTextureLoader,
            GLUIRenderer,
            ModernGLRenderer,
            PygameGLWindow,
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
        from pyguara.graphics.pipeline.passes import FinalPass, WorldPass

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
        from pyguara.graphics.backends.pygame.stubs import PygameRenderGraph
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

        # Stub implementations for advanced features (graceful degradation)
        # These allow game code using lighting/post-processing to run on Pygame
        pygame_render_graph = PygameRenderGraph(
            disp_cfg.screen_width, disp_cfg.screen_height
        )
        container.register_instance(RenderGraph, pygame_render_graph)

    # 5. Core Subsystems
    container.register_instance(IInputBackend, PygameInputBackend())  # type: ignore[type-abstract]
    container.register_singleton(InputManager, InputManager)
    container.register_singleton(SceneManager, SceneManager)
    container.register_singleton(UIManager, UIManager)

    # 5.1 Prefab System (ComponentRegistry/PrefabCache are shared, static
    # metadata; PrefabFactory itself is per-scene -- built in
    # Scene.resolve_dependencies() against that scene's own EntityManager.
    # There's no global EntityManager/SystemManager to bind one to here: each
    # scene owns its own world (see Scene-owned world and SystemManager).
    component_registry = get_component_registry()
    _register_core_components(component_registry)
    container.register_instance(ComponentRegistry, component_registry)

    prefab_cache = PrefabCache()
    container.register_instance(PrefabCache, prefab_cache)

    # 5.2 Coroutine Manager for scripted sequences
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

    # Register appropriate texture loader based on backend. Headless registers
    # none: nothing exercises image loading under it today, and the real
    # PygameImageLoader documents needing pygame.display initialized for some
    # formats -- exactly the SDL video coupling headless mode exists to avoid.
    if gl_texture_loader is not None:
        res_manager.register_loader(gl_texture_loader)
    elif not headless:
        from pyguara.graphics.backends.pygame.loaders import PygameImageLoader

        res_manager.register_loader(PygameImageLoader())

    container.register_instance(ResourceManager, res_manager)

    # Physics Engine
    physics_config = config_manager.config.physics
    physics_engine = PymunkEngine(
        substeps=physics_config.substeps,
        penetration_recovery=physics_config.penetration_recovery,
        sleep_time_threshold=physics_config.sleep_time_threshold,
    )
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
    from pyguara.common.components import ResourceLink, Tag, Transform

    registry.register(Tag)
    registry.register(Transform)
    registry.register(ResourceLink)

    # Physics components
    from pyguara.physics.components import Collider, RigidBody
    from pyguara.physics.joints import Joint
    from pyguara.physics.platformer_controller import PlatformerController
    from pyguara.physics.trigger_volume import EntityTags, TriggerVolume

    registry.register(RigidBody)
    registry.register(Collider)
    registry.register(Joint)
    registry.register(TriggerVolume)
    registry.register(EntityTags)
    registry.register(PlatformerController)

    # AI components
    from pyguara.ai.components import AIComponent, Navigator, SteeringAgent

    registry.register(AIComponent)
    registry.register(SteeringAgent)
    registry.register(Navigator)

    # Animation components
    from pyguara.graphics.components.animation import AnimationStateMachine, Animator

    registry.register(Animator)
    registry.register(AnimationStateMachine)

    # Prefab metadata
    from pyguara.prefabs.types import PrefabInstance

    registry.register(PrefabInstance)

    # Audio components
    from pyguara.audio.components import AudioEmitter, AudioListener, AudioSource

    registry.register(AudioSource)
    registry.register(AudioListener)
    registry.register(AudioEmitter)
