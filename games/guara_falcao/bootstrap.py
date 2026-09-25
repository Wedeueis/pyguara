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

from pyguara.application.bootstrap import create_container
from pyguara.config.types import GameConfig, RenderingBackend
from pyguara.di.container import DIContainer
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.lighting.light_system import LightingSystem
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.pipeline.passes import (
    CompositePass,
    FinalPass,
    LightPass,
    PostProcessPass,
)
from pyguara.graphics.vfx.effects.bloom import BloomEffect
from pyguara.graphics.vfx.effects.vignette import VignetteEffect
from pyguara.graphics.vfx.post_process import PostProcessStack
from pyguara.ui.design_system import cerrado_dusk
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


def configure_pipeline(container: DIContainer, camera: Camera2D) -> None:
    """Point the light pass at this frame's camera.

    `Application._render_with_graph()` executes every pass in the graph
    itself (in registration order, skipping only `"world"`, which it
    binds, clears and lets the scene draw into first) -- this only
    configures the one piece of per-frame state execution alone cannot
    know: where the camera is this frame. Both scenes that draw a world
    call it, at the end of their own `render()`.

    Args:
        container: The game's DI container.
        camera: The scene's camera, so the light map lines up with the
            geometry the scene just drew.
    """
    graph = container.get(RenderGraph)
    light_pass = graph.get_pass("light")
    if light_pass is not None:
        light_pass.set_camera(camera)


def _configure(config: GameConfig) -> None:
    """Select the ModernGL backend, and name the window.

    Called before the window exists, which is the only point where
    `backend` still decides which one gets built.

    Args:
        config: The loaded configuration, to adjust in place.
    """
    config.display.title = "Guará & Falcão - A Platformer Adventure"
    config.display.screen_width = WINDOW_WIDTH
    config.display.screen_height = WINDOW_HEIGHT
    config.display.backend = RenderingBackend.MODERNGL

    # Platformer gravity -- set here rather than in the shared config file,
    # since config/game_config.json is on every demo's default load path.
    config.physics.gravity_y = 800.0


def configure_game_container() -> DIContainer:
    """Build the engine container, then this demo's render chain.

    The `ResourceManager` this used to build by hand, with the backend's
    own texture loader, is gone: `create_container()` registers one with
    `GLTextureLoader` already attached whenever the ModernGL backend is
    selected. The comment that stood here explained that nothing had
    registered a loader "because this demo builds its container by hand" --
    which was the whole of #196 in one sentence.

    Returns:
        The configured container.
    """
    container = create_container(_configure)
    _install_theme()

    graph = container.get(RenderGraph)
    ctx = graph.ctx

    # The graph owns the framebuffer manager and every pass resolves
    # through it; anything built here has to share it or it allocates a
    # second, parallel set of buffers the graph never looks at.
    fbo_manager = graph.fbo_manager

    # The engine's default tail blits "world" straight to the screen. This
    # demo composites and post-processes first, so its FinalPass reads a
    # different buffer and replaces that one. WorldPass, identical to the
    # one this demo would have built, stays.
    graph.remove_pass("final")

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

    graph.add_pass(CompositePass(ctx))
    graph.add_pass(PostProcessPass(stack, input_fbo_name="composite"))
    graph.add_pass(FinalPass(ctx, input_fbo_name="post_processed"))

    # Registered so the options panel can switch it off in front of you --
    # a toggle that changes the frame is worth more in a showcase than one
    # that sets a flag nothing reads.
    container.register_instance(BloomEffect, bloom)

    return container
