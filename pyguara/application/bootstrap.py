"""Application setup and dependency wiring."""

from pyguara.application.application import Application
from pyguara.config.manager import ConfigManager
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.backends.pygame.pygame_window import PygameWindow
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.graphics.protocols import UIRenderer
from pyguara.graphics.window import Window, WindowConfig
from pyguara.input.manager import InputManager
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.resources.loaders.data_loader import JsonLoader
from pyguara.resources.manager import ResourceManager
from pyguara.scene.manager import SceneManager
from pyguara.ui.manager import UIManager


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

    # 4. Rendering (UI)
    # We register the concrete renderer bound to the window surface
    ui_renderer = PygameUIRenderer(window.native_handle)
    container.register_instance(UIRenderer, ui_renderer)  # type: ignore[type-abstract]

    # 5. Core Subsystems
    container.register_singleton(InputManager, InputManager)
    container.register_singleton(SceneManager, SceneManager)
    container.register_singleton(UIManager, UIManager)

    # 6. Resources & Physics
    res_manager = ResourceManager()
    res_manager.register_loader(JsonLoader())
    container.register_instance(ResourceManager, res_manager)

    container.register_singleton(IPhysicsEngine, PymunkEngine)  # type: ignore[type-abstract]

    # 7. Create Application
    return Application(container)
