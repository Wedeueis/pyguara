"""Concrete scene implementations for the game."""

import pygame

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import UIRenderer
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.components.rigid_body import RigidBody
from pyguara.physics.components.collider import Collider
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.types import BodyType, ShapeType
from pyguara.scene.base import Scene
from pyguara.ui.components import Button, Label, Panel
from pyguara.ui.manager import UIManager


class GameplayScene(Scene):
    """
    The main gameplay scene.

    Manages its own Physics World, ECS Entities, and UI.
    """

    def __init__(self, name: str, event_dispatcher: EventDispatcher) -> None:
        """Initialize the gameplay scene and its local systems."""
        super().__init__(name, event_dispatcher)

        # 1. Initialize Scene-Specific Systems
        self.physics_engine = PymunkEngine()
        self.physics_system = PhysicsSystem(self.physics_engine, event_dispatcher)

        self.ui_manager = UIManager(event_dispatcher)
        self.fps_label: Label = Label("FPS: 0")

    def on_enter(self) -> None:
        """Call when the scene becomes active."""
        print(f"[{self.name}] Entering Scene...")

        self._create_world()
        self._setup_ui()

    def on_exit(self) -> None:
        """Call when leaving the scene."""
        print(f"[{self.name}] Exiting Scene...")

    def update(self, dt: float) -> None:
        """Scene Logic Loop."""
        # 1. Update Physics
        physics_entities = list(
            self.entity_manager.get_entities_with(Transform, RigidBody)
        )
        self.physics_system.update(physics_entities, dt)

        # 2. Update UI
        self.ui_manager.update(dt)

        # 3. Update FPS Label
        self.fps_label.set_text(f"Entities: {len(physics_entities)}")

    def render(self, renderer: UIRenderer) -> None:
        """Scene Render Loop."""
        # 1. Debug Render Physics
        if hasattr(renderer, "_surface"):
            surface = renderer._surface

            for entity in self.entity_manager.get_entities_with(Transform, Collider):
                pos = entity.transform.position
                dims = entity.collider.dimensions

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
                    color = (
                        (100, 255, 100)
                        if entity.rigid_body.body_type == BodyType.DYNAMIC
                        else (255, 100, 100)
                    )
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
        # Fixed: correct args for Collider
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
        if player and player.rigid_body.handle:
            player.rigid_body.handle.position = Vector2(640, 100)
            player.rigid_body.handle.velocity = Vector2(0, 0)

        box = self.entity_manager.get_entity("box_1")
        if box and box.rigid_body.handle:
            box.rigid_body.handle.position = Vector2(600, 0)
            box.rigid_body.handle.velocity = Vector2(0, 0)
