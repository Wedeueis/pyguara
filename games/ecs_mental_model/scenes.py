"""Module 2: ECS Scene

Composition root. We wire up Systems and create initial Entities here.
"""

from pyguara.scene.base import Scene
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.common.types import Vector2, Color, Rect
from games.ecs_mental_model.components import Transform, Sprite
from games.ecs_mental_model.systems import MovementSystem

class ECSScene(Scene):
    """Demonstrates Entity creation and System execution."""
    
    def __init__(self, event_dispatcher: EventDispatcher):
        super().__init__("ECSScene", event_dispatcher)
        self.movement_system = None  # Will be initialized in on_enter

    def on_enter(self) -> None:
        print("ECSScene entered! Creating entities...")
        
        # 1. Initialize Systems
        # Pass the EntityManager (which belongs to the Scene) to the System
        self.movement_system = MovementSystem(self.entity_manager)
        
        # 2. Create Entities
        # We spawn a "Hero" square
        hero = self.entity_manager.create_entity("hero")
        hero.add_component(Transform(position=Vector2(100, 100)))
        hero.add_component(Sprite(color=Color(255, 0, 0), size=Vector2(50, 50)))
        
        print(f"Created entity: {hero.id} with Transform and Sprite")

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        # Run our logic systems
        if self.movement_system:
            self.movement_system.update(dt)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        # Clear screen
        world_renderer.clear(Color(30, 30, 30))
        
        # Simple Rendering Logic (usually this goes in a RenderSystem)
        # Iterate over all entities that have visuals
        for entity in self.entity_manager.get_entities_with(Transform, Sprite):
            transform = entity.get_component(Transform)
            sprite = entity.get_component(Sprite)
            
            # Draw the rect
            # We use the world_renderer primitive drawing
            rect = Rect(
                transform.position.x, 
                transform.position.y, 
                sprite.size.x, 
                sprite.size.y
            )
            world_renderer.draw_rect(rect, sprite.color)
