"""Application setup and dependency wiring."""

from pyguara.application.application import Application
from pyguara.config.manager import ConfigManager
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.backends.pygame.pygame_window import PygameWindow
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.graphics.protocols import UIRenderer, IRenderer
from pyguara.graphics.window import Window, WindowConfig
from pyguara.input.manager import InputManager
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.collision_system import CollisionSystem
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.resources.loaders.data_loader import JsonLoader
from pyguara.resources.manager import ResourceManager
from pyguara.scene.manager import SceneManager
from pyguara.scene.serializer import SceneSerializer
from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.storage import FileStorageBackend
from pyguara.ui.manager import UIManager
from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem
from pyguara.audio.backends.pygame.loaders import PygameSoundLoader
from pyguara.audio.manager import AudioManager
from pyguara.graphics.animation_system import AnimationSystem
from .sandbox import SandboxApplication


def create_application() -> Application:
    """
    Construct and configure the Application instance.

    This factory function handles the Dependency Injection wiring:
    1. Creates the container.
    2. Loads configuration.
    3. Initializes the Window based on config.
    4. Registers all core subsystems (Input, Physics, UI, Resources).

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
    container = DIContainer()

    # 1. Event System (Core)
    event_dispatcher = EventDispatcher()
    container.register_instance(EventDispatcher, event_dispatcher)

    # 2. Configuration
    config_manager = ConfigManager(event_dispatcher=event_dispatcher)
    config_manager.load()  # Loads from disk or defaults
    container.register_instance(ConfigManager, config_manager)

    # 3. Window System
    # Extract settings from loaded config
    disp_cfg = config_manager.config.display

    win_config = WindowConfig(
        title="Pyguara Game",  # Could add title to GameConfig if missing
        screen_width=disp_cfg.screen_width,
        screen_height=disp_cfg.screen_height,
        fullscreen=disp_cfg.fullscreen,
        vsync=disp_cfg.vsync,
    )

    # We use the existing Window composition pattern
    pygame_backend = PygameWindow()
    window = Window(win_config, pygame_backend)
    window.create()
    container.register_instance(Window, window)

    # 4. Rendering
    # World Renderer
    world_renderer = PygameBackend(window.native_handle)
    container.register_instance(IRenderer, world_renderer)  # type: ignore[type-abstract]

    # UI Renderer
    ui_renderer = PygameUIRenderer(window.native_handle)
    container.register_instance(UIRenderer, ui_renderer)  # type: ignore[type-abstract]

    # 5. Core Subsystems
    container.register_singleton(InputManager, InputManager)
    container.register_singleton(SceneManager, SceneManager)
    container.register_singleton(UIManager, UIManager)
    container.register_singleton(AnimationSystem, AnimationSystem)

    # 6. Audio System
    audio_system = PygameAudioSystem()
    container.register_instance(IAudioSystem, audio_system)  # type: ignore[type-abstract]
    container.register_singleton(AudioManager, AudioManager)

    # 7. Resources & Physics
    res_manager = ResourceManager()
    res_manager.register_loader(JsonLoader())
    res_manager.register_loader(PygameSoundLoader())  # Register audio loader
    container.register_instance(ResourceManager, res_manager)

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
    persistence = PersistenceManager(storage)
    container.register_instance(PersistenceManager, persistence)
    container.register_singleton(SceneSerializer, SceneSerializer)

    return container
