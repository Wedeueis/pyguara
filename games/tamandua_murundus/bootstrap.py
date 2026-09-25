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
from pyguara.graphics.vfx.effects.vignette import VignetteEffect
from pyguara.graphics.vfx.post_process import PostProcessStack
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


def _configure(config: GameConfig) -> None:
    """Select the ModernGL backend, and name the window.

    Called before the window exists, which is the only point where
    `backend` still decides which one gets built.

    Args:
        config: The loaded configuration, to adjust in place.
    """
    config.display.title = "Tamanduá: O Guardião dos Murundus"
    config.display.screen_width = WINDOW_WIDTH
    config.display.screen_height = WINDOW_HEIGHT
    config.display.backend = RenderingBackend.MODERNGL


def configure_game_container() -> DIContainer:
    """Build the engine container, then this demo's render chain.

    The light map is 16-bit float because `RenderGraph` declares the whole
    chain that way (`pipeline/buffers.py`). An 8-bit map clamps at 1.0, so
    no light could brighten anything past what was drawn, and a swarm that
    never over-exposes never crosses the bloom threshold -- which is the
    entire look of the second half of this run.

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

    graph.add_pass(CompositePass(ctx))
    graph.add_pass(PostProcessPass(stack, input_fbo_name="composite"))
    graph.add_pass(FinalPass(ctx, input_fbo_name="post_processed"))

    return container
