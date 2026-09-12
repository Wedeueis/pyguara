"""Mourisco: Ressonância - Scenes.

The pitch-black cave. Everything the player can see is something a pulse
lit, because the compositor multiplies the world by the light map -- so
the reveal is not drawn on top of the scene, it *is* how the scene
becomes visible at all.
"""

from __future__ import annotations

from games.mourisco_ressonancia import render
from games.mourisco_ressonancia.bootstrap import attach_lighting
from games.mourisco_ressonancia.cave import (
    TILE,
    cave_formations,
    exposed_faces,
    parse_cave,
)
from games.mourisco_ressonancia.pulse_pass import PulseRing
from games.mourisco_ressonancia.systems import (
    Bat,
    CreatureSystem,
    PlayerController,
    PlayerState,
    PulseSystem,
    Spider,
)
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.entity import Entity
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.lighting.components import AmbientLight, LightSource
from pyguara.graphics.lighting.light_system import LightingSystem
from pyguara.graphics.pipeline.graph import RenderGraph
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.events import OnActionEvent
from pyguara.input.keys import ESCAPE, LEFT, RIGHT, SPACE, A, D, R, S, W
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.kits.echolocation import (
    PulseEmitter,
    RevealMemory,
    start_pulse,
    tick_cooldown,
)
from pyguara.scene.base import Scene

WINDOW_WIDTH = 960
WINDOW_HEIGHT = 640

CHIRP_COLOR = (0.36, 0.88, 1.0)
SCREAM_COLOR = (0.72, 0.46, 1.0)

_UI_TEXT = Color(196, 224, 240)
_UI_DIM = Color(112, 136, 156)
_UI_ACCENT = Color(150, 240, 220)


def _dust_motes(layout) -> list[tuple[Vector2, float, float]]:
    """Scatter dust through the cave's open air, once.

    Seeded and precomputed: motes are part of the cave, and re-rolling
    them per frame would make the air crawl.
    """
    rng = RandomStream(8125)
    motes: list[tuple[Vector2, float, float]] = []
    for _ in range(220):
        for _attempt in range(6):
            point = Vector2(
                rng.uniform(0, layout.world_width), rng.uniform(0, layout.world_height)
            )
            if not layout.is_solid((int(point.x // TILE), int(point.y // TILE))):
                motes.append((point, rng.uniform(0.8, 2.1), rng.uniform(0.0, 6.28)))
                break
    return motes


class CaveScene(Scene):
    """The playable cave."""

    def __init__(self, event_dispatcher: EventDispatcher) -> None:
        """Initialize the cave scene."""
        super().__init__("CaveScene", event_dispatcher)
        self._elapsed = 0.0
        self._layout = parse_cave()
        self._faces = exposed_faces(self._layout)
        self._formations = cave_formations(self._layout)
        self._memory = RevealMemory(decay_per_second=0.16)
        self._emitter = PulseEmitter()
        self._player = PlayerState(position=self._layout.player_spawn)
        self._controller = PlayerController(self._layout, self._player)
        self._pulses = PulseSystem(self._layout, self._memory)
        self._creatures = CreatureSystem(
            self._layout,
            [Bat(position=p, home=p) for p in self._layout.bat_roosts],
            [Spider(position=p, home=p) for p in self._layout.spider_perches],
        )
        self._lighting: LightingSystem | None = None
        self._camera_target = Vector2(self._player.position.x, self._player.position.y)
        self._motes = _dust_motes(self._layout)
        self._pulse_count = 0
        self._held_left = False
        self._held_right = False
        self._player_light: Entity | None = None
        self._exit_light: Entity | None = None

    # ---- lifecycle ----------------------------------------------------

    def on_enter(self) -> None:
        """Wire lighting, input, and the player's own faint glow."""
        self._lighting = LightingSystem(self.entity_manager)
        attach_lighting(self.container, self._lighting)

        ambient = self.entity_manager.create_entity()
        # Deliberately *not* near-zero, which is the intuitive setting for
        # a dark cave and is wrong here. Darkness is enforced by what
        # `draw_cave` draws at all -- an unrevealed tile is never
        # submitted, so it composites black regardless of ambient. Ambient
        # is therefore what makes *remembered* geometry visible, and
        # crushing it just turns the whole reveal black too. The pulse
        # rings still supply the bright moving crest on top.
        ambient.add_component(AmbientLight(color=Color(150, 190, 226), intensity=1.0))

        self._player_light = self.entity_manager.create_entity()
        self._player_light.add_component(Transform(position=self._player.position))
        self._player_light.add_component(
            LightSource(color=Color(140, 200, 230), radius=96.0, intensity=0.7)
        )

        self._exit_light = self.entity_manager.create_entity()
        self._exit_light.add_component(Transform(position=self._layout.exit_position))
        self._exit_light.add_component(
            LightSource(color=Color(120, 255, 200), radius=120.0, intensity=0.8)
        )

        self._setup_input()

    def on_exit(self) -> None:
        """Drop this scene's input subscription."""
        self.event_dispatcher.unsubscribe(OnActionEvent, self._on_action)

    def _setup_input(self) -> None:
        im = self.container.get(InputManager)
        for action in ("left", "right"):
            im.register_action(action, ActionType.HOLD)
        for action in ("jump", "chirp", "scream", "restart", "quit"):
            im.register_action(action, ActionType.PRESS)

        im.bind_input(InputDevice.KEYBOARD, A, "left")
        im.bind_input(InputDevice.KEYBOARD, LEFT, "left")
        im.bind_input(InputDevice.KEYBOARD, D, "right")
        im.bind_input(InputDevice.KEYBOARD, RIGHT, "right")
        im.bind_input(InputDevice.KEYBOARD, W, "jump")
        im.bind_input(InputDevice.KEYBOARD, SPACE, "chirp")
        im.bind_input(InputDevice.KEYBOARD, R, "restart")
        im.bind_input(InputDevice.KEYBOARD, ESCAPE, "quit")
        # A dedicated key rather than shift+chirp: reading a modifier
        # alongside an action is not something the action layer exposes,
        # and both calls should be equally reachable anyway.
        im.bind_input(InputDevice.KEYBOARD, S, "scream")

        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def _on_action(self, event: OnActionEvent) -> None:
        pressed = event.value > 0
        action = event.action_name
        if action == "left":
            self._held_left = pressed
        elif action == "right":
            self._held_right = pressed
        elif action == "jump" and pressed:
            self._controller.jump_requested = True
        elif action == "chirp" and pressed:
            self._call(scream=False)
        elif action == "scream" and pressed:
            self._call(scream=True)
        elif action == "restart" and pressed:
            self._restart()

    def _call(self, *, scream: bool) -> None:
        if not self._emitter.is_ready:
            return
        origin = Vector2(self._player.position.x, self._player.position.y)
        pulse = start_pulse(self._emitter, origin, scream=scream)
        self._pulses.emit(pulse)
        self._creatures.on_pulse(pulse)
        self._player.call_flash = 1.0
        self._pulse_count += 1

    def _on_spider_hit(self, spider_position: Vector2) -> None:
        """A spider connects: thrown clear, and disoriented.

        Losing most of the reveal is the real cost -- being hurt in a game
        with no health bar has to take away the thing the player actually
        has, which here is their picture of the cave.
        """
        away = self._player.position - spider_position
        direction = (
            away.normalized()
            if away.length > 0.01
            else Vector2(-self._player.facing, 0)
        )
        self._player.velocity = Vector2(direction.x * 300.0, -260.0)
        self._player.hurt_flash = 1.0
        self._memory.dim(0.45, ceiling=0.5)

    def _restart(self) -> None:
        self._memory.clear()
        self._player.position = Vector2(
            self._layout.player_spawn.x, self._layout.player_spawn.y
        )
        self._player.velocity = Vector2(0, 0)
        self._player.reached_exit = False
        self._pulse_count = 0

    # ---- frame --------------------------------------------------------

    def update(self, dt: float) -> None:
        """Advance movement, pulses, creatures and the fading reveal."""
        self._elapsed += dt
        tick_cooldown(self._emitter, dt)

        self._controller.move_input = (1.0 if self._held_right else 0.0) - (
            1.0 if self._held_left else 0.0
        )
        if not self._player.reached_exit:
            self._controller.update(dt)

        self._pulses.update(dt)
        self._memory.decay(dt)
        self._creatures.update(dt, self._player.position)
        if self._creatures.struck_by is not None:
            self._on_spider_hit(self._creatures.struck_by.position)

        if (self._player.position - self._layout.exit_position).length < 26.0:
            self._player.reached_exit = True

        if self._player_light is not None:
            self._player_light.get_component(Transform).position = self._player.position
        if self._lighting is not None:
            self._lighting.update(dt)

        self._follow_camera(dt)

    def _follow_camera(self, dt: float) -> None:
        """Ease the view toward the player, clamped to the cave's bounds.

        Clamped here rather than through `Camera2D.follow` because the
        engine's camera has no level-bounds constraint, and without one the
        view slides off the map at the edges and shows empty black -- which
        in a game about darkness is indistinguishable from a bug.
        """
        assert self.camera is not None
        half_w, half_h = WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2
        desired = Vector2(
            min(
                max(self._player.position.x, half_w), self._layout.world_width - half_w
            ),
            min(
                max(self._player.position.y, half_h),
                self._layout.world_height - half_h,
            ),
        )
        self._camera_target = self._camera_target.lerp(desired, min(1.0, dt * 6.0))
        self.camera.position = self._camera_target

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the cave, then drive the lighting half of the pipeline."""
        offset = self._camera_offset()

        render.draw_cave(
            world_renderer,
            self._layout,
            self._faces,
            self._formations,
            self._memory.brightness,
            self._pulses.scream_amount,
            offset,
        )
        render.draw_atmosphere(
            world_renderer,
            self._motes,
            self._memory.brightness,
            offset,
            self._elapsed,
        )
        render.draw_exit(
            world_renderer, self._layout.exit_position, offset, self._elapsed
        )

        for spider in self._creatures.spiders:
            render.draw_spider(
                world_renderer,
                spider.position,
                self._pulses.lit_amount(spider.position),
                offset,
                spider.agitated,
            )
        for bat in self._creatures.bats:
            render.draw_bat(
                world_renderer,
                bat.position,
                max(self._pulses.lit_amount(bat.position), bat.agitation),
                offset,
                bat.phase,
            )

        render.draw_player(
            world_renderer,
            self._player.position,
            self._player.facing,
            offset,
            self._elapsed,
            self._player.call_flash,
            self._player.hurt_flash,
        )
        self._draw_hud(world_renderer)
        world_renderer.end_frame()

        self._run_lighting_passes()

    def _camera_offset(self) -> Vector2:
        assert self.camera is not None
        return self.camera.position - Vector2(WINDOW_WIDTH / 2, WINDOW_HEIGHT / 2)

    def _run_lighting_passes(self) -> None:
        """Execute light -> pulse -> composite -> post.

        `Application._render_with_graph()` runs only the graph's `final`
        pass, never the middle, so the scene drives the rest itself and
        leaves `final` to blit the composed result to the screen.
        """
        graph = self.container.get(RenderGraph)
        assert self.camera is not None

        rings = [
            PulseRing(
                position=pulse.origin,
                radius=pulse.radius,
                color=SCREAM_COLOR if pulse.is_scream else CHIRP_COLOR,
                intensity=(4.6 if pulse.is_scream else 3.4) * pulse.intensity,
                thickness=0.13 if pulse.is_scream else 0.085,
            )
            for pulse in self._pulses.active
        ]

        for name in ("light", "pulse", "composite", "post_process"):
            render_pass = graph.get_pass(name)
            if render_pass is None:
                continue
            if name == "light":
                render_pass.set_camera(self.camera)
            elif name == "pulse":
                render_pass.set_camera(self.camera)
                render_pass.set_rings(rings)
            render_pass.execute(graph.ctx, graph)

    # ---- HUD ----------------------------------------------------------

    def _draw_hud(self, renderer: IRenderer) -> None:
        """Draw the HUD straight to the screen, after compositing.

        Drawn into the world framebuffer, before compositing, rather than
        over the finished frame: the world FBO is screen-sized and the
        camera offset is applied by hand, so raw screen coordinates here
        stay put while the cave scrolls. The ambient floor is high enough
        that the multiply leaves it perfectly readable, and it picks up a
        little bloom, which suits the tone.
        """
        renderer.draw_text(
            "MOURISCO: RESSONÂNCIA", Vector2(18, 14), _UI_ACCENT, size=18
        )
        renderer.draw_text(
            "[SPACE] chirp   [S] scream   [A/D] move   [W] jump   [R] restart",
            Vector2(18, 38),
            _UI_DIM,
            size=14,
        )
        renderer.draw_text(
            f"CALLS  {self._pulse_count}", Vector2(18, 60), _UI_TEXT, size=14
        )

        ready = self._emitter.is_ready
        width = 92
        filled = (
            width
            if ready
            else int(
                width
                * (
                    1.0
                    - self._emitter.cooldown_remaining
                    / max(self._emitter.cooldown, 0.001)
                )
            )
        )
        renderer.draw_rect(Rect(18, 80, width, 6), Color(40, 54, 66))
        renderer.draw_rect(Rect(18, 80, filled, 6), _UI_ACCENT if ready else _UI_DIM)

        if self._player.reached_exit:
            renderer.draw_rect(Rect(280, 250, 400, 92), Color(12, 20, 26, 220))
            renderer.draw_rect(Rect(280, 250, 400, 92), _UI_ACCENT, width=2)
            renderer.draw_text(
                "OUT OF THE DARK", Vector2(336, 268), _UI_ACCENT, size=28
            )
            renderer.draw_text(
                f"{self._pulse_count} calls    [R] again",
                Vector2(360, 306),
                _UI_TEXT,
                size=16,
            )
