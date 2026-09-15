"""Tamanduá: O Guardião dos Murundus - Bootstrap.

Runs on the **ModernGL** backend. The demo's whole subject is a crowd of
identically-textured insects that are *different colours*, which is a
per-instance vertex attribute on the GL sprite path and nothing a blitter
reproduces; and their bioluminescence is a threshold-crossing colour,
which is a post-process pass.

The graph assembled here is::

    WorldPass      -- the scene draws the clearing into the "world" FBO
    LightPass      -- the murundus, the tamanduá's cone, the flock glow
    CompositePass  -- world * lightmap -> "composite"
    PostProcessPass-- bloom, then a vignette
    FinalPass      -- blit to the screen

**No heat haze.** That is Protocolo Bandeira's showcase, and two demos
claiming the same effect teach nothing. Bloom is this one's, because
bioluminescence *is* a threshold-crossing colour -- see the GDD's §3.2.

Bloom runs before the vignette for the same reason it does in Bandeira:
the vignette is a lens, not a light, and belongs over everything.
"""

from __future__ import annotations

from pyguara.application.application import Application
from pyguara.application.clock import Clock
from pyguara.audio.audio_system import IAudioSystem
from pyguara.audio.backends.pygame.pygame_audio import PygameAudioSystem
from pyguara.common.spatial import SpatialHash
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
from pyguara.graphics.pipeline.framebuffer import FramebufferManager
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.pipeline.passes import (
    CompositePass,
    FinalPass,
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

# Lower than Bandeira's 0.86, and deliberately. There the threshold had to
# sit above a sunlit red earth so only tracers crossed it; here the
# clearing spends most of the run dark, and what has to cross is a
# bioluminescent insect -- small, and never as bright as a muzzle flash.
BLOOM_THRESHOLD = 0.62
BLOOM_INTENSITY = 0.95
BLOOM_BLUR_PASSES = 3


def _install_theme() -> None:
    """Dress the UI widgets in the clearing's palette.

    The UI is drawn after the final blit and picks up no bloom, so the
    default blue-on-grey theme would read as a different application
    sitting on top of the game.
    """
    set_theme(
        UITheme(
            colors=ColorScheme(
                primary=Color(34, 44, 38),
                secondary=Color(62, 96, 74),
                background=Color(12, 16, 18),
                text=Color(226, 240, 220),
                border=Color(120, 208, 160),
            )
        )
    )


def configure_game_container() -> DIContainer:
    """Initialize and configure the DI container for Tamanduá."""
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
        title="Tamanduá: O Guardião dos Murundus",
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

    # The graph owns the framebuffer manager and every pass resolves
    # through it; anything built here has to share it or it allocates a
    # second, parallel set of buffers the graph never looks at.
    fbo_manager = render_graph.fbo_manager
    container.register_instance(FramebufferManager, fbo_manager)

    # The light map is 16-bit float because `RenderGraph` declares the
    # whole chain that way (`pipeline/buffers.py`) -- this bootstrap used to
    # claim it by hand. An 8-bit map clamps at 1.0, so no light could
    # brighten anything past what was drawn, and a swarm that never
    # over-exposes never crosses the bloom threshold, which is the entire
    # look of the second half of this run.

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
    stack.add_effect(VignetteEffect(ctx, intensity=0.52, radius=0.85, softness=0.6))

    render_graph.add_pass(WorldPass(renderer))
    render_graph.add_pass(CompositePass(ctx))
    render_graph.add_pass(PostProcessPass(stack, input_fbo_name="composite"))
    render_graph.add_pass(FinalPass(ctx, input_fbo_name="post_processed"))

    container.register_instance(RenderGraph, render_graph)

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

    # The tongue's target search and (from D4) the mote magnet both query
    # this rather than scanning every insect.
    container.register_instance(SpatialHash, SpatialHash())

    container.register_singleton(Application, Application)

    return container
