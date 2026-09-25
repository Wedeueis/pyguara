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

from pyguara.application.bootstrap import create_container
from pyguara.common.types import Color
from pyguara.config.types import GameConfig, RenderingBackend
from pyguara.di.container import DIContainer
from pyguara.graphics.lighting.light_system import LightingSystem
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.pipeline.passes import (
    CompositePass,
    FinalPass,
    LightPass,
    PostProcessPass,
)
from pyguara.graphics.vfx.effects.bloom import BloomEffect
from pyguara.graphics.vfx.effects.storm import StormEffect
from pyguara.graphics.vfx.effects.vignette import VignetteEffect
from pyguara.graphics.vfx.post_process import PostProcessStack
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


def _configure(config: GameConfig) -> None:
    """Select the ModernGL backend, and name the window.

    Called before the window exists, which is the only point where
    `backend` still decides which one gets built.

    Args:
        config: The loaded configuration, to adjust in place.
    """
    config.display.title = "True Coral"
    config.display.screen_width = WINDOW_WIDTH
    config.display.screen_height = WINDOW_HEIGHT
    config.display.backend = RenderingBackend.MODERNGL


def configure_game_container() -> DIContainer:
    """Build the engine container, then this demo's render chain.

    The light map is 16-bit float because `RenderGraph` declares the whole
    chain that way (`pipeline/buffers.py`). It is the difference between the
    lighting working and not: lights blend additively into it and the
    composite multiplies the world by it, so an 8-bit map -- clamped at 1.0
    -- could only ever restore a colour to what was drawn. A glowing mushroom
    could not push its surroundings past the bloom threshold, and a lightning
    strike could not reveal the floor, because the ambient term it lifts was
    already saturated.

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

    graph.add_pass(CompositePass(ctx))
    graph.add_pass(PostProcessPass(stack, input_fbo_name="composite"))
    graph.add_pass(FinalPass(ctx, input_fbo_name="post_processed"))

    container.register_instance(StormEffect, storm)

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
