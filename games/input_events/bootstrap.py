"""Module 4: Bootstrap.

Standard DI setup.
"""

from pyguara.application.application import Application
from pyguara.application.clock import Clock
from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem
from pyguara.config.manager import ConfigManager
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.backends.pygame.clock import PygameClock
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.graphics.backends.pygame.pygame_window import PygameWindow
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.graphics.window import Window, WindowConfig
from pyguara.input.backends.pygame_backend import PygameInputBackend
from pyguara.input.manager import InputManager
from pyguara.input.protocols import IInputBackend
from pyguara.log.manager import LogManager
from pyguara.log.types import LogLevel
from pyguara.prefabs.loader import PrefabCache
from pyguara.prefabs.registry import ComponentRegistry, get_component_registry
from pyguara.resources.manager import ResourceManager
from pyguara.scene.manager import SceneManager
from pyguara.scripting.coroutines import CoroutineManager
from pyguara.systems.manager import SystemManager
from pyguara.ui.manager import UIManager


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
        title="Module 4: Input & Events", screen_width=800, screen_height=600
    )
    window_backend = PygameWindow()
    window = Window(win_config, window_backend)
    window.create()
    container.register_instance(Window, window)

    renderer = PygameBackend(window.native_handle)
    container.register_instance(IRenderer, renderer)

    ui_renderer = PygameUIRenderer(window.native_handle)
    container.register_instance(UIRenderer, ui_renderer)

    container.register_instance(Clock, PygameClock())  # type: ignore[type-abstract]
    container.register_instance(IInputBackend, PygameInputBackend())  # type: ignore[type-abstract]
    container.register_singleton(InputManager, InputManager)
    container.register_instance(IAudioSystem, PygameAudioSystem())  # type: ignore[type-abstract]
    container.register_instance(ComponentRegistry, get_component_registry())
    container.register_instance(PrefabCache, PrefabCache())
    container.register_singleton(SceneManager, SceneManager)
    container.register_singleton(ResourceManager, ResourceManager)
    container.register_singleton(UIManager, UIManager)
    container.register_singleton(SystemManager, SystemManager)
    container.register_singleton(CoroutineManager, CoroutineManager)
    container.register_singleton(Application, Application)

    return container
