"""Main application entry point and engine integration."""

import pygame

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.graphics.window import Window, WindowConfig
from pyguara.graphics.backends.pygame.pygame_window import PygameWindow
from pyguara.input.manager import InputManager
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.components import RigidBody, Collider
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.types import BodyType, ShapeType
from pyguara.scene.manager import SceneManager
from pyguara.game.scenes import GameplayScene
from pyguara.ui.components import Label, Panel
from pyguara.ui.manager import UIManager


class GameEngine:
    """Core game engine class managing the main loop and subsystems."""

    def __init__(self) -> None:
        """Initialize the game engine, window, and subsystems."""
        # 1. Window System
        window_config = WindowConfig()
        pygame_window = PygameWindow()
        self.window = Window(window_config, pygame_window)
        self.window.create()

        self.clock = pygame.time.Clock()

        # 2. Core Services
        self.event_dispatcher = EventDispatcher()
        self.input_manager = InputManager(self.event_dispatcher)

        # 3. Subsystems
        self.entity_manager = EntityManager()

        self.physics_engine = PymunkEngine()
        self.physics_system = PhysicsSystem(self.physics_engine, self.event_dispatcher)

        # 4. Rendering & UI
        self.world_renderer = PygameBackend(self.window.native_handle)
        self.ui_renderer = PygameUIRenderer(self.window.native_handle)
        self.ui_manager = UIManager(self.event_dispatcher)

        # 5. Scene Management
        self.scene_manager = SceneManager()

        # Initialize Scene
        game_scene = GameplayScene("game", self.event_dispatcher)
        self.scene_manager.register(game_scene)
        self.scene_manager.switch_to("game")

        # Setup Test Entities (Fallback if scene not used)
        self._setup_world()
        self._setup_ui()

    def _setup_world(self) -> None:
        """Create initial game entities (Test)."""
        player = self.entity_manager.create_entity("player_test")
        player.add_component(Transform(position=Vector2(100, 100)))
        player.add_component(RigidBody(body_type=BodyType.DYNAMIC, mass=1.0))
        # Fixed dimensions
        player.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[32, 32]))

        floor = self.entity_manager.create_entity("floor_test")
        floor.add_component(Transform(position=Vector2(640, 600)))
        floor.add_component(RigidBody(body_type=BodyType.STATIC))
        floor.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[1280, 50]))

    def _setup_ui(self) -> None:
        """Configure the initial UI layout (Test)."""
        panel = Panel(position=Vector2(10, 200), size=Vector2(200, 50))
        self.ui_manager.add_element(panel)

        self.fps_label = Label("Engine FPS: 0", position=Vector2(10, 10))
        panel.add_child(self.fps_label)

    def run(self) -> None:
        """Start the main game loop."""
        while self.window.is_open:
            dt = self.clock.tick(60) / 1000.0

            # 1. Process Input
            for event in self.window.poll_events():
                self.input_manager.process_event(event)

            # 2. Update Logic
            self.update(dt)

            # 3. Render
            self.render()

        self.window.close()

    def update(self, dt: float) -> None:
        """Update game state."""
        # Update Global UI
        self.ui_manager.update(dt)
        self.fps_label.set_text(f"Engine FPS: {self.clock.get_fps():.0f}")

        # Update Global Physics (Test entities)
        physics_entities = list(
            self.entity_manager.get_entities_with(Transform, RigidBody)
        )
        self.physics_system.update(physics_entities, dt)

        # Update Scenes
        self.scene_manager.update(dt)

    def render(self) -> None:
        """Render the current frame."""
        # self.window.clear(Color(30, 30, 30))

        # Render Scene
        self.scene_manager.render(self.world_renderer, self.ui_renderer)

        # Render Global UI
        self.ui_manager.render(self.ui_renderer)

        self.window.present()


if __name__ == "__main__":
    app = GameEngine()
    app.run()
