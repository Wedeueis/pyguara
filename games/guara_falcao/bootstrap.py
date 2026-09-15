"""Guará & Falcão - Bootstrap.

Runs on the **ModernGL** backend. The demo's subject is the UI system and
the design system, and neither needs a GPU -- but the screens they draw sit
over a Cerrado at the amber hour, and that does: the low sun, the glow off
the fruit, and the way a checkpoint lifts the ground around it are light-map
and bloom, not draw calls.

The graph assembled here is::

    WorldPass      -- the scene draws the cerrado into the "world" FBO
    LightPass      -- the sun, the fruit, the checkpoints (attached per scene)
    CompositePass  -- world * lightmap -> "composite"
    PostProcessPass-- bloom, then a vignette
    FinalPass      -- blit to the screen

The UI composites *after* the final blit, which is the right way round for
this demo: a HUD that bloomed would smear its own numbers, and a pause
scrim that the vignette darkened again would be twice as heavy at the
corners as the middle. The menus are meant to read as drawn on the glass,
not as part of the world behind it.
"""

from __future__ import annotations

from pyguara.application.application import Application
from pyguara.application.clock import Clock
from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem
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
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.lighting.light_system import LightingSystem
from pyguara.graphics.pipeline.framebuffer import FramebufferManager
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.pipeline.passes import (
    CompositePass,
    FinalPass,
    LightPass,
    PostProcessPass,
    WorldPass,
)
from pyguara.graphics.protocols import IRenderer, TextureFactory, UIRenderer
from pyguara.graphics.vfx.effects.bloom import BloomEffect
from pyguara.graphics.vfx.effects.vignette import VignetteEffect
from pyguara.graphics.vfx.post_process import PostProcessStack
from pyguara.graphics.window import Window, WindowConfig
from pyguara.input.backends.pygame_backend import PygameInputBackend
from pyguara.input.manager import InputManager
from pyguara.input.protocols import IInputBackend
from pyguara.log.manager import LogManager
from pyguara.log.types import LogLevel
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.collision_system import CollisionSystem
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.prefabs.loader import PrefabCache
from pyguara.prefabs.registry import ComponentRegistry, get_component_registry
from pyguara.resources.manager import ResourceManager
from pyguara.scene.manager import SceneManager
from pyguara.scripting.coroutines import CoroutineManager
from pyguara.systems.manager import SystemManager
from pyguara.ui.design_system import cerrado_dusk
from pyguara.ui.manager import UIManager
from pyguara.ui.theme import set_theme

WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
"""16:9, which is what the menu layouts were drawn against."""

# High threshold, gentle intensity: the sun disc is meant to bloom and
# almost nothing else is. The amber hour puts most of the frame in the
# 0.8-0.9 range, so a lower threshold blooms the *sky* and the whole image
# goes to haze -- which is exactly what the first pass at this looked like.
BLOOM_THRESHOLD = 0.9
BLOOM_INTENSITY = 0.42
BLOOM_BLUR_PASSES = 3


def _install_theme() -> None:
    """Skin every UI element with the design system's dark Cerrado theme.

    One call, and the title screen, the HUD, the pause menu and the options
    panel are all in the brand's colours -- the stock components read the
    same semantic roles the theme fills in. The options screen can swap it
    for `cerrado_day()` at runtime and everything on screen follows.
    """
    set_theme(cerrado_dusk())


def attach_lighting(container: DIContainer, lighting: LightingSystem) -> None:
    """Point the light pass at a scene's own `LightingSystem`.

    `LightPass` needs a `LightingSystem`, which needs an `EntityManager`,
    which is per-scene -- so the pass cannot be built alongside the rest of
    the graph. Each scene calls this as it enters, and the previous pass is
    dropped first: re-entering a scene builds a fresh world, and the old
    pass would go on reading the dead one's entities.

    Args:
        container: The game's DI container.
        lighting: The entering scene's lighting system.
    """
    graph = container.get(RenderGraph)
    if graph.get_pass("light") is not None:
        graph.remove_pass("light")

    # Index 1: after the world is drawn, before it is composited with the
    # light map it is about to be multiplied by.
    graph.insert_pass(1, LightPass(graph.ctx, lighting))


def begin_world(container: DIContainer) -> None:
    """Re-bind the world buffer before a scene draws into it.

    `Application` binds it once per frame, but a render pass leaves *its*
    own output bound when it finishes -- so once any scene has run the
    pipeline, the next scene's shapes would land in the composite buffer
    instead of the world. That failure is invisible: the frame still
    renders, it just renders the scene underneath.

    Args:
        container: The game's DI container.
    """
    container.get(RenderGraph).fbo_manager.get_or_create("world").bind()


def run_pipeline(container: DIContainer, camera: Camera2D) -> None:
    """Execute light -> composite -> post-process for this frame.

    `Application` binds the world buffer, lets the scene draw into it, and
    then runs only the graph's `final` pass -- so everything between the
    world buffer and the screen happens here, at the end of a scene's
    `render()`. Both scenes that draw a world call it.

    Args:
        container: The game's DI container.
        camera: The scene's camera, so the light map lines up with the
            geometry the scene just drew.
    """
    graph = container.get(RenderGraph)
    for name in ("light", "composite", "post_process"):
        render_pass = graph.get_pass(name)
        if render_pass is None:
            continue
        if name == "light":
            render_pass.set_camera(camera)
        render_pass.execute(graph.ctx, graph)


def configure_game_container() -> DIContainer:
    """Initialize and configure the DI container for Guará & Falcão."""
    container = DIContainer()
    container.register_instance(DIContainer, container)

    # Event System
    event_dispatcher = EventDispatcher()
    container.register_instance(EventDispatcher, event_dispatcher)

    # Configuration & Logging
    config_manager = ConfigManager(event_dispatcher)
    config_manager.load()
    # Platformer gravity — set here rather than in the shared config file, since
    # config/game_config.json is shared across every demo's default load path.
    config_manager.config.physics.gravity_y = 800.0
    container.register_instance(ConfigManager, config_manager)

    log_manager = LogManager(event_dispatcher)
    log_manager.configure(level=LogLevel.INFO, console=True)
    container.register_instance(LogManager, log_manager)

    # Window & Graphics
    win_config = WindowConfig(
        title="Guará & Falcão - A Platformer Adventure",
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
    container.register_instance(  # type: ignore[type-abstract]
        UIRenderer, GLUIRenderer(ctx, WINDOW_WIDTH, WINDOW_HEIGHT)
    )
    container.register_instance(TextureFactory, GLTextureFactory(ctx))  # type: ignore[type-abstract]

    render_graph = RenderGraph(ctx, WINDOW_WIDTH, WINDOW_HEIGHT)

    # The graph builds its own framebuffer manager, and the passes resolve
    # every buffer through that one. Anything else built here -- the bloom
    # effect, the post-process stack -- has to share it, or it allocates a
    # second, parallel set of buffers that the graph never looks at.
    fbo_manager = render_graph.fbo_manager
    container.register_instance(FramebufferManager, fbo_manager)

    stack = PostProcessStack(ctx, fbo_manager)
    bloom = BloomEffect(
        ctx,
        fbo_manager,
        threshold=BLOOM_THRESHOLD,
        intensity=BLOOM_INTENSITY,
        blur_passes=BLOOM_BLUR_PASSES,
    )
    stack.add_effect(bloom)
    # Last, and gently: a vignette is a lens, not a light, and this one is
    # only here to stop the bright sky pulling the eye to the corners.
    stack.add_effect(VignetteEffect(ctx, intensity=0.38, radius=0.92, softness=0.6))

    render_graph.add_pass(WorldPass(renderer))
    render_graph.add_pass(CompositePass(ctx))
    render_graph.add_pass(PostProcessPass(stack, input_fbo_name="composite"))
    render_graph.add_pass(FinalPass(ctx, input_fbo_name="post_processed"))

    container.register_instance(RenderGraph, render_graph)
    # Registered so the options panel can switch it off in front of you --
    # a toggle that changes the frame is worth more in a showcase than one
    # that sets a flag nothing reads.
    container.register_instance(BloomEffect, bloom)

    # Core Systems
    container.register_instance(Clock, PygameClock())  # type: ignore[type-abstract]
    container.register_instance(IInputBackend, PygameInputBackend())  # type: ignore[type-abstract]
    container.register_singleton(InputManager, InputManager)
    container.register_instance(IAudioSystem, PygameAudioSystem())  # type: ignore[type-abstract]
    container.register_instance(ComponentRegistry, get_component_registry())
    container.register_instance(PrefabCache, PrefabCache())
    container.register_singleton(SceneManager, SceneManager)
    container.register_singleton(ResourceManager, ResourceManager)
    container.register_singleton(UIManager, UIManager)
    _install_theme()
    container.register_singleton(SystemManager, SystemManager)
    container.register_singleton(CoroutineManager, CoroutineManager)

    # Physics
    physics_engine = PymunkEngine()
    container.register_instance(IPhysicsEngine, physics_engine)

    collision_system = CollisionSystem(event_dispatcher)
    container.register_instance(CollisionSystem, collision_system)

    physics_engine.set_collision_system(collision_system)

    # Application
    container.register_singleton(Application, Application)

    return container
