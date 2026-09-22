"""Quintal do Cerrado - Bootstrap.

Runs on the **ModernGL** backend, since the fun-improvement roadmap's
Phase 5 asked for the soil and the weather to actually look like they
were affecting a living plot, not a sterile grid of flat colours -- and
that meant a shader pass, which the plain pygame backend cannot give.

The graph assembled here is deliberately smaller than the other ModernGL
demos' (`true_coral`, `protocolo_bandeira`, `mourisco_ressonancia`), which
all run a full `WorldPass -> LightPass -> CompositePass -> PostProcessPass
-> FinalPass` chain for dynamic lighting this game does not need -- the
plot is lit flat, head-on, all the time. This one skips straight from the
world to post-processing::

    WorldPass       -- the scene draws the plot into the "world" FBO
    PostProcessPass -- the soil-health grade, then rain, then a vignette
    FinalPass       -- blit to the screen

Order inside the post stack: soil health grades the frame's base colours
first, so rain and the vignette are drawn over an already-graded scene
rather than under it, the same way the other demos' vignette always runs
last, over everything, because it is a lens, not part of the world.

`IPhysicsEngine`/`CollisionSystem`/`Camera2D` are still not registered:
`Scene.resolve_dependencies()` (`pyguara/scene/base.py`) does not require
physics to be wired, and this game has no falling body and no scrolling
world for a camera to follow. The grid itself no longer needs a camera to
draw through the world pass either -- `garden_widget.py`'s
`GardenGridCanvas.render_world()` draws in the same raw screen-pixel
coordinates `IRenderer`'s primitives always have (see its own module
docstring): there is no world/screen transform to get right, because
there never was one to begin with.

`PersistenceManager` is wired the way `pyguara/application/bootstrap.py`'s
own reference wiring does it -- a `FileStorageBackend` plus a
`MigrationManager` at the schema's version -- and, unlike there, is actually
used: `scenes.GardenScene` saves and loads through it (see
`persistence_schema.py`). `FileStorageBackend.base_path` is CWD-relative, not an OS user-data
directory (a known engine gap, tracked as issue #43) -- fine for a demo
run from the repo root via `uv run python -m games.quintal_cerrado.main`,
but not a real per-user save location.
"""

from __future__ import annotations

from games.quintal_cerrado.persistence_schema import SCHEMA_VERSION
from games.quintal_cerrado.soil_health_effect import SoilHealthEffect
from pyguara.application.application import Application
from pyguara.application.clock import Clock
from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.backends.pygame.loaders import PygameSoundLoader
from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem
from pyguara.audio.manager import AudioManager
from pyguara.config.manager import ConfigManager
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.backends.moderngl import (
    GLTextureFactory,
    GLUIRenderer,
    ModernGLRenderer,
    PygameGLWindow,
)
from pyguara.graphics.backends.pygame.clock import PygameClock
from pyguara.graphics.pipeline.framebuffer import FramebufferManager
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.pipeline.passes import FinalPass, PostProcessPass, WorldPass
from pyguara.graphics.protocols import IRenderer, TextureFactory, UIRenderer
from pyguara.graphics.vfx.effects.storm import StormEffect
from pyguara.graphics.vfx.effects.vignette import VignetteEffect
from pyguara.graphics.vfx.post_process import PostProcessStack
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

# A mild, permanent frame -- the same reason every other ModernGL demo in
# this repo runs one -- strengthened a little (not swapped for a
# different effect) when `WeatherState.cold_snap` is true, so a cold
# snap reads as a colder, tighter frame rather than a different filter
# appearing out of nowhere. See `scenes.py`'s per-frame effect wiring.
BASE_VIGNETTE_INTENSITY = 0.28
BASE_VIGNETTE_RADIUS = 0.85
COLD_SNAP_VIGNETTE_INTENSITY = 0.5


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
    gl_window = PygameGLWindow()
    window = Window(win_config, gl_window)
    window.create()
    container.register_instance(Window, window)

    ctx = gl_window.get_screen()

    renderer = ModernGLRenderer(ctx, WINDOW_WIDTH, WINDOW_HEIGHT)
    container.register_instance(IRenderer, renderer)  # type: ignore[type-abstract]
    ui_renderer = GLUIRenderer(ctx, WINDOW_WIDTH, WINDOW_HEIGHT)
    container.register_instance(UIRenderer, ui_renderer)  # type: ignore[type-abstract]
    container.register_instance(TextureFactory, GLTextureFactory(ctx))  # type: ignore[type-abstract]

    render_graph = RenderGraph(ctx, WINDOW_WIDTH, WINDOW_HEIGHT)
    fbo_manager = render_graph.fbo_manager
    container.register_instance(FramebufferManager, fbo_manager)

    soil_health_effect = SoilHealthEffect(ctx)
    storm = StormEffect(ctx)
    vignette = VignetteEffect(
        ctx, intensity=BASE_VIGNETTE_INTENSITY, radius=BASE_VIGNETTE_RADIUS
    )
    stack = PostProcessStack(ctx, fbo_manager)
    stack.add_effect(soil_health_effect)
    stack.add_effect(storm)
    stack.add_effect(vignette)

    render_graph.add_pass(WorldPass(renderer))
    render_graph.add_pass(PostProcessPass(stack, input_fbo_name="world"))
    render_graph.add_pass(FinalPass(ctx, input_fbo_name="post_processed"))

    container.register_instance(RenderGraph, render_graph)
    container.register_instance(SoilHealthEffect, soil_health_effect)
    container.register_instance(StormEffect, storm)
    container.register_instance(VignetteEffect, vignette)

    container.register_instance(Clock, PygameClock())  # type: ignore[type-abstract]
    container.register_instance(IInputBackend, PygameInputBackend())  # type: ignore[type-abstract]
    container.register_singleton(InputManager, InputManager)
    container.register_instance(IAudioSystem, PygameAudioSystem())  # type: ignore[type-abstract]
    container.register_singleton(AudioManager, AudioManager)
    container.register_instance(ComponentRegistry, get_component_registry())
    container.register_instance(PrefabCache, PrefabCache())
    container.register_singleton(SceneManager, SceneManager)

    res_manager = ResourceManager()
    res_manager.register_loader(PygameSoundLoader())
    container.register_instance(ResourceManager, res_manager)

    container.register_singleton(UIManager, UIManager)
    set_theme(cerrado_dusk())
    container.register_singleton(SystemManager, SystemManager)
    container.register_singleton(CoroutineManager, CoroutineManager)

    storage = FileStorageBackend(base_path=SAVE_DIRECTORY)
    migration_manager = MigrationManager(current_version=SCHEMA_VERSION)
    persistence = PersistenceManager(storage, migration_manager)
    container.register_instance(PersistenceManager, persistence)

    container.register_singleton(Application, Application)

    return container
