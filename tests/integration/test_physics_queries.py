"""Spatial queries against a real pymunk space.

`raycast` and `overlap_box` were the only queries the engine exposed, which
ruled out click-picking, explosion radii, melee arcs, piercing shots and
"roughly what is in this rectangle". These drive the five that fill the gap
(`point_query`, `overlap_circle`, `overlap_box_all`, `region_query`,
`raycast_all`) plus the `mask` parameter added to `overlap_box`.

Every query here is exercised against bodies built directly in a
`PymunkEngine`, in a mix of positions, layers and shape counts -- not the
single slow-body-at-rest that the rest of the physics suite reuses.
"""

from __future__ import annotations

import pytest

from pyguara.common.types import Rect, Vector2
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.types import (
    BodyType,
    CollisionLayer,
    PhysicsMaterial,
    ShapeType,
)

pytestmark = pytest.mark.integration

MAT = PhysicsMaterial()


@pytest.fixture
def engine() -> PymunkEngine:
    """An initialised, gravity-free space."""
    eng = PymunkEngine(substeps=1)
    eng.initialize(Vector2(0, 0))
    return eng


def box(
    eng: PymunkEngine,
    entity_id: str,
    centre: tuple[float, float],
    size: tuple[float, float] = (40.0, 40.0),
    *,
    body_type: BodyType = BodyType.STATIC,
    sensor: bool = False,
    category: int = 0xFFFFFFFF,
) -> None:
    """Attach one axis-aligned box, owned by `entity_id`."""
    body = eng.create_body(entity_id, body_type, Vector2(*centre), mass=1.0)
    eng.add_shape(
        body,
        ShapeType.BOX,
        list(size),
        Vector2(0, 0),
        MAT,
        CollisionLayer(category=category),
        sensor,
    )


class TestPointQuery:
    def test_a_point_inside_a_shape_returns_its_entity(self, engine):
        box(engine, "A", (100, 100))
        assert engine.point_query(Vector2(100, 100)) == ["A"]

    def test_a_point_in_open_space_returns_nothing(self, engine):
        box(engine, "A", (100, 100))
        assert engine.point_query(Vector2(400, 400)) == []

    def test_sensors_are_skipped(self, engine):
        box(engine, "SENSOR", (100, 100), sensor=True)
        assert engine.point_query(Vector2(100, 100)) == []

    def test_ignore_entity_id_excludes_that_body(self, engine):
        box(engine, "A", (100, 100))
        assert engine.point_query(Vector2(100, 100), ignore_entity_id="A") == []

    def test_stacked_shapes_come_back_most_enclosed_first(self, engine):
        # BIG spans x 60..160; SMALL spans 90..110. The point at x=100 is
        # 40px inside BIG and only 10px inside SMALL, so BIG is the better
        # pick and must lead.
        box(engine, "BIG", (110, 100), size=(100, 100))
        box(engine, "SMALL", (100, 100), size=(20, 40))
        assert engine.point_query(Vector2(100, 100)) == ["BIG", "SMALL"]

    def test_mask_selects_which_categories_are_hit(self, engine):
        box(engine, "LAYER1", (100, 100), category=0b01)
        box(engine, "LAYER2", (100, 100), category=0b10)
        assert engine.point_query(Vector2(100, 100), mask=0b10) == ["LAYER2"]

    def test_empty_space_is_tolerated(self):
        assert PymunkEngine().point_query(Vector2(0, 0)) == []


class TestOverlapCircle:
    def test_it_returns_every_shape_the_circle_touches(self, engine):
        box(engine, "A", (100, 100))
        box(engine, "B", (160, 100))
        found = engine.overlap_circle(Vector2(130, 100), 40)
        assert set(found) == {"A", "B"}

    def test_a_shape_outside_the_radius_is_not_returned(self, engine):
        box(engine, "A", (100, 100))
        box(engine, "FAR", (400, 100))
        assert engine.overlap_circle(Vector2(100, 100), 50) == ["A"]

    def test_sensors_are_skipped(self, engine):
        box(engine, "A", (100, 100))
        box(engine, "SENSOR", (130, 100), sensor=True)
        assert engine.overlap_circle(Vector2(115, 100), 60) == ["A"]

    def test_a_two_shape_body_is_reported_once(self, engine):
        body = engine.create_body("TWO", BodyType.STATIC, Vector2(200, 100))
        for dx in (-15, 15):
            engine.add_shape(
                body,
                ShapeType.BOX,
                [20, 20],
                Vector2(dx, 0),
                MAT,
                CollisionLayer(),
                False,
            )
        assert engine.overlap_circle(Vector2(200, 100), 40) == ["TWO"]

    def test_ignore_entity_id_and_mask(self, engine):
        box(engine, "SELF", (100, 100), category=0b01)
        box(engine, "OTHER", (110, 100), category=0b10)
        assert engine.overlap_circle(
            Vector2(105, 100), 30, mask=0b10, ignore_entity_id="SELF"
        ) == ["OTHER"]


class TestOverlapBoxAll:
    def test_it_returns_every_overlapping_shape(self, engine):
        box(engine, "A", (100, 100))
        box(engine, "B", (150, 100))
        box(engine, "C", (400, 400))
        assert set(engine.overlap_box_all(Vector2(125, 100), Vector2(40, 40))) == {
            "A",
            "B",
        }

    def test_single_hit_overlap_box_still_stops_at_the_first(self, engine):
        box(engine, "A", (100, 100))
        box(engine, "B", (150, 100))
        one = engine.overlap_box(Vector2(125, 100), Vector2(40, 40))
        assert one in {"A", "B"}

    def test_overlap_box_mask_is_honoured(self, engine):
        box(engine, "L1", (100, 100), category=0b01)
        box(engine, "L2", (100, 100), category=0b10)
        assert engine.overlap_box(Vector2(100, 100), Vector2(5, 5), mask=0b10) == "L2"

    def test_sensors_are_skipped(self, engine):
        box(engine, "SENSOR", (100, 100), sensor=True)
        assert engine.overlap_box_all(Vector2(100, 100), Vector2(30, 30)) == []


class TestRegionQuery:
    def test_it_reports_bodies_whose_bounding_box_overlaps(self, engine):
        box(engine, "A", (100, 100))
        box(engine, "B", (150, 120))
        box(engine, "OUT", (400, 400))
        assert set(engine.region_query(Rect(60, 60, 130, 100))) == {"A", "B"}

    def test_it_is_broad_phase_a_circle_out_of_shape_still_counts(self, engine):
        # A circle centred at (100,100) r40: its bounding box is x,y 60..140.
        # A rect touching only that box's corner overlaps the box but not the
        # disc -- region_query still reports it.
        body = engine.create_body("DISC", BodyType.STATIC, Vector2(100, 100))
        engine.add_shape(
            body, ShapeType.CIRCLE, [40], Vector2(0, 0), MAT, CollisionLayer(), False
        )
        assert engine.region_query(Rect(130, 130, 20, 20)) == ["DISC"]

    def test_sensors_are_skipped(self, engine):
        box(engine, "SENSOR", (100, 100), sensor=True)
        assert engine.region_query(Rect(50, 50, 100, 100)) == []

    def test_a_far_rectangle_is_clear(self, engine):
        box(engine, "A", (100, 100))
        assert engine.region_query(Rect(400, 400, 10, 10)) == []


class TestRaycastAll:
    def test_hits_come_back_ordered_by_distance(self, engine):
        box(engine, "NEAR", (100, 100))
        box(engine, "MID", (200, 100))
        box(engine, "FAR", (300, 100))
        hits = engine.raycast_all(Vector2(0, 100), Vector2(500, 100))
        assert [h.entity_id for h in hits] == ["NEAR", "MID", "FAR"]
        assert hits[0].distance < hits[1].distance < hits[2].distance

    def test_it_pierces_where_raycast_stops_at_the_first(self, engine):
        box(engine, "NEAR", (100, 100))
        box(engine, "FAR", (300, 100))
        assert engine.raycast(Vector2(0, 100), Vector2(500, 100)).entity_id == "NEAR"
        assert [
            h.entity_id for h in engine.raycast_all(Vector2(0, 100), Vector2(500, 100))
        ] == ["NEAR", "FAR"]

    def test_a_two_shape_body_yields_one_hit(self, engine):
        body = engine.create_body("TWO", BodyType.STATIC, Vector2(200, 100))
        for dx in (-30, 30):
            engine.add_shape(
                body,
                ShapeType.BOX,
                [20, 40],
                Vector2(dx, 0),
                MAT,
                CollisionLayer(),
                False,
            )
        hits = engine.raycast_all(Vector2(0, 100), Vector2(500, 100))
        assert [h.entity_id for h in hits] == ["TWO"]

    def test_sensors_and_ignored_bodies_are_skipped(self, engine):
        box(engine, "SELF", (50, 100))
        box(engine, "SENSOR", (150, 100), sensor=True)
        box(engine, "TARGET", (250, 100))
        hits = engine.raycast_all(
            Vector2(0, 100), Vector2(500, 100), ignore_entity_id="SELF"
        )
        assert [h.entity_id for h in hits] == ["TARGET"]

    def test_mask_filters_the_ray(self, engine):
        box(engine, "L1", (100, 100), category=0b01)
        box(engine, "L2", (200, 100), category=0b10)
        hits = engine.raycast_all(Vector2(0, 100), Vector2(400, 100), mask=0b10)
        assert [h.entity_id for h in hits] == ["L2"]

    def test_a_ray_through_nothing_is_empty(self, engine):
        assert engine.raycast_all(Vector2(0, 0), Vector2(10, 10)) == []
