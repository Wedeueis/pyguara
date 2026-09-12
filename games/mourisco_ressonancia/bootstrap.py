"""Mourisco: Ressonância - Bootstrap.

The only demo in this repo that runs on the **ModernGL** backend, because
it is the only one whose whole premise is lighting: a pitch-black cave
where an echolocation pulse is the light source.

That also makes it the first place the engine's lighting pipeline is
assembled end to end. `pyguara/application/bootstrap.py` only ever builds
`WorldPass -> FinalPass`; `LightPass`, `CompositePass` and
`PostProcessPass` existed and were unit-tested in isolation but nothing
had ever strung them together, so this wiring is new:

    WorldPass      -- draw the cave into the "world" FBO
    LightPass      -- accumulate lights into "lightmap", over ambient
    PulsePass      -- add the expanding wavefront rings on top of it
    CompositePass  -- world * lightmap -> "composite"
    PostProcessPass-- bloom the bright rings -> "post_processed"
    FinalPass      -- blit to the screen

Note the pulse rings are injected into the *lightmap*, before compositing,
so they light the cave rather than merely drawing over it.
"""

from __future__ import annotations

from games.mourisco_ressonancia.pulse_pass import PulsePass
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
from pyguara.ui.manager import UIManager

WINDOW_WIDTH = 960
WINDOW_HEIGHT = 640

# Pushed low so the cave really is black between pulses -- the whole read
# of the game is "what the last pulse lit", and any meaningful ambient
# floor destroys it.
BLOOM_THRESHOLD = 0.45
BLOOM_INTENSITY = 1.5
BLOOM_BLUR_PASSES = 3


def configure_game_container() -> DIContainer:
    """Initialize and configure the DI container for Mourisco: Ressonância."""
    container = DIContainer()
    container.register_instance(DIContainer, container)

    event_dispatcher = EventDispatcher()
    container.register_instance(EventDispatcher, event_dispatcher)

    config_manager = ConfigManager(event_dispatcher)
    config_manager.load()
    config_manager.config.physics.gravity_y = 1500.0
    container.register_instance(ConfigManager, config_manager)

    log_manager = LogManager(event_dispatcher)
    log_manager.configure(level=LogLevel.INFO, console=True)
    container.register_instance(LogManager, log_manager)

    win_config = WindowConfig(
        title="Mourisco: Ressonância -- Master the Mix!",
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

    fbo_manager = FramebufferManager(ctx, WINDOW_WIDTH, WINDOW_HEIGHT)
    container.register_instance(FramebufferManager, fbo_manager)

    # The lighting system is scene-agnostic but needs an EntityManager,
    # which is per-scene, so the scene builds its own and hands it to the
    # passes registered here via `set_lighting_system`.
    render_graph = RenderGraph(ctx, WINDOW_WIDTH, WINDOW_HEIGHT)

    world_pass = WorldPass(renderer)
    pulse_pass = PulsePass(ctx)
    composite_pass = CompositePass(ctx)
    bloom = BloomEffect(
        ctx,
        fbo_manager,
        threshold=BLOOM_THRESHOLD,
        intensity=BLOOM_INTENSITY,
        blur_passes=BLOOM_BLUR_PASSES,
    )
    stack = PostProcessStack(ctx, fbo_manager)
    stack.add_effect(bloom)
    post_pass = PostProcessPass(stack, input_fbo_name="composite")
    final_pass = FinalPass(ctx, input_fbo_name="post_processed")

    render_graph.add_pass(world_pass)
    render_graph.add_pass(pulse_pass)
    render_graph.add_pass(composite_pass)
    render_graph.add_pass(post_pass)
    render_graph.add_pass(final_pass)

    container.register_instance(RenderGraph, render_graph)
    container.register_instance(WorldPass, world_pass)
    container.register_instance(PulsePass, pulse_pass)
    container.register_instance(BloomEffect, bloom)

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

    physics_engine = PymunkEngine()
    container.register_instance(IPhysicsEngine, physics_engine)  # type: ignore[type-abstract]
    collision_system = CollisionSystem(event_dispatcher)
    container.register_instance(CollisionSystem, collision_system)
    physics_engine.set_collision_system(collision_system)

    container.register_singleton(Application, Application)

    return container


def attach_lighting(container: DIContainer, lighting: LightingSystem) -> None:
    """Point the light pass at a scene's own `LightingSystem`.

    `LightPass` needs a `LightingSystem`, which needs an `EntityManager`,
    which is per-scene (`Scene` owns its world) -- so the pass cannot be
    fully built in `configure_game_container()` alongside the rest of the
    graph. The scene calls this from `on_enter()` once its world exists.
    """
    graph = container.get(RenderGraph)
    if graph.get_pass("light") is not None:
        # Re-entering the scene (restart, stage change) builds a fresh
        # world and so a fresh LightingSystem; the old pass would keep
        # reading the dead scene's entities.
        graph.remove_pass("light")

    # Index 1: after WorldPass, before PulsePass -- the rings are added on
    # top of the accumulated lightmap, so they light the cave rather than
    # being multiplied away by it during compositing.
    graph.insert_pass(1, LightPass(graph.ctx, lighting))
