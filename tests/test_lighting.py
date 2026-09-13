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

import math

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Color, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.lighting.components import AmbientLight, LightSource, LightType
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


def make_light_system(light: LightSource) -> LightingSystem:
    """A system holding one light at the origin."""
    entity_manager = EntityManager()
    entity = entity_manager.create_entity()
    entity.add_component(Transform(position=Vector2(0, 0)))
    entity.add_component(light)
    return LightingSystem(entity_manager)


class TestLightShapeData:
    """What the CPU hands the shader. Whether the resulting cone *looks*
    right is `tests/integration/test_light_shapes_pixels.py`'s job."""

    def test_the_light_type_reaches_the_light_data(self) -> None:
        system = make_light_system(LightSource(light_type=LightType.SPOT))

        system.update(0.0)

        assert system.lights[0].light_type == float(LightType.SPOT.value)

    def test_the_half_angle_cosine_is_precomputed_on_the_cpu(self) -> None:
        """`light.frag` compares dot products; it must not call `cos` once
        per fragment for a value that changes once per frame at most."""
        system = make_light_system(LightSource(spot_angle=60.0))

        system.update(0.0)

        assert system.lights[0].spot_cos_half_angle == pytest.approx(
            math.cos(math.radians(30.0))
        )

    def test_the_spot_direction_is_converted_to_radians(self) -> None:
        system = make_light_system(LightSource(spot_direction=90.0))

        system.update(0.0)

        assert system.lights[0].spot_direction == pytest.approx(math.pi / 2)

    def test_the_shape_data_survives_the_screen_space_transform(self) -> None:
        """`collect_lights_screen_space` rebuilds every `LightData`, so a
        field left out there is a field the shader never sees."""
        system = make_light_system(
            LightSource(light_type=LightType.SPOT, spot_angle=60.0, spot_direction=45.0)
        )
        system.update(0.0)

        screen = system.collect_lights_screen_space(1.0, Vector2(0, 0))[0]

        assert screen.light_type == float(LightType.SPOT.value)
        assert screen.spot_direction == pytest.approx(math.radians(45.0))
        assert screen.spot_cos_half_angle == pytest.approx(math.cos(math.radians(30.0)))


class TestFlicker:
    """Resolved on the CPU, in `update(dt)`, which is what makes it
    testable at all -- the shader alternative would need a GL context for
    every one of these."""

    def test_a_light_without_flicker_keeps_its_intensity(self) -> None:
        system = make_light_system(LightSource(intensity=0.8))

        system.update(0.016)

        assert system.lights[0].intensity == pytest.approx(0.8)

    def test_flicker_varies_the_intensity_over_time(self) -> None:
        system = make_light_system(
            LightSource(intensity=1.0, flicker_enabled=True, flicker_speed=10.0)
        )

        seen = []
        for _ in range(20):
            system.update(0.016)
            seen.append(system.lights[0].intensity)

        assert len(set(seen)) > 1

    def test_flicker_stays_within_flicker_intensity_of_the_base(self) -> None:
        """The field is a *bound*, not a scale -- a torch set to vary by
        10% must not gutter to black."""
        base, amount = 1.0, 0.1
        system = make_light_system(
            LightSource(
                intensity=base,
                flicker_enabled=True,
                flicker_speed=37.0,  # Deliberately not a multiple of dt.
                flicker_intensity=amount,
            )
        )

        for _ in range(400):
            system.update(0.016)
            assert abs(system.lights[0].intensity - base) <= base * amount + 1e-6

    def test_flicker_never_goes_negative(self) -> None:
        """A flicker wider than the base would otherwise drive the light
        past black and back up as a negative additive contribution."""
        system = make_light_system(
            LightSource(intensity=0.2, flicker_enabled=True, flicker_intensity=5.0)
        )

        for _ in range(200):
            system.update(0.016)
            assert system.lights[0].intensity >= 0.0

    def test_two_lights_do_not_flicker_in_lockstep(self) -> None:
        """A row of torches sharing one phase reads as a single blinking
        object rather than as several fires."""
        entity_manager = EntityManager()
        for _ in range(2):
            entity = entity_manager.create_entity()
            entity.add_component(Transform(position=Vector2(0, 0)))
            entity.add_component(
                LightSource(flicker_enabled=True, flicker_intensity=0.5)
            )
        system = LightingSystem(entity_manager)

        system.update(0.016)

        first, second = system.lights[0].intensity, system.lights[1].intensity
        assert first != pytest.approx(second)

    def test_the_starting_phase_is_stable_across_processes(self) -> None:
        """Derived from a checksum of the entity id, not `hash()`, which
        is salted per process -- a light that flickered differently on
        every run would break replay reproduction."""
        entity_manager = EntityManager()
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        entity.add_component(LightSource(flicker_enabled=True, flicker_intensity=0.5))

        first = LightingSystem(entity_manager)
        first.update(0.016)
        second = LightingSystem(entity_manager)
        second.update(0.016)

        assert first.lights[0].intensity == pytest.approx(second.lights[0].intensity)

    def test_a_removed_light_does_not_leave_its_phase_behind(self) -> None:
        """The phase dict is keyed by entity id; without pruning it grows
        for the life of the scene."""
        entity_manager = EntityManager()
        entity = entity_manager.create_entity()
        entity.add_component(Transform(position=Vector2(0, 0)))
        entity.add_component(LightSource(flicker_enabled=True))
        system = LightingSystem(entity_manager)
        system.update(0.016)
        assert system._flicker_phases

        entity_manager.remove_entity(entity.id)
        system.update(0.016)

        assert system._flicker_phases == {}
