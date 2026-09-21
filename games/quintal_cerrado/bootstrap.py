"""Quintal do Cerrado - Bootstrap.

Runs on the plain pygame backend, not ModernGL -- the plot is a static
12x8 grid drawn head-on through the UI system (see `garden_widget.py`), so
there is nothing here that needs lighting, bloom or a shader pass.

No `IPhysicsEngine`/`CollisionSystem`/`Camera2D` are registered either:
`Scene.resolve_dependencies()` (`pyguara/scene/base.py`) does not require
physics to be wired, and this game has no falling body and no scrolling
world for a camera to follow -- both are scope this demo genuinely does
not need, not omissions.

`PersistenceManager` is wired here even though Phase 1 does not call it
yet, mirroring `pyguara/application/bootstrap.py`'s own reference wiring
-- which, notably, no other capstone actually exercises for real gameplay.
`FileStorageBackend.base_path` is CWD-relative, not an OS user-data
directory (a known engine gap, tracked as issue #43) -- fine for a demo
run from the repo root via `uv run python -m games.quintal_cerrado.main`,
but not a real per-user save location.
"""

from __future__ import annotations

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
from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.migration import MigrationManager
from pyguara.persistence.storage import FileStorageBackend
from pyguara.prefabs.loader import PrefabCache
from pyguara.prefabs.registry import ComponentRegistry, get_component_registry
from pyguara.resources.manager import ResourceManager
from pyguara.scene.manager import SceneManager
from pyguara.scripting.coroutines import CoroutineManager
from pyguara.systems.manager import SystemManager
from pyguara.ui.design_system import cerrado_dusk
from pyguara.ui.manager import UIManager
from pyguara.ui.theme import set_theme

WINDOW_WIDTH = 960
WINDOW_HEIGHT = 640

SAVE_DIRECTORY = "saves/quintal_cerrado"
SAVE_SCHEMA_VERSION = 1


def configure_game_container() -> DIContainer:
    """Initialize and configure the DI container for Quintal do Cerrado."""
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
        title="Quintal do Cerrado",
        screen_width=WINDOW_WIDTH,
        screen_height=WINDOW_HEIGHT,
    )
    window_backend = PygameWindow()
    window = Window(win_config, window_backend)
    window.create()
    container.register_instance(Window, window)

    renderer = PygameBackend(window.native_handle)
    container.register_instance(IRenderer, renderer)  # type: ignore[type-abstract]

    ui_renderer = PygameUIRenderer(window.native_handle)
    container.register_instance(UIRenderer, ui_renderer)  # type: ignore[type-abstract]

    container.register_instance(Clock, PygameClock())  # type: ignore[type-abstract]
    container.register_instance(IInputBackend, PygameInputBackend())  # type: ignore[type-abstract]
    container.register_singleton(InputManager, InputManager)
    container.register_instance(IAudioSystem, PygameAudioSystem())  # type: ignore[type-abstract]
    container.register_instance(ComponentRegistry, get_component_registry())
    container.register_instance(PrefabCache, PrefabCache())
    container.register_singleton(SceneManager, SceneManager)
    container.register_singleton(ResourceManager, ResourceManager)
    container.register_singleton(UIManager, UIManager)
    set_theme(cerrado_dusk())
    container.register_singleton(SystemManager, SystemManager)
    container.register_singleton(CoroutineManager, CoroutineManager)

    storage = FileStorageBackend(base_path=SAVE_DIRECTORY)
    migration_manager = MigrationManager(current_version=SAVE_SCHEMA_VERSION)
    persistence = PersistenceManager(storage, migration_manager)
    container.register_instance(PersistenceManager, persistence)

    container.register_singleton(Application, Application)

    return container
