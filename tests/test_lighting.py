"""Tests for the 2D lighting system.

The world-to-screen transform is the part worth pinning down. `LightPass`
hands `collect_lights_screen_space` the camera's `screen_offset`, which
already has the camera position subtracted out of it; subtracting the
position a second time inside displaced every light by a whole camera
position. On a camera centred on its viewport -- the ordinary case for a
fixed, screen-space scene -- that threw the entire light map off the left
edge of the frame, so no light lit anything and only the ambient clear
survived. The demo it was found in looked exactly like a scene with
lighting disabled.
"""

from pyguara.common.components import Transform
from pyguara.common.types import Color, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.lighting.components import AmbientLight, LightSource
from pyguara.graphics.lighting.light_system import LightingSystem
from pyguara.graphics.pipeline.viewport import Viewport


def make_system(*positions: Vector2) -> LightingSystem:
    """Build a lighting system holding one light at each position."""
    entity_manager = EntityManager()
    for position in positions:
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=position))
        entity.add_component(LightSource(radius=100.0))

    system = LightingSystem(entity_manager)
    system.update(0.016)
    return system


class TestLightCollection:
    def test_lights_are_collected_from_entities(self) -> None:
        system = make_system(Vector2(10, 20), Vector2(30, 40))

        assert len(system.lights) == 2

    def test_a_disabled_light_is_skipped(self) -> None:
        entity_manager = EntityManager()
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(10, 20)))
        entity.add_component(LightSource(enabled=False))

        system = LightingSystem(entity_manager)
        system.update(0.016)

        assert system.lights == []

    def test_ambient_is_read_from_the_ambient_light_component(self) -> None:
        entity_manager = EntityManager()
        entity = entity_manager.create_entity()
        entity.add_component(AmbientLight(color=Color(100, 200, 250), intensity=0.5))

        system = LightingSystem(entity_manager)
        system.update(0.016)

        red, green, blue = system.get_ambient_normalized()
        assert red == 100 / 255 * 0.5
        assert green == 200 / 255 * 0.5
        assert blue == 250 / 255 * 0.5


class TestScreenSpaceTransform:
    """The transform must be `Camera2D`'s, and only applied once."""

    def test_a_light_lands_where_the_camera_says_it_does(self) -> None:
        """The regression: a centred camera used to displace every light.

        A camera sitting on the middle of its own viewport maps world to
        screen one-to-one, so a light at (300, 200) belongs at (300, 200).
        Subtracting the camera position on top of `screen_offset` put it
        at (-180, -160) -- off-frame, along with every other light.
        """
        viewport = Viewport(0, 0, 960, 720)
        camera = Camera2D(960, 720)
        camera.position = Vector2(480, 360)
        system = make_system(Vector2(300, 200))

        lights = system.collect_lights_screen_space(
            camera.zoom, camera.screen_offset(viewport)
        )

        assert lights[0].position.x == 300
        assert lights[0].position.y == 200

    def test_the_transform_matches_world_to_screen(self) -> None:
        """Any camera, not just a centred one: the same single definition."""
        viewport = Viewport(0, 0, 800, 600)
        camera = Camera2D(800, 600)
        camera.position = Vector2(120, 90)
        world = Vector2(300, 200)
        system = make_system(world)

        lights = system.collect_lights_screen_space(
            camera.zoom, camera.screen_offset(viewport)
        )

        expected = camera.world_to_screen(world, viewport)
        assert lights[0].position.x == expected.x
        assert lights[0].position.y == expected.y

    def test_zoom_scales_the_radius_with_the_position(self) -> None:
        viewport = Viewport(0, 0, 800, 600)
        camera = Camera2D(800, 600)
        camera.zoom = 2.0
        system = make_system(Vector2(100, 50))

        lights = system.collect_lights_screen_space(
            camera.zoom, camera.screen_offset(viewport)
        )

        assert lights[0].radius == 200.0
