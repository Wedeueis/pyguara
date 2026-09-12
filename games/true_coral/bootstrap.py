"""True Coral - Bootstrap.

Runs on the **ModernGL** backend, for the same reason Mourisco does: the
demo's look is not something a blitter can produce. The forest floor is
dark except where something glows on it, the glow is a bloom threshold,
and the weather is a fragment shader -- all three are pipeline features,
not draw calls.

The graph assembled here is::

    WorldPass      -- the scene draws the arena into the "world" FBO
    LightPass      -- fungi, prey and the snake's head light the arena
    CompositePass  -- world * lightmap -> "composite"
    PostProcessPass-- bloom, then the storm, then a vignette
    FinalPass      -- blit to the screen

Order inside the post stack is the part worth defending. Bloom runs first,
so it bleeds the scene's own hot colours and not the rain. The storm runs
on the bloomed image, so its bolt is a crisp discharge over a soft frame
rather than a smear. The vignette runs last, over everything, because it
is a lens, not a light.
"""

from __future__ import annotations

from pyguara.application.application import Application
from pyguara.application.clock import Clock
from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem
from pyguara.common.types import Color
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
from pyguara.graphics.pipeline.passes.light_pass import LIGHT_FBO_NAME
from pyguara.graphics.protocols import IRenderer, TextureFactory, UIRenderer
from pyguara.graphics.vfx.effects.bloom import BloomEffect
from pyguara.graphics.vfx.effects.storm import StormEffect
from pyguara.graphics.vfx.effects.vignette import VignetteEffect
from pyguara.graphics.vfx.post_process import PostProcessStack
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
from pyguara.ui.theme import UITheme, set_theme
from pyguara.ui.types import ColorScheme

WINDOW_WIDTH = 960
WINDOW_HEIGHT = 720

# Low enough that the snake's red cores and the fungi bleed, high enough
# that the leaf litter never does -- the litter is meant to be the dark
# the rest glows against.
BLOOM_THRESHOLD = 0.74
BLOOM_INTENSITY = 0.85
BLOOM_BLUR_PASSES = 3


def _install_theme() -> None:
    """Dress the UI widgets in the game's palette.

    The UI is drawn after the final blit, so it picks up no bloom and no
    rain -- which makes the default blue-on-grey widget theme read as a
    different application sitting on top of the game. These colours are
    the arena's own.
    """
    set_theme(
        UITheme(
            colors=ColorScheme(
                primary=Color(16, 26, 27),
                secondary=Color(30, 58, 58),
                background=Color(10, 14, 14),
                text=Color(240, 234, 214),
                border=Color(90, 226, 214),
            )
        )
    )


def configure_game_container() -> DIContainer:
    """Initialize and configure the DI container for True Coral."""
    container = DIContainer()
    container.register_instance(DIContainer, container)

    # Event System
    event_dispatcher = EventDispatcher()
    container.register_instance(EventDispatcher, event_dispatcher)

    # Configuration & Logging
    config_manager = ConfigManager(event_dispatcher)
    config_manager.load()
    container.register_instance(ConfigManager, config_manager)

    log_manager = LogManager(event_dispatcher)
    log_manager.configure(level=LogLevel.INFO, console=True)
    container.register_instance(LogManager, log_manager)

    # Window & Graphics
    win_config = WindowConfig(
        title="True Coral - cocar the coral snake",
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

    # Claim the light map before `LightPass` does, so it is 16-bit float
    # rather than the manager's default 8-bit.
    #
    # This is the difference between the lighting working and not. Lights
    # blend additively into this buffer and the composite multiplies the
    # world by it, so an 8-bit map -- clamped at 1.0 -- can only ever
    # restore a colour to what was drawn. No light brightens anything, a
    # glowing mushroom cannot push its surroundings past the bloom
    # threshold, and a lightning strike cannot reveal the floor, because
    # the ambient term it lifts is already saturated. With a float map the
    # same lights over-expose what they fall on, which is what bloom is
    # looking for.
    fbo_manager.get_or_create(LIGHT_FBO_NAME, dtype="f2")

    storm = StormEffect(ctx)
    stack = PostProcessStack(ctx, fbo_manager)
    stack.add_effect(
        BloomEffect(
            ctx,
            fbo_manager,
            threshold=BLOOM_THRESHOLD,
            intensity=BLOOM_INTENSITY,
            blur_passes=BLOOM_BLUR_PASSES,
        )
    )
    stack.add_effect(storm)
    stack.add_effect(VignetteEffect(ctx, intensity=0.42, radius=0.86, softness=0.55))

    render_graph.add_pass(WorldPass(renderer))
    render_graph.add_pass(CompositePass(ctx))
    render_graph.add_pass(PostProcessPass(stack, input_fbo_name="composite"))
    render_graph.add_pass(FinalPass(ctx, input_fbo_name="post_processed"))

    container.register_instance(RenderGraph, render_graph)
    container.register_instance(StormEffect, storm)

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

    # Application
    container.register_singleton(Application, Application)

    return container


def attach_lighting(container: DIContainer, lighting: LightingSystem) -> None:
    """Point the light pass at a scene's own `LightingSystem`.

    `LightPass` needs a `LightingSystem`, which needs an `EntityManager`,
    which is per-scene -- so the pass cannot be built alongside the rest of
    the graph. Each scene calls this from `on_enter()` once its world
    exists, and the previous pass is dropped first: re-entering a scene
    builds a fresh world, and the old pass would go on reading the dead
    one's entities.

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
