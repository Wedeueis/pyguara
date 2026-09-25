"""Protocolo Bandeira - Bootstrap.

Runs on the **ModernGL** backend, for the same reason True Coral and
Mourisco do: the demo's look is not something a blitter can produce. The
clearing is lit by a low sun and by whatever the fight throws off, the
tracers and the bomber fuses glow because they cross a bloom threshold,
and the afternoon heat is a fragment shader refracting the finished frame.
All three are pipeline features, not draw calls.

The graph assembled here is::

    WorldPass      -- the scene draws the clearing into the "world" FBO
    LightPass      -- the sun, the muzzle flash, the tracers, the blasts
    CompositePass  -- world * lightmap -> "composite"
    PostProcessPass-- bloom, then the heat haze, then a vignette
    FinalPass      -- blit to the screen

Order inside the post stack is the part worth defending. Bloom runs first,
so it bleeds the scene's own hot colours -- and only those; running it
after the haze would bloom the dust instead. The haze runs on the bloomed
image, because hot air refracts a glow exactly as it refracts anything
else behind it. The vignette runs last, over everything, because it is a
lens, not a light.
"""

from __future__ import annotations

from pyguara.application.bootstrap import create_container
from pyguara.common.types import Color
from pyguara.config.types import GameConfig, RenderingBackend
from pyguara.di.container import DIContainer
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.pipeline.passes import (
    CompositePass,
    FinalPass,
    PostProcessPass,
)
from pyguara.graphics.vfx.effects.bloom import BloomEffect
from pyguara.graphics.vfx.effects.heat_haze import HeatHazeEffect
from pyguara.graphics.vfx.effects.vignette import VignetteEffect
from pyguara.graphics.vfx.post_process import PostProcessStack
from pyguara.ui.theme import UITheme, set_theme
from pyguara.ui.types import ColorScheme

WINDOW_WIDTH = 960
WINDOW_HEIGHT = 720

# High enough that the red earth never bleeds -- it is meant to be the
# matte the fight glows against -- and low enough that tracer heads, a
# bomber's fuse and the muzzle flash all cross it.
BLOOM_THRESHOLD = 0.86
BLOOM_INTENSITY = 0.7
BLOOM_BLUR_PASSES = 3


def _install_theme() -> None:
    """Dress the UI widgets in the game's palette.

    The UI is drawn after the final blit, so it picks up no bloom and no
    heat -- which makes the default blue-on-grey widget theme read as a
    different application sitting on top of the game. These colours are
    the clearing's own.
    """
    set_theme(
        UITheme(
            colors=ColorScheme(
                primary=Color(58, 26, 20),
                secondary=Color(104, 48, 30),
                background=Color(22, 13, 14),
                text=Color(244, 230, 204),
                border=Color(206, 112, 54),
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
    config.display.title = "Protocolo Bandeira"
    config.display.screen_width = WINDOW_WIDTH
    config.display.screen_height = WINDOW_HEIGHT
    config.display.backend = RenderingBackend.MODERNGL


def configure_game_container() -> DIContainer:
    """Build the engine container, then this demo's render chain.

    The light map is 16-bit float because `RenderGraph` declares the whole
    chain that way (`pipeline/buffers.py`). Lights blend additively into it
    and the composite multiplies the world by it, so an 8-bit map -- clamped
    at 1.0 -- could only ever restore a colour to what was drawn. No light
    brightened anything, and a muzzle flash could not push the earth around
    it past the bloom threshold. With a float map the same lights over-expose
    what they fall on, which is what bloom is looking for.

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

    haze = HeatHazeEffect(ctx)
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
    stack.add_effect(haze)
    stack.add_effect(VignetteEffect(ctx, intensity=0.46, radius=0.88, softness=0.55))

    graph.add_pass(CompositePass(ctx))
    graph.add_pass(PostProcessPass(stack, input_fbo_name="composite"))
    graph.add_pass(FinalPass(ctx, input_fbo_name="post_processed"))

    container.register_instance(HeatHazeEffect, haze)

    return container
