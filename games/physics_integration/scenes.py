"""Module 5: Physics Scene.

Demonstrates physics simulation with Pymunk backend.
"""

from pyguara.scene.base import Scene
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.common.types import Vector2, Color, Rect
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.physics.components import RigidBody, Collider
from pyguara.physics.types import BodyType
from pyguara.common.components import Transform
from games.physics_integration.components import BoxSprite


class PhysicsScene(Scene):
    """A scene with falling boxes and a static floor."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the scene."""
        super().__init__("PhysicsScene", event_dispatcher)
        self.physics_system = None

    def on_enter(self) -> None:
        """Create physics world and entities."""
        print("PhysicsScene entered! Watch the box fall.")

        # 1. Initialize Physics System
        physics_engine = self.container.get(IPhysicsEngine)
        self.physics_system = PhysicsSystem(
            engine=physics_engine,
            entity_manager=self.entity_manager,
            event_dispatcher=self.event_dispatcher,
        )

        # Configure gravity (Positive Y is down)
        physics_engine.gravity = Vector2(0, 900)

        # 2. Create Ground (Static)
        ground = self.entity_manager.create_entity("ground")
        ground.add_component(Transform(position=Vector2(400, 550)))
        ground.add_component(RigidBody(body_type=BodyType.STATIC))
        ground.add_component(Collider(dimensions=[800, 20]))
        ground.add_component(
            BoxSprite(color=Color(100, 100, 100), size=Vector2(800, 20))
        )

        # 3. Create Falling Box (Dynamic)
        box = self.entity_manager.create_entity("box")
        box.add_component(
            Transform(position=Vector2(400, 100), rotation=45.0)
        )  # Rotated!
        box.add_component(RigidBody(body_type=BodyType.DYNAMIC, mass=10))
        box.add_component(Collider(dimensions=[50, 50]))
        box.add_component(BoxSprite(color=Color(255, 0, 0), size=Vector2(50, 50)))

        print(f"Created entities. Gravity set to {physics_engine.gravity}")

    def on_exit(self) -> None:
        """Clean up physics."""
        if self.physics_system:
            self.physics_system.cleanup()

    def fixed_update(self, fixed_dt: float) -> None:
        """Step physics simulation."""
        # Step the physics simulation
        if self.physics_system:
            self.physics_system.update(fixed_dt)

    def update(self, dt: float) -> None:
        """Update logic."""
        pass

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render entities."""
        world_renderer.clear(Color(30, 30, 30))

        # Render Sprites
        # Note: We aren't handling rotation in this simple render loop,
        # but the physics system IS updating the Transform rotation.
        # To see rotation, we need a renderer that supports it.
        # PygameBackend.draw_rect doesn't support rotation easily.
        # But we can see position update.

        for entity in self.entity_manager.get_entities_with(Transform, BoxSprite):
            trans = entity.get_component(Transform)
            sprite = entity.get_component(BoxSprite)

            # Simple unrotated rect for debug
            # Center the rect on the position (Transform is usually center for physics)
            rect = Rect(
                trans.position.x - sprite.size.x / 2,
                trans.position.y - sprite.size.y / 2,
                sprite.size.x,
                sprite.size.y,
            )
            world_renderer.draw_rect(rect, sprite.color)
