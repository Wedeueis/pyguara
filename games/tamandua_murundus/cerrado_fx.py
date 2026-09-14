"""The clearing every scene sits in, and the feedback it throws off.

The `arena_fx.py` analogue: lighting, backdrop, sparks, shake, hit-stop
and floating text wired together once, so the menu and the run are the
same patch of cerrado rather than two unrelated screens.

It also drives the half of the render graph the application does not.
`Application._render_with_graph()` executes only the graph's `final` pass;
everything between the world buffer and that blit -- lighting,
compositing, post-processing -- is the scene's to run, so it is run here
rather than copied into every scene.

**Hit-stop** lives here because it is the one piece of feedback that is
not purely visual: a kill freezes the simulation for a few frames while
the frame keeps being drawn. The scene steps its systems with
`gameplay_dt(dt)` while everything in this module keeps running on the
real `dt` -- sparks have to fly and the shake has to settle during the
freeze, or it reads as a stutter instead of an impact.

**The ambient light is left alone here.** D3 attaches an `AmbientCycle` to
the ambient entity, and the rule that comes with it is that the cycle owns
the light: a module that also wrote `AmbientLight.intensity` would be a
second writer racing it. So this module sets the ambient *once*, at
construction, and never touches it again.
"""

from __future__ import annotations

import math

from games.tamandua_murundus.render import Backdrop
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Rect, Vector2
from pyguara.di.container import DIContainer
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.floating_text import FloatingText
from pyguara.graphics.components.screen_flash import ScreenFlash
from pyguara.graphics.lighting.components import AmbientLight, LightSource, LightType
from pyguara.graphics.lighting.light_system import LightingSystem
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.protocols import IRenderer
from pyguara.graphics.vfx.shake import Shaker
from pyguara.graphics.vfx.sparks import Sparks

# Dusk, where the run starts: warm but already going. D3 replaces this
# fixed pair with the first keyframe of an `AmbientCycle`.
AMBIENT_COLOR = Color(158, 162, 196)
AMBIENT_BASE = 0.66

# Dynamic lights (mounds, flock centroids, kills) borrow from this pool.
# Asking for more than this drops the extras rather than allocating
# mid-frame. Sized for ~8 mounds, ~6 flock centroids and a margin --
# deliberately nowhere near the insect count, because insects are not
# lights (GDD §3.2).
LIGHT_POOL_SIZE = 24

# A kill's light, and how long it takes to die.
FLARE_LIFE = 0.3


class _Flare:
    """A decaying point of light left behind by a kill."""

    __slots__ = ("position", "color", "radius", "life")

    def __init__(self, position: Vector2, color: Color, radius: float) -> None:
        self.position = position
        self.color = color
        self.radius = radius
        self.life = FLARE_LIFE


class CerradoFX:
    """The clearing, the light map, and every bit of feedback."""

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
            seed: Seed for the scatter and the sparks, or None.
        """
        self._container = container
        self._width = width
        self._height = height
        self._arena = arena
        self._rng = RandomStream(seed)

        self.backdrop = Backdrop(width, height, arena, self._rng)
        self.sparks = Sparks(capacity=260, rng=self._rng)
        self.shaker = Shaker(self._rng)
        self.popups = FloatingText(capacity=32)
        self.flash = ScreenFlash()

        self.time = 0.0
        self._freeze = 0.0
        self._flares: list[_Flare] = []

        self._lighting = LightingSystem(entity_manager)
        attach_lighting(container, self._lighting)

        # Set once. From D3 an `AmbientCycle` drives this entity, and the
        # cycle owns the light -- see the module docstring.
        self.ambient_entity = entity_manager.create_entity("ambient")
        self.ambient_entity.add_component(
            AmbientLight(color=AMBIENT_COLOR, intensity=AMBIENT_BASE)
        )

        # The tamanduá's own cone: a genuine SPOT light, aimed by the
        # player's facing. This is the light the clearing is actually read
        # by once the ambient falls.
        self.snout_light = entity_manager.create_entity("snout")
        self.snout_light.add_component(Transform(position=Vector2.zero()))
        self.snout_light.add_component(
            LightSource(
                color=Color(255, 236, 198),
                radius=300.0,
                intensity=0.9,
                light_type=LightType.SPOT,
                spot_angle=74.0,
            )
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

        Takes the longest request in flight rather than summing them: two
        kills on the same frame should land as one beat, and adding their
        freezes would stall the run noticeably -- which matters far more
        here than in a duel, because this demo kills in handfuls.
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
        """The current screen shake offset, in pixels."""
        return self.shaker.offset

    def aim_snout(self, position: Vector2, facing: float) -> None:
        """Point the tamanduá's cone.

        Args:
            position: The anteater's body centre.
            facing: Heading in radians, clockwise from screen +x -- the
                same convention `LightSource.spot_direction` uses, so this
                needs no conversion beyond degrees.
        """
        transform = self.snout_light.get_component(Transform)
        transform.position = Vector2(
            position.x + math.cos(facing) * 18.0,
            position.y + math.sin(facing) * 18.0,
        )
        self.snout_light.get_component(LightSource).spot_direction = math.degrees(
            facing
        )

    def kill(self, position: Vector2, color: Color) -> None:
        """Mark an insect's death: sparks, a flare, and a small shake."""
        self.sparks.burst(position, color, count=7, streak=False)
        self._flares.append(_Flare(position, color, 74.0))
        self.shaker.add(0.9, 0.1)

    def mound_broken(self, position: Vector2) -> None:
        """Mark a murundu breaking: the biggest single beat in the run."""
        self.sparks.burst(position, Color(255, 176, 92), count=34, streak=True)
        self._flares.append(_Flare(position, Color(255, 150, 70), 260.0))
        self.shaker.add(7.0, 0.42)
        self.flash.trigger(Color(255, 188, 120, 52), 0.24)
        self.hit_stop(0.09)

    def popup(self, text: str, position: Vector2, color: Color, size: int = 16) -> None:
        """Float a number or a word up from a position."""
        self.popups.spawn(text, position, color, size=size)

    # ---- frame -----------------------------------------------------

    def update(self, dt: float, camera: Camera2D | None = None) -> None:
        """Advance everything that runs on real time, not gameplay time."""
        self.time += dt
        self.sparks.update(dt)
        self.shaker.update(dt)
        self.popups.update(dt)
        self.flash.update(dt)

        for flare in self._flares:
            flare.life -= dt
        self._flares = [flare for flare in self._flares if flare.life > 0.0]

        self._lighting.update(dt)

    def set_dynamic_lights(
        self, lights: list[tuple[Vector2, Color, float, float]]
    ) -> None:
        """Point the light pool at this frame's dynamic lights.

        Flares are appended to whatever the scene asked for, so a kill
        lights the clearing without the scene having to remember it.

        Args:
            lights: `(position, colour, radius, intensity)` per light.
        """
        requested = list(lights)
        for flare in self._flares:
            fade = max(0.0, flare.life / FLARE_LIFE)
            requested.append((flare.position, flare.color, flare.radius * fade, fade))

        for index, entity in enumerate(self._pool):
            source = entity.get_component(LightSource)
            if index >= len(requested):
                source.enabled = False
                continue
            position, color, radius, intensity = requested[index]
            entity.get_component(Transform).position = position
            source.enabled = True
            source.color = color
            source.radius = radius
            source.intensity = intensity

    def draw_ground(self, renderer: IRenderer) -> None:
        """Paint the clearing. Call first, before anything standing on it."""
        self.backdrop.draw(renderer)

    def run_pipeline(self, camera: Camera2D) -> None:
        """Execute light -> composite -> post-process for this frame.

        Named explicitly rather than "every pass except final". The world
        pass is in the graph too, and it *clears* the world buffer before
        drawing its own queue -- running it here would erase everything
        the scene just drew immediately into that buffer, which is a blank
        frame and no error.

        Args:
            camera: The scene's camera, so the light map lines up with
                geometry the scene drew shaken.
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
    which a scene owns -- so the pass cannot be built in the bootstrap
    before any scene exists. It is inserted here instead, and replaced
    rather than appended when a second scene enters: each scene brings its
    own world and so a fresh `LightingSystem`, and a stale pass would keep
    lighting the previous scene's entities.
    """
    from pyguara.graphics.pipeline.passes import LightPass

    graph = container.get(RenderGraph)
    if graph.get_pass("light") is not None:
        graph.remove_pass("light")

    # Index 1: after the world is drawn, before it is composited with the
    # light map it is about to be multiplied by.
    graph.insert_pass(1, LightPass(graph.ctx, lighting))
