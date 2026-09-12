"""Mourisco: Ressonância - Scenes (validation slice)."""

from __future__ import annotations

from games.mourisco_ressonancia.bootstrap import attach_lighting
from games.mourisco_ressonancia.pulse_pass import PulsePass, PulseRing
from pyguara.common.components import Transform
from pyguara.common.types import Color, Rect, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.lighting.components import AmbientLight, LightSource
from pyguara.graphics.lighting.light_system import LightingSystem
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.scene.base import Scene

WINDOW_WIDTH = 960
WINDOW_HEIGHT = 640


class CaveScene(Scene):
    """Minimal slice: dark cave, one light, one expanding ring."""

    def __init__(self, event_dispatcher: EventDispatcher) -> None:
        """Initialize the cave scene."""
        super().__init__("CaveScene", event_dispatcher)
        self._elapsed = 0.0
        self._lighting: LightingSystem | None = None

    def on_enter(self) -> None:
        """Build the lighting world and attach it to the render graph."""
        self._lighting = LightingSystem(self.entity_manager)
        attach_lighting(self.container, self._lighting)

        # A camera at the origin puts world-centre at the screen's
        # bottom-right corner, because `screen_offset()` adds half a
        # viewport. Centre it so world and screen coincide.
        assert self.camera is not None
        self.camera.position = Vector2(WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2)

        ambient = self.entity_manager.create_entity()
        ambient.add_component(AmbientLight(color=Color(18, 26, 40), intensity=0.16))

        lamp = self.entity_manager.create_entity()
        lamp.add_component(Transform(position=Vector2(300, 320)))
        lamp.add_component(
            LightSource(color=Color(120, 220, 255), radius=180.0, intensity=1.4)
        )

    def on_exit(self) -> None:
        """Nothing to clean up yet."""

    def update(self, dt: float) -> None:
        """Advance the test pulse."""
        self._elapsed += dt
        if self._lighting is not None:
            self._lighting.update(dt)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the cave, then run the lighting half of the pipeline.

        `Application._render_with_graph()` binds and clears the world FBO,
        calls this, then executes only the graph's `final` pass -- it never
        runs the middle of the graph. So the scene drives light -> pulse ->
        composite -> post itself, leaving `final` to blit the result.
        """
        # Cave geometry, drawn into the already-bound world FBO.
        world_renderer.draw_rect(
            Rect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT), Color(30, 34, 44)
        )
        for i in range(6):
            world_renderer.draw_rect(
                Rect(80 + i * 150, 160, 90, 320), Color(96, 104, 124)
            )
        world_renderer.draw_circle(Vector2(300, 320), 22.0, Color(210, 220, 240))
        world_renderer.end_frame()

        self._run_lighting_passes()

    def _run_lighting_passes(self) -> None:
        graph = self.container.get(RenderGraph)
        assert self.camera is not None

        radius = 40.0 + (self._elapsed * 220.0) % 420.0
        fade = 1.0 - (radius - 40.0) / 420.0

        for name in ("light", "pulse", "composite", "post_process"):
            render_pass = graph.get_pass(name)
            if render_pass is None:
                continue
            if name == "light":
                render_pass.set_camera(self.camera)
            elif name == "pulse":
                render_pass.set_camera(self.camera)
                render_pass.set_rings(
                    [
                        PulseRing(
                            position=Vector2(480, 320),
                            radius=radius,
                            color=(0.35, 0.95, 1.0),
                            intensity=2.6 * max(fade, 0.0),
                            thickness=0.05,
                        )
                    ]
                )
            render_pass.execute(graph.ctx, graph)


__all__ = ["CaveScene", "PulsePass"]
