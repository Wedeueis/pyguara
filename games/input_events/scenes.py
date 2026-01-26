"""Module 4: Input Scene.

Demonstrates input binding and physics interaction.
"""

from pyguara.scene.base import Scene
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.common.types import Vector2, Color, Rect
from pyguara.input.manager import InputManager
from pyguara.input.types import InputDevice, ActionType
from pyguara.input.keys import SPACE
from games.input_events.components import Transform, Velocity, Sprite
from games.input_events.systems import InputBridgeSystem, PlayerSystem


class InputScene(Scene):
    """Binds keys and simulates jump physics."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the scene."""
        super().__init__("InputScene", event_dispatcher)
        self.input_bridge = None
        self.player_system = None

    def on_enter(self) -> None:
        """Initialize input and entities."""
        print("InputScene entered! Press SPACE to jump.")

        # 1. Setup Input Bindings
        input_manager = self.container.get(InputManager)

        # Register semantic action "jump" that triggers on PRESS
        input_manager.register_action("jump", ActionType.PRESS)

        # Bind keyboard SPACE to "jump" action
        input_manager.bind_input(InputDevice.KEYBOARD, SPACE, "jump")

        # 2. Create Systems
        self.input_bridge = InputBridgeSystem(self.event_dispatcher, player_id="hero")
        self.player_system = PlayerSystem(self.entity_manager, self.event_dispatcher)

        # 3. Create Player Entity
        hero = self.entity_manager.create_entity("hero")
        hero.add_component(Transform(position=Vector2(400, 500)))  # Start on floor
        hero.add_component(Velocity(value=Vector2(0, 0)))
        hero.add_component(Sprite(color=Color(0, 255, 0), size=Vector2(40, 40)))

        print(f"Created player {hero.id} at {hero.get_component(Transform).position}")

    def on_exit(self) -> None:
        """Clean up."""
        pass

    def update(self, dt: float) -> None:
        """Update game logic."""
        if self.player_system:
            self.player_system.update(dt)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render the scene."""
        world_renderer.clear(Color(30, 30, 30))

        # Draw Floor line
        world_renderer.draw_line(
            Vector2(0, 540), Vector2(800, 540), Color(100, 100, 100), width=2
        )

        # Render Player
        for entity in self.entity_manager.get_entities_with(Transform, Sprite):
            transform = entity.get_component(Transform)
            sprite = entity.get_component(Sprite)

            rect = Rect(
                transform.position.x, transform.position.y, sprite.size.x, sprite.size.y
            )
            world_renderer.draw_rect(rect, sprite.color)
