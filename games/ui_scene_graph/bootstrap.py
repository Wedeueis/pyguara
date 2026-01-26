"""Module 6: UI Bootstrap."""

from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.config.manager import ConfigManager
from pyguara.log.manager import LogManager
from pyguara.log.types import LogLevel
from pyguara.graphics.window import Window, WindowConfig
from pyguara.graphics.backends.pygame.pygame_window import PygameWindow
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.manager import InputManager
from pyguara.scene.manager import SceneManager
from pyguara.resources.manager import ResourceManager
from pyguara.ui.manager import UIManager
from pyguara.systems.manager import SystemManager
from pyguara.scripting.coroutines import CoroutineManager
from pyguara.application.application import Application


def configure_game_container() -> DIContainer:
    """Initialize and configure the DI container."""
    container = DIContainer()
    container.register_instance(DIContainer, container)

    event_dispatcher = EventDispatcher()
    container.register_instance(EventDispatcher, event_dispatcher)

    config_manager = ConfigManager(event_dispatcher)
    config_manager.load()
    container.register_instance(ConfigManager, config_manager)

    log_manager = LogManager(event_dispatcher)
    log_manager.configure(level=LogLevel.INFO, console=True)
    container.register_instance(LogManager, log_manager)

    win_config = WindowConfig(
        title="Module 6: UI & Scene Graph", screen_width=800, screen_height=600
    )
    window_backend = PygameWindow()
    window = Window(win_config, window_backend)
    window.create()
    container.register_instance(Window, window)

    renderer = PygameBackend(window.native_handle)
    container.register_instance(IRenderer, renderer)

    ui_renderer = PygameUIRenderer(window.native_handle)
    container.register_instance(UIRenderer, ui_renderer)

    container.register_singleton(InputManager, InputManager)
    container.register_singleton(SceneManager, SceneManager)
    container.register_singleton(ResourceManager, ResourceManager)
    container.register_singleton(UIManager, UIManager)
    container.register_singleton(SystemManager, SystemManager)
    container.register_singleton(CoroutineManager, CoroutineManager)
    container.register_singleton(Application, Application)

    return container
