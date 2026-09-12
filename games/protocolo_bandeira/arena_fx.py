"""Protocolo Bandeira - the clearing every scene sits in, and the juice.

Lighting, heat, backdrop, sparks, shake, hit-stop and floating text, wired
together once and reused by the menu, the arena and the game-over screen,
so all three are the same patch of cerrado rather than three unrelated
screens.

It also owns the half of the render graph the application does not run.
`Application._render_with_graph()` executes only the graph's `final` pass;
everything between the world buffer and that blit -- lighting,
compositing, post-processing -- is the scene's to drive, so it is driven
here rather than copied into three scenes.

**Hit-stop** lives here too, because it is the one piece of feedback that
is not purely visual: a kill freezes the simulation for a few frames while
the frame keeps being drawn, which is what makes a hit land. The scene
asks for `gameplay_dt(dt)` and steps its systems with that, while
everything in this module keeps running on the real `dt` -- sparks have to
fly and the shake has to settle during the freeze, or the freeze reads as
a stutter rather than as an impact.
"""

from __future__ import annotations

import math

from games.protocolo_bandeira import render
from games.protocolo_bandeira.render import Backdrop
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Rect, Vector2
from pyguara.di.container import DIContainer
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.floating_text import FloatingText
from pyguara.graphics.components.screen_flash import ScreenFlash
from pyguara.graphics.lighting.components import AmbientLight, LightSource
from pyguara.graphics.lighting.light_system import LightingSystem
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.protocols import IRenderer
from pyguara.graphics.vfx.effects.heat_haze import HeatHazeEffect
from pyguara.graphics.vfx.shake import Shaker
from pyguara.graphics.vfx.sparks import Sparks

# Late afternoon: warm, low, and dim enough that muzzle flashes and a
# bomber's fuse are genuinely the brightest things on the field.
AMBIENT_COLOR = Color(255, 186, 142)
AMBIENT_BASE = 0.55

# The standing shimmer, in pixels of refraction, plus the dust hanging in
# it and how much an explosion kicks up on top. The shimmer is kept small
# on purpose: it should make the air look hot, not make the arena hard to
# read while something is shooting at you.
HAZE_PIXELS = 3.2
HAZE_DUST = 0.34
HAZE_WIND = 1.0
HAZE_SUN = 0.16
EXPLOSION_GUST = 0.28

# Dynamic lights (the player, shots, bombers, blasts) borrow from this
# pool. Asking for more than this drops the extras rather than allocating
# mid-frame.
LIGHT_POOL_SIZE = 56

# A blast's light, and how long it takes to die.
FLARE_LIFE = 0.42


class _Flare:
    """A decaying point of light left behind by an explosion."""

    __slots__ = ("position", "color", "radius", "life")

    def __init__(self, position: Vector2, color: Color, radius: float) -> None:
        self.position = position
        self.color = color
        self.radius = radius
        self.life = FLARE_LIFE


class ArenaFX:
    """The clearing, the light map, the heat, and every bit of feedback."""

    def __init__(
        self,
        container: DIContainer,
        entity_manager: EntityManager,
        *,
        width: int,
        height: int,
        arena: Rect,
        seed: int | None = None,
    ) -> None:
        """Build the environment and attach it to the render graph.

        Args:
            container: The game's DI container.
            entity_manager: The entering scene's world; light entities are
                created in it and die with it.
            width: Window width in pixels.
            height: Window height in pixels.
            arena: The play area in screen space.
            seed: Seed for the scatter and the sparks. None for an
                unseeded run.
        """
        self._container = container
        self._width = width
        self._height = height
        self._arena = arena
        self._rng = RandomStream(seed)

        self.backdrop = Backdrop(width, height, arena, self._rng)
        self.sparks = Sparks(capacity=420, rng=self._rng)
        self.shaker = Shaker(self._rng)
        self.popups = FloatingText(capacity=40)
        self.flash = ScreenFlash()

        self.time = 0.0
        self._freeze = 0.0
        self._flares: list[_Flare] = []

        # The heat is a shared post-process effect built once in the
        # bootstrap, so the *look* of the afternoon is set here, where the
        # rest of the clearing's look is, rather than at construction of
        # a pipeline that knows nothing about this game.
        haze = container.get(HeatHazeEffect)
        haze.haze = HAZE_PIXELS
        haze.dust = HAZE_DUST
        haze.wind = HAZE_WIND
        haze.sun = HAZE_SUN
        # Heat pools on the ground, and here the ground is the whole
        # frame below the bezel -- so the ramp starts at the arena's top
        # edge rather than at a distant horizon.
        haze.horizon = arena.top / height

        self._lighting = LightingSystem(entity_manager)
        attach_lighting(container, self._lighting)

        self._ambient = entity_manager.create_entity("ambient")
        self._ambient.add_component(
            AmbientLight(color=AMBIENT_COLOR, intensity=AMBIENT_BASE)
        )

        # The sun, low and off to one side. A single wide light rather
        # than a raised ambient, so the clearing has a direction to it --
        # placed well above the window, because a light *inside* the frame
        # has a hotspot, and anything that walks into a hotspot on a
        # float light map blows out to white.
        sun = entity_manager.create_entity("sun")
        sun.add_component(Transform(position=Vector2(width * 0.68, -260.0)))
        sun.add_component(
            LightSource(color=Color(255, 152, 92), radius=1150.0, intensity=0.42)
        )

        self._pool: list[Entity] = []
        for _ in range(LIGHT_POOL_SIZE):
            entity = entity_manager.create_entity()
            entity.add_component(Transform(position=Vector2.zero()))
            entity.add_component(LightSource(enabled=False))
            self._pool.append(entity)

    # ---- hit-stop --------------------------------------------------

    @property
    def frozen(self) -> bool:
        """Whether the simulation is currently held for a hit."""
        return self._freeze > 0.0

    def hit_stop(self, duration: float) -> None:
        """Freeze the simulation for a moment.

        Takes the longest of the requests in flight rather than summing
        them: two kills on the same frame should land as one beat, and
        adding their freezes would stall the game noticeably.

        Args:
            duration: Seconds to hold. Kills use a few frames' worth;
                anything past about 0.15 reads as a hitch.
        """
        self._freeze = max(self._freeze, duration)

    def gameplay_dt(self, dt: float) -> float:
        """Return the timestep the scene's systems should advance by.

        Args:
            dt: The real frame time.

        Returns:
            Zero while a hit-stop is holding, otherwise `dt`.
        """
        if self._freeze > 0.0:
            self._freeze = max(0.0, self._freeze - dt)
            return 0.0
        return dt

    # ---- feedback --------------------------------------------------

    @property
    def offset(self) -> Vector2:
        """The current screen-shake offset, in pixels."""
        return self.shaker.offset

    def impact(
        self,
        position: Vector2,
        color: Color,
        *,
        count: int = 10,
        speed: float = 190.0,
        direction: float | None = None,
        shake: float = 0.0,
    ) -> None:
        """A small hit: a spray of sparks and an optional nudge.

        Args:
            position: Where the hit landed, in screen space.
            color: Spark colour.
            count: How many sparks.
            speed: Base spark speed.
            direction: Centre angle of the spray, or None for all around.
            shake: Screen shake magnitude in pixels; 0 for none.
        """
        self.sparks.burst(
            position,
            color,
            count=count,
            speed=speed,
            direction=direction,
            spread=1.9 if direction is not None else math.tau,
            life=0.34,
            radius=2.6,
            gravity=0.0,
            drag=0.86,
            streak=True,
        )
        if shake > 0.0:
            self.shaker.add(shake, duration=0.18)

    def explode(
        self,
        position: Vector2,
        color: Color,
        *,
        big: bool = False,
    ) -> None:
        """A death: debris, a flare of light, a gust of dust and a shake.

        Args:
            position: Where it went off, in screen space.
            color: Debris and flare colour.
            big: Whether this is a bomber rather than an ordinary kill.
        """
        self.sparks.burst(
            position,
            color,
            count=22 if big else 14,
            speed=300.0 if big else 210.0,
            life=0.5,
            radius=3.4 if big else 2.8,
            gravity=0.0,
            drag=0.9,
            streak=True,
        )
        self.sparks.burst(
            position,
            render.DUST_PALE,
            count=10,
            speed=110.0,
            life=0.7,
            radius=4.0,
            gravity=0.0,
            drag=0.93,
        )
        self._flares.append(_Flare(position, color, radius=170.0 if big else 115.0))
        self.shaker.add(9.0 if big else 4.0, duration=0.3 if big else 0.2)
        self._container.get(HeatHazeEffect).gust(EXPLOSION_GUST * (1.8 if big else 1.0))

    def popup(self, text: str, position: Vector2, color: Color, size: int = 16) -> None:
        """Float a number or a word up from a point on the field.

        Args:
            text: The string to show. Kept short -- it is never wrapped.
            position: Where it starts, in screen space.
            color: Text colour; it fades out from here.
            size: Font size in pixels.
        """
        self.popups.spawn(
            text,
            position + Vector2(self._rng.uniform(-8, 8), -10),
            color,
            size=size,
            life=0.85,
            velocity=Vector2(self._rng.uniform(-18, 18), -62),
        )

    # ---- per-frame -------------------------------------------------

    def update(self, dt: float, camera: Camera2D | None = None) -> None:
        """Advance the heat, the shake, the sparks and the light map.

        Always called with the *real* frame time, never the hit-stopped
        one: the freeze holds the simulation, not the feedback.

        Args:
            dt: Seconds since the last frame.
            camera: The scene's camera, repositioned so world space and
                screen space coincide, offset by this frame's shake. Done
                here rather than at render time because anything drawn
                through the camera -- floating text, the light map -- needs
                it settled before the frame is drawn.
        """
        self.time += dt

        haze = self._container.get(HeatHazeEffect)
        haze.update(dt)

        for flare in self._flares:
            flare.life -= dt
        self._flares = [flare for flare in self._flares if flare.life > 0.0]

        self.sparks.update(dt)
        self.shaker.update(dt)
        self.popups.update(dt)
        self.flash.update(dt)
        self._lighting.update(dt)

        if camera is not None:
            camera.position = Vector2(self._width / 2, self._height / 2) - self.offset

    def set_dynamic_lights(
        self, lights: list[tuple[Vector2, Color, float, float]]
    ) -> None:
        """Point the light pool at this frame's moving lights.

        The decaying explosion flares are appended here rather than being
        the caller's problem, since they outlive the entity that caused
        them.

        Args:
            lights: `(position, colour, radius, intensity)` per light.
                Anything beyond the pool's size is dropped.
        """
        combined = list(lights)
        for flare in self._flares:
            fraction = flare.life / FLARE_LIFE
            combined.append(
                (flare.position, flare.color, flare.radius * fraction, 0.75 * fraction)
            )

        for index, entity in enumerate(self._pool):
            source = entity.get_component(LightSource)
            if index >= len(combined):
                source.enabled = False
                continue
            position, color, radius, intensity = combined[index]
            entity.get_component(Transform).position = position
            source.color = color
            source.radius = radius
            source.intensity = intensity
            source.enabled = True

    # ---- drawing ---------------------------------------------------

    def draw_ground(self, renderer: IRenderer) -> None:
        """Draw the earth, the fissures and the scatter, under everything.

        Args:
            renderer: Target renderer.
        """
        render.draw_ground(
            renderer,
            self.backdrop,
            offset=self.offset,
            width=self._width,
            height=self._height,
            arena=self._arena,
        )
        render.draw_scatter(renderer, self.backdrop, offset=self.offset)
        render.draw_arena_edge(renderer, self._arena, offset=self.offset)

    def run_pipeline(self, camera: Camera2D) -> None:
        """Execute light -> composite -> post-process for this frame.

        The application runs only the graph's `final` pass, so everything
        between the world buffer and the screen happens here.

        Args:
            camera: The scene's camera, already positioned by `update()`
                so the light map lines up with geometry the scene drew
                shaken.
        """
        graph = self._container.get(RenderGraph)
        for name in ("light", "composite", "post_process"):
            render_pass = graph.get_pass(name)
            if render_pass is None:
                continue
            if name == "light":
                render_pass.set_camera(camera)
            render_pass.execute(graph.ctx, graph)


def attach_lighting(container: DIContainer, lighting: LightingSystem) -> None:
    """Point the light pass at a scene's own `LightingSystem`.

    `LightPass` needs a `LightingSystem`, which needs an `EntityManager`,
    which is per-scene -- so the pass cannot be built alongside the rest of
    the graph. Each scene calls this as it builds its `ArenaFX`, and the
    previous pass is dropped first: re-entering a scene builds a fresh
    world, and the old pass would go on reading the dead one's entities.

    Args:
        container: The game's DI container.
        lighting: The entering scene's lighting system.
    """
    from pyguara.graphics.pipeline.passes import LightPass

    graph = container.get(RenderGraph)
    if graph.get_pass("light") is not None:
        graph.remove_pass("light")

    # Index 1: after the world is drawn, before it is composited with the
    # light map it is about to be multiplied by.
    graph.insert_pass(1, LightPass(graph.ctx, lighting))
