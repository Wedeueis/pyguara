"""Mourisco: Ressonância - Bootstrap.

Render pipeline, in execution order:

    WorldPass      -- the cave and its occupants
    LightPass      -- inserted by `attach_lighting()` once a scene exists
    PulsePass      -- the echolocation rings, added onto the light map
    CompositePass  -- world x lightmap -> "composite"
    PostProcessPass-- bloom the bright rings -> "post_processed"
    FinalPass      -- blit to the screen

`create_container()` wires everything else, and gives this demo a graph
that already holds `WorldPass` and a `FinalPass` reading straight from
"world". Only the tail is replaced: this chain ends somewhere else.
"""

from __future__ import annotations

from games.mourisco_ressonancia.pulse_pass import PulsePass
from pyguara.application.bootstrap import create_container
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
from pyguara.graphics.vfx.post_process import PostProcessStack

WINDOW_WIDTH = 960
WINDOW_HEIGHT = 640

# Pushed low so the cave really is black between pulses -- the whole read
# of the game is "what the last pulse lit", and any meaningful ambient
# floor destroys it.
BLOOM_THRESHOLD = 0.45
BLOOM_INTENSITY = 1.5
BLOOM_BLUR_PASSES = 3


def _configure(config: GameConfig) -> None:
    """Select the ModernGL backend, and name the window.

    Called before the window exists, which is the only point where
    `backend` still decides which one gets built.

    Args:
        config: The loaded configuration, to adjust in place.
    """
    config.display.title = "Mourisco: Ressonância -- Master the Mix!"
    config.display.screen_width = WINDOW_WIDTH
    config.display.screen_height = WINDOW_HEIGHT
    config.display.backend = RenderingBackend.MODERNGL


def configure_game_container() -> DIContainer:
    """Build the engine container, then this demo's render chain.

    Nothing here touches pymunk: movement is a hand-rolled AABB/grid
    stepper against `CaveLayout` (see `systems.py`'s `PlayerController`)
    for tight platformer feel, and no entity in this demo carries a
    `RigidBody`. The engine registers an `IPhysicsEngine` regardless --
    unused and never ticked, since no scene builds a `PhysicsSystem`.

    Returns:
        The configured container.
    """
    container = create_container(_configure)

    graph = container.get(RenderGraph)
    ctx = graph.ctx

    # The graph's own manager. Anything that allocates buffers -- the bloom
    # effect, the post-process stack -- has to share it, or it gets a
    # parallel set the graph never looks at.
    fbo_manager = graph.fbo_manager

    # The engine's default tail blits "world" straight to the screen. This
    # demo has four passes to run first and ends on a different buffer, so
    # its FinalPass replaces that one. WorldPass, which is identical to
    # what this demo would have built, stays.
    graph.remove_pass("final")

    pulse_pass = PulsePass(ctx)
    bloom = BloomEffect(
        ctx,
        fbo_manager,
        threshold=BLOOM_THRESHOLD,
        intensity=BLOOM_INTENSITY,
        blur_passes=BLOOM_BLUR_PASSES,
    )
    stack = PostProcessStack(ctx, fbo_manager)
    stack.add_effect(bloom)

    graph.add_pass(pulse_pass)
    graph.add_pass(CompositePass(ctx))
    graph.add_pass(PostProcessPass(stack, input_fbo_name="composite"))
    graph.add_pass(FinalPass(ctx, input_fbo_name="post_processed"))

    container.register_instance(PulsePass, pulse_pass)
    container.register_instance(BloomEffect, bloom)

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
