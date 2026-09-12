"""True Coral - the shared environment every scene sits in.

Weather, lighting, backdrop, sparks and shake, wired together once and
reused by the menu, the arena and the game-over screen, so all three are
the same rainy patch of forest floor rather than three unrelated screens.

It also owns the half of the render graph the application does not run.
`Application._render_with_graph()` executes only the graph's `final` pass;
everything between the world buffer and that blit -- lighting, compositing,
post-processing -- is the scene's to drive, so it is driven here rather
than copied into three scenes.
"""

from __future__ import annotations

from games.true_coral.bootstrap import attach_lighting
from games.true_coral.render import Backdrop, draw_ground, draw_litter, draw_owl
from games.true_coral.storm import StormDirector
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Rect, Vector2
from pyguara.di.container import DIContainer
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.lighting.components import AmbientLight, LightSource
from pyguara.graphics.lighting.light_system import LightingSystem
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.protocols import IRenderer
from pyguara.graphics.vfx.effects.storm import StormEffect
from pyguara.graphics.vfx.shake import Shaker
from pyguara.graphics.vfx.sparks import Sparks

# The base exposure everything is multiplied by. Low enough that the leaf
# litter is a texture rather than a subject, high enough that the arena
# stays readable between strikes -- the balance the whole look rests on.
AMBIENT_COLOR = Color(198, 212, 232)
AMBIENT_BASE = 0.62

# How much of a strike's `light_boost` reaches the light map. A strike
# should reveal the floor, not bleach it.
STRIKE_AMBIENT_GAIN = 0.9

# Dynamic lights (prey, the snake) borrow from this pool. Sized for a
# board of prey plus a long snake; asking for more than this silently
# drops the extras rather than allocating mid-frame.
LIGHT_POOL_SIZE = 40

# Splashes per second at full downpour.
SPLASH_RATE = 26.0
SPLASH_COLOR = Color(150, 205, 245)


class Atmosphere:
    """The storm, the light map, the floor, and the feedback layer."""

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
            arena: The play area in screen space. Splashes fall inside it;
                fungi grow around it.
            seed: Seed for weather and sparks. None for an unseeded run.
        """
        self._container = container
        self._entity_manager = entity_manager
        self._width = width
        self._height = height
        self._arena = arena
        self._rng = RandomStream(seed)

        self.backdrop = Backdrop(width, height, arena)
        self.storm = StormDirector(self._rng)
        self.sparks = Sparks(rng=self._rng)
        self.shaker = Shaker(self._rng)

        self.time = 0.0
        self._splash_debt = 0.0

        self._lighting = LightingSystem(entity_manager)
        attach_lighting(container, self._lighting)

        self._ambient = entity_manager.create_entity("ambient")
        self._ambient.add_component(
            AmbientLight(color=AMBIENT_COLOR, intensity=AMBIENT_BASE)
        )

        for position, color, radius in self.backdrop.lights():
            fungus = entity_manager.create_entity()
            fungus.add_component(Transform(position=position))
            fungus.add_component(
                LightSource(color=color, radius=radius, intensity=0.45)
            )

        self._pool: list[Entity] = []
        for _ in range(LIGHT_POOL_SIZE):
            entity = entity_manager.create_entity()
            entity.add_component(Transform(position=Vector2.zero()))
            entity.add_component(LightSource(enabled=False))
            self._pool.append(entity)

    # ---- per-frame -------------------------------------------------

    @property
    def offset(self) -> Vector2:
        """The current screen-shake offset, in pixels."""
        return self.shaker.offset

    def update(self, dt: float, camera: Camera2D | None = None) -> None:
        """Advance the weather, the shake, the sparks and the light map.

        Args:
            dt: Seconds since the last frame.
            camera: The scene's camera, repositioned so that world space
                and screen space coincide, offset by this frame's shake.
                Done here rather than at render time because anything
                drawn through the camera -- floating text, the light map
                -- needs it settled before the frame is drawn.
        """
        self.time += dt
        self.storm.update(dt)

        storm_effect = self._container.get(StormEffect)
        if self.storm.strike_started:
            # A new shape per strike, not per frame: the shader would
            # otherwise redraw a different bolt every frame of the same
            # flash, which reads as static rather than as lightning.
            storm_effect.strike(self.storm.bolt_x)
            self.shaker.add(self.storm.take_shake(), duration=0.35)
        else:
            self.storm.take_shake()

        storm_effect.rain = self.storm.rain
        storm_effect.flash = self.storm.flash
        storm_effect.bolt = self.storm.bolt
        storm_effect.update(dt)

        ambient = self._ambient.get_component(AmbientLight)
        ambient.intensity = AMBIENT_BASE + self.storm.light_boost * STRIKE_AMBIENT_GAIN

        self._spawn_splashes(dt)
        self.sparks.update(dt)
        self.shaker.update(dt)
        self._lighting.update(dt)

        if camera is not None:
            camera.position = Vector2(self._width / 2, self._height / 2) - self.offset

    def _spawn_splashes(self, dt: float) -> None:
        """Land a few drops on the arena floor, in proportion to the rain."""
        self._splash_debt += SPLASH_RATE * self.storm.rain * dt
        while self._splash_debt >= 1.0:
            self._splash_debt -= 1.0
            self.sparks.burst(
                Vector2(
                    self._rng.uniform(self._arena.left, self._arena.right),
                    self._rng.uniform(self._arena.top, self._arena.bottom),
                ),
                SPLASH_COLOR,
                count=3,
                speed=42.0,
                direction=-1.57,  # straight up, then gravity takes it back
                spread=2.2,
                life=0.28,
                radius=1.6,
                gravity=420.0,
                drag=0.9,
            )

    def set_dynamic_lights(
        self, lights: list[tuple[Vector2, Color, float, float]]
    ) -> None:
        """Point the light pool at this frame's moving lights.

        Args:
            lights: `(position, colour, radius, intensity)` per light.
                Anything beyond the pool's size is dropped.
        """
        for index, entity in enumerate(self._pool):
            source = entity.get_component(LightSource)
            if index >= len(lights):
                source.enabled = False
                continue
            position, color, radius, intensity = lights[index]
            entity.get_component(Transform).position = position
            source.color = color
            source.radius = radius
            source.intensity = intensity
            source.enabled = True

    # ---- drawing ---------------------------------------------------

    def draw_ground(self, renderer: IRenderer) -> None:
        """Draw the soil and roots that go under everything.

        Args:
            renderer: Target renderer.
        """
        draw_ground(
            renderer,
            self.backdrop,
            offset=self.offset,
            width=self._width,
            height=self._height,
        )

    def draw_litter(self, renderer: IRenderer) -> None:
        """Draw the leaves, the fungi and the owl, over the arena floor.

        Args:
            renderer: Target renderer.
        """
        draw_litter(renderer, self.backdrop, time=self.time, offset=self.offset)
        draw_owl(renderer, self.backdrop, time=self.time, offset=self.offset)

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
