"""Module 4: Input Scene.

Demonstrates input binding and the input-to-gameplay event bridge.
"""

from games.input_events.components import Movement, Sprite, Transform
from games.input_events.systems import InputBridgeSystem, PlayerSystem
from pyguara.common.types import Color, Rect, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.input.keys import SPACE, A, D, S, W
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, InputDevice
from pyguara.scene.base import Scene

# Registered with the scene's own SystemManager, which SceneManager ticks
# every fixed step. Module 2 introduced that; here it is what drives
# PlayerSystem, so nothing in this scene has to call update() by hand.
_PRIORITY_PLAYER = 400


class InputScene(Scene):
    """Binds keys and moves a square with them."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the scene."""
        super().__init__("InputScene", event_dispatcher)
        self.input_bridge = None
        self.player_system = None

    def on_enter(self) -> None:
        """Initialize input and entities."""
        print("InputScene entered! WASD to move, SPACE to dash.")

        # 1. Setup Input Bindings
        input_manager = self.container.get(InputManager)

        # HOLD for the directions: they stay true while the key is down, and
        # the bridge keeps them as state. PRESS for the dash: it happens
        # once, and the bridge turns it into an event.
        for action in ("move_up", "move_down", "move_left", "move_right"):
            input_manager.register_action(action, ActionType.HOLD)
        input_manager.register_action("dash", ActionType.PRESS)

        input_manager.bind_input(InputDevice.KEYBOARD, W, "move_up")
        input_manager.bind_input(InputDevice.KEYBOARD, S, "move_down")
        input_manager.bind_input(InputDevice.KEYBOARD, A, "move_left")
        input_manager.bind_input(InputDevice.KEYBOARD, D, "move_right")
        input_manager.bind_input(InputDevice.KEYBOARD, SPACE, "dash")

        # 2. Create the Player Entity, before the systems that look for it
        hero = self.entity_manager.create_entity("hero")
        hero.add_component(Transform(position=Vector2(400, 300)))
        hero.add_component(Movement(direction=Vector2(0, 0), speed=220.0))
        hero.add_component(Sprite(color=Color(0, 255, 0), size=Vector2(40, 40)))

        # 3. Create Systems
        self.input_bridge = InputBridgeSystem(
            self.entity_manager, self.event_dispatcher, player_id="hero"
        )
        self.player_system = PlayerSystem(self.entity_manager, self.event_dispatcher)
        self.system_manager.register(self.player_system, priority=_PRIORITY_PLAYER)

        print(f"Created player {hero.id} at {hero.get_component(Transform).position}")

    def on_exit(self) -> None:
        """Clean up."""
        pass

    def update(self, dt: float) -> None:
        """Nothing to do per frame.

        `PlayerSystem` is registered with `self.system_manager`, which
        `SceneManager` ticks every fixed step -- so there is nothing to
        call by hand here.
        """

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render the scene."""
        world_renderer.clear(Color(30, 30, 30))

        # Render Player
        for entity in self.entity_manager.get_entities_with(Transform, Sprite):
            transform = entity.get_component(Transform)
            sprite = entity.get_component(Sprite)

            rect = Rect(
                transform.position.x, transform.position.y, sprite.size.x, sprite.size.y
            )
            world_renderer.draw_rect(rect, sprite.color)
