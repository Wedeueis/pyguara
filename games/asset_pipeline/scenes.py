"""Module 3: Asset Scene.

Demonstrates loading resources and rendering sprites.
"""

from pyguara.scene.base import Scene
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.common.types import Vector2, Color
from pyguara.resources.manager import ResourceManager
from pyguara.resources.types import Texture
from games.asset_pipeline.components import Transform, Sprite
from games.asset_pipeline.systems import MovementSystem


class AssetScene(Scene):
    """Loads a texture and renders it."""

    def __init__(self, event_dispatcher: EventDispatcher):
        """Initialize the scene."""
        super().__init__("AssetScene", event_dispatcher)
        self.movement_system = None

    def on_enter(self) -> None:
        """Load resources and create entities."""
        print("AssetScene entered! Loading resources...")

        # 1. Get ResourceManager from DI Container
        res_manager = self.container.get(ResourceManager)

        # 2. Load the Texture
        # Thanks to index_directory(), we can just use the filename
        # The meta file "hero.png.meta" will be automatically applied (nearest filter)
        hero_texture = res_manager.load("hero.png", Texture)

        # 3. Create Entity
        self.movement_system = MovementSystem(self.entity_manager)

        hero = self.entity_manager.create_entity("hero")
        hero.add_component(Transform(position=Vector2(100, 100)))
        hero.add_component(Sprite(texture=hero_texture))

        print(f"Created entity {hero.id} with texture: {hero_texture.path}")

    def on_exit(self) -> None:
        """Clean up resources."""
        pass

    def update(self, dt: float) -> None:
        """Update game logic."""
        if self.movement_system:
            self.movement_system.update(dt)

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        """Render the scene."""
        world_renderer.clear(Color(30, 30, 30))

        # Render Sprites
        for entity in self.entity_manager.get_entities_with(Transform, Sprite):
            transform = entity.get_component(Transform)
            sprite = entity.get_component(Sprite)

            # Draw texture at position
            world_renderer.draw_texture(
                sprite.texture,
                transform.position,
                scale=Vector2(10, 10),  # Scale up because 32x32 is small
            )
