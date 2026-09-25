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
`persistence_schema.py`), with `MIGRATIONS` registered so a garden saved
by an older build is carried forward rather than refused. `FileStorageBackend.base_path` is CWD-relative, not an OS user-data
directory (a known engine gap, tracked as issue #43) -- fine for a demo
run from the repo root via `uv run python -m games.quintal_cerrado.main`,
but not a real per-user save location.
"""

from __future__ import annotations

from games.quintal_cerrado.persistence_schema import MIGRATIONS, SCHEMA_VERSION
from games.quintal_cerrado.soil_health_effect import SoilHealthEffect
from pyguara.application.bootstrap import create_container
from pyguara.config.types import GameConfig, RenderingBackend
from pyguara.di.container import DIContainer
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.pipeline.passes import FinalPass, PostProcessPass
from pyguara.graphics.vfx.effects.storm import StormEffect
from pyguara.graphics.vfx.effects.vignette import VignetteEffect
from pyguara.graphics.vfx.post_process import PostProcessStack
from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.migration import MigrationManager
from pyguara.persistence.storage import FileStorageBackend
from pyguara.ui.design_system import cerrado_dusk
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


def _configure(config: GameConfig) -> None:
    """Select the ModernGL backend, and name the window.

    Called before the window exists, which is the only point where
    `backend` still decides which one gets built.

    Args:
        config: The loaded configuration, to adjust in place.
    """
    config.display.title = "Quintal do Cerrado"
    config.display.screen_width = WINDOW_WIDTH
    config.display.screen_height = WINDOW_HEIGHT
    config.display.backend = RenderingBackend.MODERNGL


def configure_game_container() -> DIContainer:
    """Build the engine container, then this demo's render chain and saves.

    Two things here are genuinely this demo's own, and both *replace* an
    engine default rather than adding to it: the post-process chain, and
    persistence -- which needs its own save directory, its own schema
    version and its own migrations. A later `register_instance` wins, so
    the override is the whole mechanism.

    Returns:
        The configured container.
    """
    container = create_container(_configure)
    set_theme(cerrado_dusk())

    graph = container.get(RenderGraph)
    ctx = graph.ctx

    # The graph owns the framebuffer manager and every pass resolves
    # through it; anything built here has to share it or it allocates a
    # second, parallel set of buffers the graph never looks at.
    fbo_manager = graph.fbo_manager

    # The engine's default tail blits "world" straight to the screen. This
    # demo post-processes first, so its FinalPass reads a different buffer
    # and replaces that one. WorldPass, identical to the one this demo
    # would have built, stays. There is no CompositePass: nothing here
    # renders a light map.
    graph.remove_pass("final")

    soil_health_effect = SoilHealthEffect(ctx)
    storm = StormEffect(ctx)
    vignette = VignetteEffect(
        ctx, intensity=BASE_VIGNETTE_INTENSITY, radius=BASE_VIGNETTE_RADIUS
    )
    stack = PostProcessStack(ctx, fbo_manager)
    stack.add_effect(soil_health_effect)
    stack.add_effect(storm)
    stack.add_effect(vignette)

    graph.add_pass(PostProcessPass(stack, input_fbo_name="world"))
    graph.add_pass(FinalPass(ctx, input_fbo_name="post_processed"))

    container.register_instance(SoilHealthEffect, soil_health_effect)
    container.register_instance(StormEffect, storm)
    container.register_instance(VignetteEffect, vignette)

    # Saves live under this demo's own directory, at its own schema
    # version, with its own migrations -- none of which the engine's
    # default (base_path="saves", version 1, the global migration
    # registry) can know about.
    storage = FileStorageBackend(base_path=SAVE_DIRECTORY)
    migration_manager = MigrationManager(current_version=SCHEMA_VERSION)
    for migration in MIGRATIONS:
        migration_manager.register(migration)
    container.register_instance(MigrationManager, migration_manager)
    container.register_instance(
        PersistenceManager, PersistenceManager(storage, migration_manager)
    )

    return container
