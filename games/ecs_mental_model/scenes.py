"""Module 2: ECS Scene

Composition root. We wire up Systems and create initial Entities here.
"""

from games.ecs_mental_model.components import Sprite, Transform
from games.ecs_mental_model.systems import MovementSystem
from pyguara.common.types import Color, Rect, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.protocols import IRenderer, UIRenderer
from pyguara.scene.base import Scene

# SystemManager runs lower numbers first. The engine registers its own four
# systems in the 100-399 band (see Scene.resolve_dependencies), so game
# systems go after them unless they have a reason not to.
_PRIORITY_MOVEMENT = 400


class ECSScene(Scene):
    """Demonstrates Entity creation and System execution."""

    def __init__(self, event_dispatcher: EventDispatcher):
        super().__init__("ECSScene", event_dispatcher)

    def on_enter(self) -> None:
        print("ECSScene entered! Creating entities...")

        # 1. Register Systems
        # Every Scene owns a SystemManager. Registering here rather than
        # calling update() by hand is what "System" means in this engine:
        # SceneManager ticks the whole set every fixed step, in priority
        # order, and cleans them up when the scene exits.
        self.system_manager.register(
            MovementSystem(self.entity_manager), priority=_PRIORITY_MOVEMENT
        )

        # 2. Create Entities
        # We spawn a "Hero" square
        hero = self.entity_manager.create_entity("hero")
        hero.add_component(Transform(position=Vector2(100, 100)))
        hero.add_component(Sprite(color=Color(255, 0, 0), size=Vector2(50, 50)))

        print(f"Created entity: {hero.id} with Transform and Sprite")

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        # Nothing here on purpose. MovementSystem is registered with
        # self.system_manager, so it is already being ticked -- this is the
        # difference between "a class with an update() method" and a System.
        pass

    def render(self, world_renderer: IRenderer, ui_renderer: UIRenderer) -> None:
        # Clear screen
        world_renderer.clear(Color(30, 30, 30))

        # Drawn by hand, with renderer primitives, because this module has
        # no textures: `Sprite` here is a colour and a size we defined
        # ourselves, to show that a Component is just data. The engine's
        # RenderSystem draws `Renderable`s, and a Renderable needs a
        # Texture -- which is module 3's subject. From module 3 on, Scene's
        # own render() does this for you and nothing overrides it.
        for entity in self.entity_manager.get_entities_with(Transform, Sprite):
            transform = entity.get_component(Transform)
            sprite = entity.get_component(Sprite)

            # Draw the rect
            # We use the world_renderer primitive drawing
            rect = Rect(
                transform.position.x, transform.position.y, sprite.size.x, sprite.size.y
            )
            world_renderer.draw_rect(rect, sprite.color)
