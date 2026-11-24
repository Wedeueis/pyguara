"""Correição: a calango in the caatinga, and an army-ant raid closing in.

Everything on screen, the ground, the ants and the calango, is an entity
with a `Sprite`, drawn by the base `Scene.render`: the engine's own sprite
path, which is what this demo exists to load. The raid's size is the
`ants` argument, so the same scene runs at 1,000 or at 10,000.

Keys: WASD or the arrows to move; the calango pulses on its own. Until a
key is pressed it walks a loop by itself.
"""

from __future__ import annotations

import math

from examples.correicao.bootstrap import SCREEN_HEIGHT, SCREEN_WIDTH
from examples.correicao.components import PlayerState
from examples.correicao.systems import (
    PULSE_FLASH,
    PULSE_RADIUS,
    WORLD_SIZE,
    CombatSystem,
    HordeSpawner,
    PlayerSystem,
)
from pyguara.ai.flocking_system import FlockingSystem
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.components.animation import (
    AnimationClip,
    Animator,
    add_clip,
    play_clip,
)
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input import keys
from pyguara.input.events import OnActionEvent
from pyguara.input.types import ActionType, InputDevice
from pyguara.random.service import RandomService
from pyguara.resources.manager import ResourceManager
from pyguara.resources.types import Texture
from pyguara.scene.base import Scene

ASSETS = "examples/correicao/assets"
DEFAULT_ANTS = 2000
GROUND_DECALS = 4000

GROUND = Color(196, 168, 120)
PULSE = Color(250, 236, 170)
TEXT = Color(40, 28, 18)

# The flock is steered before the fight reads it, and both before the
# calango's sprite follows it; the engine's own systems run at 100 to 399.
_PRIORITY_PLAYER = 400
_PRIORITY_SPAWN = 410
_PRIORITY_FLOCK = 420
_PRIORITY_COMBAT = 430

_MOVES = {
    "move_up": (keys.W, keys.UP),
    "move_down": (keys.S, keys.DOWN),
    "move_left": (keys.A, keys.LEFT),
    "move_right": (keys.D, keys.RIGHT),
}


class HordeScene(Scene):
    """The raid: one calango, `ants` ants, and a world about five screens wide."""

    def __init__(
        self,
        event_dispatcher: EventDispatcher | None = None,
        *,
        ants: int = DEFAULT_ANTS,
        autopilot: bool = True,
    ) -> None:
        """Build the scene; the world is made in `on_enter`.

        Args:
            event_dispatcher: The engine's event bus, or None to be given it.
            ants: How many ants the raid keeps.
            autopilot: Whether the calango walks its loop until a key is
                pressed.
        """
        super().__init__("HordeScene", event_dispatcher)
        self.ants = ants
        self.player = PlayerState(position=Vector2(WORLD_SIZE / 2, WORLD_SIZE / 2))
        self._autopilot = autopilot
        self._held: dict[str, bool] = dict.fromkeys(_MOVES, False)
        self.spawner: HordeSpawner | None = None
        self.player_system: PlayerSystem | None = None
        self._player_entity_id = ""

    def on_enter(self) -> None:
        """Scatter the ground, place the calango and start the raid."""
        assert self.camera is not None and self.container is not None
        resources = self.container.get(ResourceManager)
        rng = self.container.get(RandomService).stream("correicao")

        def texture(name: str) -> Texture:
            return resources.load(f"{ASSETS}/{name}.png", Texture)  # type: ignore[type-abstract]

        view_radius = math.hypot(SCREEN_WIDTH, SCREEN_HEIGHT) / 2
        self._scatter_ground([texture("tuft"), texture("stone")], rng)
        self._place_player([texture("calango_0"), texture("calango_1")])

        self.player_system = PlayerSystem(self.player, autopilot=self._autopilot)
        self.spawner = HordeSpawner(
            self.entity_manager,
            self.player,
            [texture("ant_0"), texture("ant_1")],
            rng,
            target=self.ants,
            view_radius=view_radius,
        )
        manager = self.system_manager
        manager.register(self.player_system, priority=_PRIORITY_PLAYER)
        manager.register(self.spawner, priority=_PRIORITY_SPAWN)
        manager.register(
            FlockingSystem(self.entity_manager, cell_size=26.0),
            priority=_PRIORITY_FLOCK,
        )
        manager.register(
            CombatSystem(
                self.entity_manager,
                self.player,
                self.spawner,
                view_radius=view_radius,
            ),
            priority=_PRIORITY_COMBAT,
        )
        self._bind_keys()
        self.event_dispatcher.subscribe(OnActionEvent, self._on_action)

    def on_exit(self) -> None:
        """Stop listening for the movement keys."""
        self.event_dispatcher.unsubscribe(OnActionEvent, self._on_action)

    def _scatter_ground(self, decals: list[Texture], rng: RandomStream) -> None:
        """Strew grass and stones over the whole world, most of it off screen."""
        for _ in range(GROUND_DECALS):
            entity = self.entity_manager.create_entity()
            entity.add_component(
                Transform(
                    position=Vector2(
                        round(rng.uniform(0.0, WORLD_SIZE)),
                        round(rng.uniform(0.0, WORLD_SIZE)),
                    )
                )
            )
            entity.add_component(Sprite(texture=rng.choice(decals), layer=0))

    def _place_player(self, frames: list[Texture]) -> None:
        """Create the calango's entity, which follows `self.player` each frame."""
        entity = self.entity_manager.create_entity("calango")
        entity.add_component(Transform(position=self.player.position))
        sprite = Sprite(texture=frames[0], layer=20)
        entity.add_component(sprite)
        animator = Animator(sprite)
        add_clip(animator, AnimationClip(name="walk", frames=frames, frame_rate=6.0))
        play_clip(animator, "walk")
        entity.add_component(animator)
        self._player_entity_id = entity.id

    def _bind_keys(self) -> None:
        manager = self.input_manager
        for action, codes in _MOVES.items():
            manager.register_action(action, ActionType.HOLD)
            for code in codes:
                manager.bind_input(InputDevice.KEYBOARD, code, action)

    def _on_action(self, event: OnActionEvent) -> None:
        if event.action_name in self._held:
            self._held[event.action_name] = event.value > 0

    def update(self, dt: float) -> None:
        """Steer the calango by the held keys, and keep the camera on it.

        Args:
            dt: Seconds since the last frame.
        """
        assert self.player_system is not None and self.camera is not None
        held = self._held
        self.player_system.move_direction = Vector2(
            float(held["move_right"]) - float(held["move_left"]),
            float(held["move_down"]) - float(held["move_up"]),
        )
        calango = self.entity_manager.get_entity(self._player_entity_id)
        if calango is not None:
            calango.get_component(Transform).position = self.player.position
            heading = self.player.heading
            calango.get_component(Sprite).rotation = math.degrees(
                math.atan2(heading.y, heading.x)
            )
        # On whole pixels, so pixel art does not shimmer as the camera moves.
        position = self.player.position
        self.camera.position = Vector2(round(position.x), round(position.y))

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Draw the ground, every sprite, the pulse ring and the counts.

        Args:
            world_renderer: Draws the world.
            ui_renderer: Draws the counts.
        """
        assert self.camera is not None
        world_renderer.clear(GROUND)
        super().render(world_renderer, ui_renderer)
        state = self.player
        if state.pulse_flash > 0.0:
            screen = self.camera.world_to_screen(state.position)
            centre = Vector2(round(screen.x), round(screen.y))
            grown = 1.0 - state.pulse_flash / PULSE_FLASH
            world_renderer.draw_circle(
                centre, PULSE_RADIUS * (0.6 + 0.4 * grown), PULSE, width=3
            )
        alive = self.spawner.alive if self.spawner is not None else 0
        ui_renderer.draw_text(
            f"ants {alive}   kills {state.kills}   health {state.health:.0f}"
            f"   overrun {state.overruns}",
            Vector2(12, 10),
            TEXT,
            18,
        )
