"""Main application entry point and engine integration."""

import pygame

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.input.manager import InputManager
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.components.rigid_body import RigidBody
from pyguara.physics.components.collider import Collider
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.types import BodyType, ShapeType
from pyguara.ui.components import Button, Label, Panel
from pyguara.ui.manager import UIManager


class GameEngine:
    """Core game engine class managing the main loop and subsystems."""

    def __init__(self) -> None:
        """Initialize the game engine, window, and subsystems."""
        pygame.init()
        self.window = pygame.display.set_mode((1280, 720))
        self.running = True
        self.clock = pygame.time.Clock()

        # 1. Core Event & Input
        self.event_dispatcher = EventDispatcher()
        self.input_manager = InputManager(self.event_dispatcher)

        # 2. ECS (The Data)
        self.entity_manager = EntityManager()

        # 3. Physics (The Logic)
        self.physics_engine = PymunkEngine()  # The Adapter
        self.physics_system = PhysicsSystem(
            engine=self.physics_engine, event_dispatcher=self.event_dispatcher
        )

        # 4. UI (The View)
        self.ui_renderer = PygameUIRenderer(self.window)
        self.ui_manager = UIManager(self.event_dispatcher)

        # Setup initial state
        self._setup_bindings()
        self._setup_world()
        self._setup_ui()

    def _setup_bindings(self) -> None:
        """Configure input bindings."""
        # Example: Quit on ESC
        # You would bind keys to Semantic Actions here
        pass

    def _setup_world(self) -> None:
        """Create initial game entities."""
        # --- Create Player ---
        player = self.entity_manager.create_entity("player")
        player.add_component(Transform(position=Vector2(100, 100)))
        player.add_component(RigidBody(body_type=BodyType.DYNAMIC))
        player.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[32, 32]))

        # --- Create Floor ---
        floor = self.entity_manager.create_entity("floor")
        floor.add_component(Transform(position=Vector2(640, 600)))
        floor.add_component(RigidBody(body_type=BodyType.STATIC))
        floor.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[1280, 50]))

    def _setup_ui(self) -> None:
        """Configure the initial UI layout."""
        panel = Panel(position=Vector2(10, 10), size=Vector2(200, 100))
        self.ui_manager.add_element(panel)

        fps_label = Label("FPS: 0", position=Vector2(10, 10))
        panel.add_child(fps_label)
        self.fps_label = fps_label  # Keep ref to update later

        btn = Button("Reset Physics", position=Vector2(10, 40))
        btn.on_click = lambda e: self._reset_physics()
        panel.add_child(btn)

    def _reset_physics(self) -> None:
        """Call a callback to reset player position."""
        player = self.entity_manager.get_entity("player")
        if player and player.rigid_body.handle:
            player.rigid_body.handle.position = Vector2(100, 100)
            player.rigid_body.handle.velocity = Vector2(0, 0)

    def run(self) -> None:
        """Start the main game loop."""
        while self.running:
            dt = self.clock.tick(60) / 1000.0

            # 1. Process Input
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                self.input_manager.process_event(event)

            # 2. Update Logic
            self.update(dt)

            # 3. Render
            self.render()

        pygame.quit()

    def update(self, dt: float) -> None:
        """Update game state and subsystems."""
        # Update UI
        self.ui_manager.update(dt)
        self.fps_label.set_text(f"FPS: {self.clock.get_fps():.0f}")

        # Update Physics
        # Query ECS for entities that obey physics
        physics_entities = list(
            self.entity_manager.get_entities_with(Transform, RigidBody)
        )
        self.physics_system.update(physics_entities, dt)

        # (Future) Update Gameplay Systems...
        # self.gameplay_system.update(self.entity_manager.get_entities_with(Health), dt)

    def render(self) -> None:
        """Render the current frame."""
        self.window.fill((30, 30, 30))

        # --- Debug Render Physics Entities ---
        # In a real engine, you'd have a RenderingSystem that queries SpriteComponent
        # For now, we just draw simple rects where the physics bodies are
        for entity in self.entity_manager.get_entities_with(Transform, Collider):
            pos = entity.transform.position
            # Simple debug draw
            dims = entity.collider.dimensions
            rect = pygame.Rect(
                int(pos.x - dims[0] / 2),
                int(pos.y - dims[1] / 2),
                int(dims[0]),
                int(dims[1]),
            )
            pygame.draw.rect(self.window, (100, 200, 100), rect, 2)

        # Render UI on top
        self.ui_manager.render(self.ui_renderer)

        pygame.display.flip()


if __name__ == "__main__":
    app = GameEngine()
    app.run()
