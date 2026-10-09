"""Picking: what is under the cursor, and what a marquee caught.

The bug this module exists to not repeat is worth stating, because the
code looked reasonable: `pyguara/tools/gizmos.py` was the only picking
code in the tree, and it compared a **world** position against a
**screen** position with no camera transform, against a hardcoded 32x32
box it invented rather than measured. It worked in a demo whose camera sat
at the origin and nothing else.

So the tests here are mostly about the two things that went wrong there --
measuring real bounds, and agreeing with the camera -- plus the depth
ordering, without which clicking overlapping sprites selects whichever the
ECS happened to iterate first.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.studio.viewport.picking import (
    DEFAULT_PICK_SIZE,
    fallback_bounds,
    iter_pickable,
    marquee_rect,
    pick_at,
    pick_in_region,
    screen_to_world,
    sprite_bounds,
    world_to_panel,
)
from tests.test_scene_serializer import FakeTexture


def _sprite(width: int = 64, height: int = 64, **kwargs: object) -> Sprite:
    """Build a sprite with a measurable texture."""
    return Sprite(texture=FakeTexture("art.png", width, height), **kwargs)


@pytest.fixture
def scene(world: EntityManager) -> EntityManager:
    """A world with sprites of different sizes, layers and positions."""
    big = world.create_entity("big")
    big.add_component(Transform(position=Vector2(0, 0)))
    big.add_component(_sprite(256, 256, layer=0))

    small = world.create_entity("small")
    small.add_component(Transform(position=Vector2(0, 0)))
    small.add_component(_sprite(32, 32, layer=10))

    far = world.create_entity("far")
    far.add_component(Transform(position=Vector2(500, 500)))
    far.add_component(_sprite(64, 64))

    marker = world.create_entity("marker")
    marker.add_component(Transform(position=Vector2(-300, 0)))

    return world


class TestSpriteBounds:
    """Measured from the texture, not assumed."""

    def test_uses_the_texture_size(self) -> None:
        """A 16x16 coin and a 256x256 backdrop are both pickable at their
        real size, which a fixed box cannot do."""
        bounds = sprite_bounds(Transform(), _sprite(16, 16))
        assert bounds == Rect(-8, -8, 16, 16)

    def test_centres_on_the_transform(self) -> None:
        bounds = sprite_bounds(Transform(position=Vector2(100, 50)), _sprite(64, 64))
        assert bounds == Rect(68, 18, 64, 64)

    def test_the_sprite_offset_is_added(self) -> None:
        """A sprite's `position` is an offset from its transform."""
        sprite = _sprite(32, 32, position=Vector2(10, 0))
        bounds = sprite_bounds(Transform(), sprite)
        assert bounds is not None
        assert bounds.x == -6

    def test_transform_scale_is_applied(self) -> None:
        transform = Transform(scale=Vector2(2, 2))
        bounds = sprite_bounds(transform, _sprite(32, 32))
        assert bounds == Rect(-32, -32, 64, 64)

    def test_sprite_scale_multiplies_transform_scale(self) -> None:
        transform = Transform(scale=Vector2(2, 1))
        sprite = _sprite(32, 32, scale=Vector2(2, 1))
        bounds = sprite_bounds(transform, sprite)
        assert bounds == Rect(-64, -16, 128, 32)

    def test_a_negative_scale_still_gives_a_positive_box(self) -> None:
        """A flipped sprite occupies the same area."""
        transform = Transform(scale=Vector2(-1, -1))
        bounds = sprite_bounds(transform, _sprite(32, 32))
        assert bounds == Rect(-16, -16, 32, 32)

    def test_no_sprite_gives_no_bounds(self) -> None:
        assert sprite_bounds(Transform(), None) is None

    def test_a_zero_sized_texture_gives_no_bounds(self) -> None:
        assert sprite_bounds(Transform(), _sprite(0, 0)) is None


class TestFallbackBounds:
    """An entity with nothing but a transform still has to be clickable."""

    def test_is_centred_and_square(self) -> None:
        """A spawn point, a trigger marker, an empty used as a parent."""
        bounds = fallback_bounds(Transform(position=Vector2(100, 100)))
        assert bounds.width == bounds.height == DEFAULT_PICK_SIZE * 2
        assert bounds.x == 100 - DEFAULT_PICK_SIZE

    def test_scales_with_the_transform(self) -> None:
        bounds = fallback_bounds(Transform(scale=Vector2(2, 2)))
        assert bounds.width == DEFAULT_PICK_SIZE * 4

    def test_a_zero_scale_still_gives_a_clickable_box(self) -> None:
        """Otherwise a mistake in a prefab makes an entity unselectable,
        and therefore unfixable in the editor."""
        bounds = fallback_bounds(Transform(scale=Vector2(0, 0)))
        assert bounds.width >= 1


class TestIterPickable:
    """What is eligible, and in what order."""

    def test_includes_every_transform(self, scene: EntityManager) -> None:
        ids = {pick.entity_id for pick in iter_pickable(scene)}
        assert ids == {"big", "small", "far", "marker"}

    def test_an_entity_with_no_sprite_gets_fallback_bounds(
        self, scene: EntityManager
    ) -> None:
        pick = next(p for p in iter_pickable(scene) if p.entity_id == "marker")
        assert pick.bounds.width == DEFAULT_PICK_SIZE * 2

    def test_a_disabled_entity_is_excluded(self, scene: EntityManager) -> None:
        """Clicking something that is not on screen is never what was
        meant."""
        scene.set_entity_enabled("big", False)
        ids = {pick.entity_id for pick in iter_pickable(scene)}
        assert "big" not in ids

    def test_an_invisible_sprite_is_excluded(self, world: EntityManager) -> None:
        entity = world.create_entity("hidden")
        entity.add_component(Transform())
        entity.add_component(_sprite(32, 32, visible=False))
        assert iter_pickable(world) == []

    def test_a_higher_layer_sorts_in_front(self, scene: EntityManager) -> None:
        """So clicking overlapping sprites selects the one actually
        visible."""
        order = [pick.entity_id for pick in iter_pickable(scene)]
        assert order.index("small") < order.index("big")

    def test_a_sprite_sorts_in_front_of_a_bare_marker(
        self, scene: EntityManager
    ) -> None:
        """An invisible marker should not win a click against the thing
        drawn on top of it."""
        order = [pick.entity_id for pick in iter_pickable(scene)]
        assert order.index("small") < order.index("marker")

    def test_z_index_breaks_a_layer_tie(self, world: EntityManager) -> None:
        for name, z in (("under", 0), ("over", 5)):
            entity = world.create_entity(name)
            entity.add_component(Transform())
            entity.add_component(_sprite(32, 32, z_index=z))

        order = [pick.entity_id for pick in iter_pickable(world)]
        assert order == ["over", "under"]

    def test_sort_group_outranks_layer(self, world: EntityManager) -> None:
        held = world.create_entity("held")
        held.add_component(Transform())
        held.add_component(_sprite(32, 32, layer=0, sort_group=1))
        scenery = world.create_entity("scenery")
        scenery.add_component(Transform())
        scenery.add_component(_sprite(32, 32, layer=99, sort_group=0))

        order = [pick.entity_id for pick in iter_pickable(world)]
        assert order == ["held", "scenery"]

    def test_the_order_is_deterministic(self, world: EntityManager) -> None:
        """A viewport whose selection depended on ECS iteration order
        would be maddening to use."""
        for name in ("c", "a", "b"):
            entity = world.create_entity(name)
            entity.add_component(Transform())
            entity.add_component(_sprite(32, 32))

        first = [pick.entity_id for pick in iter_pickable(world)]
        second = [pick.entity_id for pick in iter_pickable(world)]
        assert first == second == ["a", "b", "c"]


class TestPickAt:
    """A single click."""

    def test_finds_the_entity_under_the_point(self, scene: EntityManager) -> None:
        pick = pick_at(scene, Vector2(500, 500))
        assert pick is not None
        assert pick.entity_id == "far"

    def test_returns_none_over_empty_space(self, scene: EntityManager) -> None:
        assert pick_at(scene, Vector2(-9999, -9999)) is None

    def test_the_front_most_wins(self, scene: EntityManager) -> None:
        """Both `big` and `small` contain the origin."""
        pick = pick_at(scene, Vector2(0, 0))
        assert pick is not None
        assert pick.entity_id == "small"

    def test_an_edge_counts_as_a_hit(self, world: EntityManager) -> None:
        """Being a pixel forgiving is a feature in a picker."""
        entity = world.create_entity("block")
        entity.add_component(Transform())
        entity.add_component(_sprite(32, 32))

        assert pick_at(world, Vector2(16, 16)) is not None

    def test_the_pick_carries_bounds_for_drawing(self, scene: EntityManager) -> None:
        """The viewport draws a selection box from them."""
        pick = pick_at(scene, Vector2(500, 500))
        assert pick is not None
        assert pick.bounds.width == 64


class TestPickAtWithPhysics:
    """Physics first, where there is any."""

    class _Engine:
        """Just enough of `IPhysicsEngine` to answer a point query."""

        def __init__(self, hits: list[str]) -> None:
            self.hits = hits
            self.queried: list[Vector2] = []

        def point_query(self, point: Vector2) -> list[str]:
            self.queried.append(point)
            return self.hits

    def test_a_collider_hit_wins_over_sprite_bounds(self, scene: EntityManager) -> None:
        """A collider is a deliberate statement about an entity's extent;
        a sprite box is inferred from its image."""
        engine = self._Engine(["big"])
        pick = pick_at(scene, Vector2(0, 0), physics=engine)
        assert pick is not None
        assert pick.entity_id == "big"

    def test_the_first_physics_hit_is_used(self, scene: EntityManager) -> None:
        """`point_query` orders results most-deeply-enclosing first."""
        engine = self._Engine(["far", "big"])
        pick = pick_at(scene, Vector2(0, 0), physics=engine)
        assert pick is not None
        assert pick.entity_id == "far"

    def test_it_falls_back_to_sprites_when_physics_finds_nothing(
        self, scene: EntityManager
    ) -> None:
        """Most decoration has no collider at all."""
        pick = pick_at(scene, Vector2(500, 500), physics=self._Engine([]))
        assert pick is not None
        assert pick.entity_id == "far"

    def test_a_physics_hit_still_gets_bounds_to_draw(
        self, scene: EntityManager
    ) -> None:
        engine = self._Engine(["far"])
        pick = pick_at(scene, Vector2(500, 500), physics=engine)
        assert pick is not None
        assert pick.bounds.width == 64

    def test_a_hit_with_no_transform_still_returns(self, scene: EntityManager) -> None:
        engine = self._Engine(["ghost_body"])
        pick = pick_at(scene, Vector2(0, 0), physics=engine)
        assert pick is not None
        assert pick.entity_id == "ghost_body"

    def test_a_failing_engine_does_not_break_picking(
        self, scene: EntityManager
    ) -> None:
        """Sprite bounds still work, so the editor stays usable."""

        class _Broken:
            def point_query(self, point: Vector2) -> list[str]:
                raise RuntimeError("space is not stepped")

        pick = pick_at(scene, Vector2(500, 500), physics=_Broken())
        assert pick is not None
        assert pick.entity_id == "far"

    def test_an_engine_without_point_query_is_ignored(
        self, scene: EntityManager
    ) -> None:
        pick = pick_at(scene, Vector2(500, 500), physics=object())
        assert pick is not None


class TestMarquee:
    """A dragged region."""

    def test_normalises_any_drag_direction(self) -> None:
        """Dragging up-and-left is as valid as down-and-right, and a Rect
        with negative width contains nothing."""
        down_right = marquee_rect(Vector2(10, 10), Vector2(50, 40))
        up_left = marquee_rect(Vector2(50, 40), Vector2(10, 10))
        assert down_right == up_left == Rect(10, 10, 40, 30)

    def test_a_zero_drag_still_has_area(self) -> None:
        assert marquee_rect(Vector2(5, 5), Vector2(5, 5)).width >= 1

    def test_touch_select_catches_a_partial_overlap(self, scene: EntityManager) -> None:
        caught = {
            pick.entity_id for pick in pick_in_region(scene, Rect(-200, -200, 210, 210))
        }
        assert "big" in caught

    def test_enclose_select_requires_full_containment(
        self, scene: EntityManager
    ) -> None:
        """Both conventions exist in real editors -- touch is quicker,
        enclose is precise -- so the caller chooses."""
        region = Rect(-200, -200, 210, 210)
        caught = {
            pick.entity_id
            for pick in pick_in_region(scene, region, require_full_containment=True)
        }
        assert "big" not in caught

    def test_enclose_select_catches_what_fits(self, scene: EntityManager) -> None:
        caught = {
            pick.entity_id
            for pick in pick_in_region(
                scene, Rect(400, 400, 200, 200), require_full_containment=True
            )
        }
        assert caught == {"far"}

    def test_an_empty_region_catches_nothing(self, scene: EntityManager) -> None:
        assert pick_in_region(scene, Rect(-9999, -9999, 1, 1)) == []

    def test_results_are_front_most_first(self, scene: EntityManager) -> None:
        caught = [
            pick.entity_id for pick in pick_in_region(scene, Rect(-200, -200, 400, 400))
        ]
        assert caught.index("small") < caught.index("big")

    def test_a_disabled_entity_is_not_caught(self, scene: EntityManager) -> None:
        scene.set_entity_enabled("far", False)
        caught = {
            pick.entity_id for pick in pick_in_region(scene, Rect(400, 400, 200, 200))
        }
        assert caught == set()


class TestCoordinateMapping:
    """The pair that has to agree exactly."""

    def test_round_trips_when_the_panel_matches_the_render_size(self) -> None:
        camera = Camera2D(800, 600)
        panel = target = Rect(0, 0, 800, 600)

        for point in (Vector2(0, 0), Vector2(400, 300), Vector2(799, 599)):
            world = screen_to_world(camera, point, panel, target)
            back = world_to_panel(camera, world, panel, target)
            assert back.x == pytest.approx(point.x)
            assert back.y == pytest.approx(point.y)

    def test_round_trips_when_the_panel_is_a_different_size(self) -> None:
        """The case a naive implementation gets wrong: a docked panel is
        almost never exactly the render resolution."""
        camera = Camera2D(800, 600)
        panel = Rect(0, 0, 400, 300)
        target = Rect(0, 0, 800, 600)

        for point in (Vector2(0, 0), Vector2(200, 150), Vector2(37, 211)):
            world = screen_to_world(camera, point, panel, target)
            back = world_to_panel(camera, world, panel, target)
            assert back.x == pytest.approx(point.x)
            assert back.y == pytest.approx(point.y)

    def test_round_trips_with_a_panned_and_zoomed_camera(self) -> None:
        camera = Camera2D(800, 600)
        camera.position = Vector2(123, -456)
        camera.zoom = 2.5
        panel = Rect(0, 0, 640, 480)
        target = Rect(0, 0, 800, 600)

        for point in (Vector2(0, 0), Vector2(320, 240), Vector2(639, 479)):
            world = screen_to_world(camera, point, panel, target)
            back = world_to_panel(camera, world, panel, target)
            assert back.x == pytest.approx(point.x)
            assert back.y == pytest.approx(point.y)

    def test_the_panel_centre_is_the_camera_position(self) -> None:
        camera = Camera2D(800, 600)
        camera.position = Vector2(100, 200)
        panel = Rect(0, 0, 400, 300)
        target = Rect(0, 0, 800, 600)

        centre = screen_to_world(camera, Vector2(200, 150), panel, target)
        assert centre.x == pytest.approx(100)
        assert centre.y == pytest.approx(200)

    def test_it_agrees_with_the_camera_on_an_unscaled_panel(self) -> None:
        """Which is what makes it agree with what the batcher drew --
        `test_graphics.py` locks `world_to_screen` to the batcher
        transform, and this is layered on top of it."""
        camera = Camera2D(800, 600)
        camera.position = Vector2(50, 50)
        camera.zoom = 1.5
        panel = target = Rect(0, 0, 800, 600)

        world = Vector2(123, 456)
        assert world_to_panel(camera, world, panel, target).x == pytest.approx(
            camera.world_to_screen(world, target).x
        )

    def test_a_collapsed_panel_does_not_divide_by_zero(self) -> None:
        camera = Camera2D(800, 600)
        screen_to_world(camera, Vector2(0, 0), Rect(0, 0, 0, 0), Rect(0, 0, 800, 600))
        world_to_panel(camera, Vector2(0, 0), Rect(0, 0, 400, 300), Rect(0, 0, 0, 0))
