"""Concrete scene implementations for the game."""

from typing import Optional

import pygame

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import UIRenderer
from pyguara.physics.components import RigidBody, Collider
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.protocols import IPhysicsEngine  # Changed import
from pyguara.physics.types import BodyType, ShapeType
from pyguara.scene.base import Scene
from pyguara.ui.components import Button, Label, Panel
from pyguara.ui.manager import UIManager


class GameplayScene(Scene):
    """
    The main gameplay scene.

    Manages its own Physics System, ECS Entities, and UI.
    """

    def __init__(self, name: str, event_dispatcher: EventDispatcher) -> None:
        """Initialize the gameplay scene and its local systems."""
        super().__init__(name, event_dispatcher)
        self.ui_manager = UIManager(event_dispatcher)
        self.fps_label = Label("FPS: 0")

        # Placeholders
        self.physics_system: Optional[PhysicsSystem] = None

    def on_enter(self) -> None:
        """Call when the scene becomes active."""
        print(f"[{self.name}] Entering Scene...")
        # 1. RESOLVE DEPENDENCIES
        # We grab the global engine from the container we inherited
        if self.container:
            physics_engine = self.container.get(IPhysicsEngine)  # type: ignore[type-abstract]
            self.physics_system = PhysicsSystem(physics_engine, self.event_dispatcher)
        else:
            raise RuntimeError("Scene has no DI Container!")

        self._create_world()
        self._setup_ui()

    def on_exit(self) -> None:
        """Call when leaving the scene."""
        print(f"[{self.name}] Exiting Scene...")

    def update(self, dt: float) -> None:
        """Scene Logic Loop."""
        # 1. Update Physics
        if self.physics_system:
            print("Physics System Active... simulating entities...")
            physics_entities = list(
                self.entity_manager.get_entities_with(Transform, RigidBody)
            )
            self.physics_system.update(physics_entities, dt)

        # 2. Update UI
        self.ui_manager.update(dt)

        # 3. Update FPS Label
        self.fps_label.set_text(f"FPS: {int(1 / dt) if dt > 0 else 0}")
        self.fps_label.set_text(f"Entities: {len(physics_entities)}")

    def render(self, renderer: UIRenderer) -> None:
        """Scene Render Loop."""
        # 1. Debug Render Physics
        # Note: In a real engine, we'd use a dedicated DebugDrawer service
        if hasattr(renderer, "_surface"):
            surface = renderer._surface

            for entity in self.entity_manager.get_entities_with(Transform, Collider):
                # OPTIMIZATION: Use get_component
                pos = entity.get_component(Transform).position
                col = entity.get_component(Collider)
                dims = col.dimensions

                # Handle Circle vs Box render
                if len(dims) == 1:
                    pygame.draw.circle(
                        surface,
                        (100, 255, 100),
                        (int(pos.x), int(pos.y)),
                        int(dims[0]),
                        2,
                    )
                else:
                    rect = pygame.Rect(
                        int(pos.x - dims[0] / 2),
                        int(pos.y - dims[1] / 2),
                        int(dims[0]),
                        int(dims[1]),
                    )

                    # Check body type for color
                    rb = (
                        entity.get_component(RigidBody)
                        if entity.has_component(RigidBody)
                        else None
                    )
                    is_dynamic = rb and rb.body_type == BodyType.DYNAMIC

                    color = (100, 255, 100) if is_dynamic else (255, 100, 100)
                    pygame.draw.rect(surface, color, rect, 2)

        # 2. Render UI
        self.ui_manager.render(renderer)

    # --- Setup Helpers ---

    def _create_world(self) -> None:
        """Populate the ECS with game objects."""
        # -- Floor --
        floor = self.entity_manager.create_entity("floor")
        floor.add_component(Transform(position=Vector2(640, 650)))
        floor.add_component(RigidBody(body_type=BodyType.STATIC))
        floor.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[1280, 50]))

        # -- Player --
        player = self.entity_manager.create_entity("player")
        player.add_component(Transform(position=Vector2(640, 100)))
        player.add_component(RigidBody(body_type=BodyType.DYNAMIC, mass=10.0))
        player.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[40, 40]))

        # -- Random Box --
        box = self.entity_manager.create_entity("box_1")
        box.add_component(Transform(position=Vector2(600, 0)))
        box.add_component(RigidBody(body_type=BodyType.DYNAMIC, mass=5.0))
        box.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[30, 30]))

    def _setup_ui(self) -> None:
        """Create the HUD."""
        panel = Panel(position=Vector2(10, 10), size=Vector2(220, 120))
        self.ui_manager.add_element(panel)

        title = Label("Debug HUD", position=Vector2(10, 10), font_size=20)
        panel.add_child(title)

        self.fps_label = Label("Entities: 0", position=Vector2(10, 40))
        panel.add_child(self.fps_label)

        btn = Button("Reset Physics", position=Vector2(10, 70), size=Vector2(200, 30))
        btn.on_click = lambda e: self._reset_physics()
        panel.add_child(btn)

    def _reset_physics(self) -> None:
        """Call the callback to teleport entities back to start."""
        print("Resetting Physics...")

        player = self.entity_manager.get_entity("player")
        if player:
            rb = player.get_component(RigidBody)
            if rb._body_handle:  # Access backing field directly
                rb._body_handle.position = Vector2(640, 100)
                rb._body_handle.velocity = Vector2(0, 0)

        box = self.entity_manager.get_entity("box_1")
        if box:
            rb = box.get_component(RigidBody)
            if rb._body_handle:
                rb._body_handle.position = Vector2(600, 0)
                rb._body_handle.velocity = Vector2(0, 0)


class TestScene(Scene):
    """Basic test scene for window functionality."""

    def on_enter(self) -> None:
        """Call when the scene becomes active."""
        print("[TestScene] Entered. If you see this, the Scene Manager is working.")
        print("[TestScene] The window should be BLUE with a RED box.")

    def on_exit(self) -> None:
        """Call when leaving the scene."""
        print("[TestScene] Exited.")

    def update(self, dt: float) -> None:
        """Scene Logic Loop."""
        # Simple test: Print to console if Space is pressed
        # This proves the Input System is working
        keys = pygame.key.get_pressed()
        if keys[pygame.K_SPACE]:
            print(f"[TestScene] Input Alive! dt={dt:.4f}")

    def render(self, renderer: UIRenderer) -> None:
        """Scene Render Loop."""
        # Access the raw Pygame surface to draw directly
        # This proves the Window and Render Pipeline are working
        if hasattr(renderer, "_surface"):
            surface = renderer._surface

            # 1. Fill Background (Blue)
            surface.fill((50, 50, 200))

            # 2. Draw a Box (Red)
            rect = pygame.Rect(100, 100, 200, 200)
            pygame.draw.rect(surface, (255, 50, 50), rect)

            # 3. Draw diagonal line (White)
            pygame.draw.line(surface, (255, 255, 255), (0, 0), (800, 600), 5)
