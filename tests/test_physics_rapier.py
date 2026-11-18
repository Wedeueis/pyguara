"""The Rapier backend keeps the contract the pymunk one does.

Every behaviour here runs against both engines, so where pymunk's answer is
the contract the Rapier one is held to it. Numbers differ between the two
solvers, so positions are compared to a pixel or two and the assertions are
about behaviour: what rests where, what is hit, what is reported.
"""

from __future__ import annotations

from typing import Any

import pytest

from pyguara.common.types import Rect, Vector2
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.backends.rapier_impl import RapierEngine
from pyguara.physics.types import (
    BodyType,
    CollisionLayer,
    PhysicsMaterial,
    ShapeType,
)

DT = 1.0 / 60.0
SOLID = PhysicsMaterial(friction=0.5, restitution=0.0, density=1.0)
EVERYTHING = CollisionLayer()


class _Recorder:
    """A collision system that records what it is told."""

    def __init__(self, process: bool = True) -> None:
        self.process = process
        self.events: list[tuple[str, str, str, str | None]] = []

    def on_collision_begin(
        self,
        a: str,
        b: str,
        point: Any,
        normal: Any,
        impulse: float,
        sensor: str | None,
    ) -> bool:
        self.events.append(("begin", *sorted((a, b)), sensor))
        return self.process

    def on_collision_persist(
        self,
        a: str,
        b: str,
        point: Any,
        normal: Any,
        impulse: float,
        sensor: str | None,
    ) -> bool:
        self.events.append(("persist", *sorted((a, b)), sensor))
        return self.process

    def on_collision_end(self, a: str, b: str, sensor: str | None) -> None:
        self.events.append(("end", *sorted((a, b)), sensor))

    def kinds(self, pair: tuple[str, str]) -> list[str]:
        return [kind for kind, a, b, _ in self.events if (a, b) == tuple(sorted(pair))]


@pytest.fixture(params=["pymunk", "rapier"])
def engine(request: pytest.FixtureRequest) -> Any:
    built: Any = PymunkEngine() if request.param == "pymunk" else RapierEngine()
    built.initialize(Vector2(0, 980))
    yield built
    built.cleanup()


def _box(
    engine: Any,
    entity: str,
    at: Vector2,
    size: tuple[float, float] = (20, 20),
    kind: BodyType = BodyType.DYNAMIC,
    layer: CollisionLayer = EVERYTHING,
    sensor: bool = False,
    **body: Any,
) -> Any:
    handle = engine.create_body(entity, kind, at, **body)
    engine.add_shape(
        handle, ShapeType.BOX, list(size), Vector2(0, 0), SOLID, layer, sensor
    )
    return handle


def _circle(
    engine: Any,
    entity: str,
    at: Vector2,
    radius: float,
    kind: BodyType = BodyType.DYNAMIC,
) -> Any:
    handle = engine.create_body(entity, kind, at)
    engine.add_shape(
        handle, ShapeType.CIRCLE, [radius], Vector2(0, 0), SOLID, EVERYTHING, False
    )
    return handle


def _ground(engine: Any, y: float = 200.0) -> Any:
    return _box(engine, "ground", Vector2(100, y), (600, 20), BodyType.STATIC)


def _run(engine: Any, seconds: float) -> None:
    for _ in range(round(seconds / DT)):
        engine.update(DT)


class TestBodies:
    def test_a_box_comes_to_rest_on_the_ground(self, engine: Any) -> None:
        _ground(engine)
        box = _box(engine, "box", Vector2(100, 0))
        _run(engine, 2.0)
        assert box.position.y == pytest.approx(180.0, abs=1.5)
        assert abs(box.velocity.y) < 5.0

    def test_a_gravity_scale_of_zero_floats(self, engine: Any) -> None:
        box = _box(engine, "box", Vector2(0, 0), gravity_scale=0.0)
        _run(engine, 1.0)
        assert box.position == Vector2(0, 0)

    def test_a_static_body_never_moves(self, engine: Any) -> None:
        ground = _ground(engine)
        _box(engine, "box", Vector2(100, 150))
        _run(engine, 1.0)
        assert ground.position == Vector2(100, 200)

    def test_a_kinematic_body_moves_by_its_velocity_alone(self, engine: Any) -> None:
        mover = _box(engine, "mover", Vector2(0, 0), kind=BodyType.KINEMATIC)
        mover.velocity = Vector2(60, 0)
        _run(engine, 1.0)
        assert mover.position.x == pytest.approx(60.0, abs=0.01)
        assert mover.position.y == pytest.approx(0.0, abs=0.01)

    def test_fixed_rotation_keeps_a_box_upright(self, engine: Any) -> None:
        _ground(engine)
        box = _box(engine, "box", Vector2(100, 100), fixed_rotation=True)
        box.apply_impulse(Vector2(0, 400), Vector2(9, -9))
        _run(engine, 1.0)
        assert box.rotation == pytest.approx(0.0, abs=1e-6)

    def test_an_off_centre_impulse_turns_a_free_box(self, engine: Any) -> None:
        box = _box(engine, "box", Vector2(0, 0), gravity_scale=0.0)
        box.apply_impulse(Vector2(0, 400), Vector2(9, -9))
        _run(engine, 0.5)
        assert abs(box.rotation) > 1.0

    def test_mass_comes_from_density_as_in_chipmunk(self, engine: Any) -> None:
        """A 20x20 box of density 1 weighs 400, whatever `mass` said."""
        box = _box(engine, "box", Vector2(0, 0), mass=7.0, gravity_scale=0.0)
        box.apply_impulse(Vector2(400, 0))
        assert box.velocity.x == pytest.approx(1.0, rel=1e-6)

    def test_a_force_lasts_one_solver_step(self, engine: Any) -> None:
        """Chipmunk clears forces after each step; with four substeps the
        force acts for a quarter of the tick."""
        box = _box(engine, "box", Vector2(0, 0), gravity_scale=0.0)
        box.apply_force(Vector2(4000, 0))
        engine.update(DT)
        engine.update(DT)
        assert box.velocity.x == pytest.approx(4000 / 400 * DT / 4, rel=1e-6)

    def test_setting_position_and_rotation_reads_back(self, engine: Any) -> None:
        box = _box(engine, "box", Vector2(0, 0), gravity_scale=0.0)
        box.position = Vector2(12.5, -3.25)
        box.rotation = 30.0
        assert box.position == Vector2(12.5, -3.25)
        assert box.rotation == pytest.approx(30.0)


class TestQueries:
    def test_a_ray_reports_the_nearest_solid(self, engine: Any) -> None:
        _box(engine, "near", Vector2(100, 100), kind=BodyType.STATIC)
        _box(engine, "far", Vector2(200, 100), kind=BodyType.STATIC)
        hit = engine.raycast(Vector2(0, 100), Vector2(300, 100))
        assert hit is not None and hit.entity_id == "near"
        assert hit.position.x == pytest.approx(90.0, abs=1.5)
        assert hit.normal.x == pytest.approx(-1.0, abs=1e-6)
        assert hit.distance == pytest.approx(hit.position.x, abs=1e-6)

    def test_every_hit_comes_back_nearest_first(self, engine: Any) -> None:
        for index, x in enumerate((250, 100, 175)):
            _box(engine, f"b{index}", Vector2(x, 100), kind=BodyType.STATIC)
        hits = engine.raycast_all(Vector2(0, 100), Vector2(400, 100))
        assert [hit.entity_id for hit in hits] == ["b1", "b2", "b0"]

    def test_a_ray_can_ignore_its_caster(self, engine: Any) -> None:
        _box(engine, "me", Vector2(100, 100), kind=BodyType.STATIC)
        _box(engine, "wall", Vector2(200, 100), kind=BodyType.STATIC)
        hit = engine.raycast(
            Vector2(100, 100), Vector2(300, 100), ignore_entity_id="me"
        )
        assert hit is not None and hit.entity_id == "wall"

    def test_a_mask_hides_a_category(self, engine: Any) -> None:
        _box(
            engine,
            "ghost",
            Vector2(100, 100),
            kind=BodyType.STATIC,
            layer=CollisionLayer(category=2),
        )
        assert engine.raycast(Vector2(0, 100), Vector2(300, 100), mask=1) is None
        assert engine.raycast(Vector2(0, 100), Vector2(300, 100), mask=2) is not None

    def test_a_ray_passes_through_a_sensor(self, engine: Any) -> None:
        _box(engine, "trigger", Vector2(100, 100), kind=BodyType.STATIC, sensor=True)
        assert engine.raycast(Vector2(0, 100), Vector2(300, 100)) is None

    def test_box_and_circle_overlaps(self, engine: Any) -> None:
        _box(engine, "a", Vector2(0, 0), kind=BodyType.STATIC)
        _box(engine, "b", Vector2(40, 0), kind=BodyType.STATIC)
        assert engine.overlap_box(Vector2(5, 0), Vector2(2, 2)) == "a"
        assert engine.overlap_box(Vector2(100, 100), Vector2(2, 2)) is None
        assert sorted(engine.overlap_box_all(Vector2(20, 0), Vector2(15, 2))) == [
            "a",
            "b",
        ]
        assert sorted(engine.overlap_circle(Vector2(20, 0), 12.0)) == ["a", "b"]
        assert engine.overlap_circle(Vector2(20, 0), 12.0, ignore_entity_id="a") == [
            "b"
        ]

    def test_a_body_with_two_shapes_is_reported_once(self, engine: Any) -> None:
        body = _box(engine, "twin", Vector2(0, 0), kind=BodyType.STATIC)
        engine.add_shape(
            body, ShapeType.BOX, [20, 20], Vector2(5, 0), SOLID, EVERYTHING, False
        )
        assert engine.overlap_box_all(Vector2(0, 0), Vector2(30, 30)) == ["twin"]

    def test_a_point_query_puts_the_deepest_shape_first(self, engine: Any) -> None:
        _box(engine, "big", Vector2(0, 0), (100, 100), BodyType.STATIC)
        _box(engine, "small", Vector2(40, 0), (10, 10), BodyType.STATIC)
        assert engine.point_query(Vector2(40, 0)) == ["big", "small"]
        assert engine.point_query(Vector2(500, 0)) == []

    def test_a_region_query_compares_bounding_boxes(self, engine: Any) -> None:
        """A circle's bounding-box corner counts though the circle does not."""
        _circle(engine, "round", Vector2(0, 0), 10.0, BodyType.STATIC)
        corner = Rect(8, 8, 4, 4)
        assert engine.region_query(corner) == ["round"]
        assert engine.overlap_box(Vector2(10, 10), Vector2(2, 2)) is None

    def test_a_query_sees_a_body_made_this_tick(self, engine: Any) -> None:
        box = _box(engine, "new", Vector2(50, 50), kind=BodyType.STATIC)
        assert engine.overlap_box(Vector2(50, 50), Vector2(1, 1)) == "new"
        box.position = Vector2(500, 500)
        assert engine.overlap_box(Vector2(50, 50), Vector2(1, 1)) is None
        assert engine.overlap_box(Vector2(500, 500), Vector2(1, 1)) == "new"


class TestFiltering:
    def test_a_mask_lets_a_category_pass_through(self, engine: Any) -> None:
        _box(
            engine,
            "floor",
            Vector2(100, 200),
            (600, 20),
            BodyType.STATIC,
            layer=CollisionLayer(category=2),
        )
        box = _box(
            engine, "box", Vector2(100, 0), layer=CollisionLayer(category=1, mask=1)
        )
        _run(engine, 1.0)
        assert box.position.y > 250

    def test_the_same_group_never_collides(self, engine: Any) -> None:
        _box(
            engine,
            "floor",
            Vector2(100, 200),
            (600, 20),
            BodyType.STATIC,
            layer=CollisionLayer(group=3),
        )
        box = _box(engine, "box", Vector2(100, 0), layer=CollisionLayer(group=3))
        _run(engine, 1.0)
        assert box.position.y > 250

    def test_a_different_group_does(self, engine: Any) -> None:
        _box(
            engine,
            "floor",
            Vector2(100, 200),
            (600, 20),
            BodyType.STATIC,
            layer=CollisionLayer(group=3),
        )
        box = _box(engine, "box", Vector2(100, 0), layer=CollisionLayer(group=4))
        _run(engine, 1.0)
        assert box.position.y == pytest.approx(180.0, abs=1.5)


class TestCollisionEvents:
    def test_a_landing_begins_persists_and_ends(self, engine: Any) -> None:
        recorder = _Recorder()
        engine.set_collision_system(recorder)
        _ground(engine)
        box = _box(engine, "box", Vector2(100, 150))
        _run(engine, 0.5)
        kinds = recorder.kinds(("box", "ground"))
        assert kinds[0] == "begin" and "persist" in kinds and "end" not in kinds
        box.position = Vector2(100, -500)
        box.velocity = Vector2(0, 0)
        _run(engine, 0.1)
        assert recorder.kinds(("box", "ground"))[-1] == "end"

    def test_a_sensor_reports_itself_and_does_not_block(self, engine: Any) -> None:
        recorder = _Recorder()
        engine.set_collision_system(recorder)
        _box(engine, "zone", Vector2(100, 100), (200, 40), BodyType.STATIC, sensor=True)
        box = _box(engine, "box", Vector2(100, 0))
        _run(engine, 1.0)
        assert box.position.y > 200
        begins = [event for event in recorder.events if event[0] == "begin"]
        assert begins == [("begin", "box", "zone", "zone")]
        assert recorder.kinds(("box", "zone"))[-1] == "end"

    def test_declining_a_pair_lets_it_pass_through(self, engine: Any) -> None:
        recorder = _Recorder(process=False)
        engine.set_collision_system(recorder)
        _ground(engine)
        box = _box(engine, "box", Vector2(100, 150))
        _run(engine, 1.0)
        assert box.position.y > 250
        assert recorder.kinds(("box", "ground"))[0] == "begin"

    def test_destroying_a_body_ends_its_contacts(self, engine: Any) -> None:
        recorder = _Recorder()
        engine.set_collision_system(recorder)
        _ground(engine)
        box = _box(engine, "box", Vector2(100, 175))
        _run(engine, 0.2)
        engine.destroy_body(box)
        engine.update(DT)
        assert recorder.kinds(("box", "ground"))[-1] == "end"


class TestOneWayPlatforms:
    """Solid from above, passable from below, decided every step."""

    @staticmethod
    def _platform(engine: Any) -> None:
        engine.set_collision_system(_Recorder())
        body = engine.create_body("platform", BodyType.STATIC, Vector2(100, 200))
        engine.add_shape(
            body,
            ShapeType.BOX,
            [200, 10],
            Vector2(0, 0),
            SOLID,
            EVERYTHING,
            False,
            one_way=True,
        )

    def test_a_box_dropped_from_above_lands_on_it(self, engine: Any) -> None:
        self._platform(engine)
        box = _box(engine, "box", Vector2(100, 100))
        _run(engine, 1.5)
        assert box.position.y == pytest.approx(185.0, abs=1.5)

    def test_a_box_thrown_up_from_below_passes_and_lands_on_top(
        self, engine: Any
    ) -> None:
        self._platform(engine)
        box = _box(engine, "box", Vector2(100, 260))
        box.velocity = Vector2(0, -700)
        _run(engine, 2.0)
        assert box.position.y == pytest.approx(185.0, abs=1.5)

    def test_a_box_below_it_falls_away(self, engine: Any) -> None:
        self._platform(engine)
        box = _box(engine, "box", Vector2(100, 215))
        _run(engine, 0.5)
        assert box.position.y > 240

    def test_the_solid_face_can_point_another_way(self, engine: Any) -> None:
        """A ceiling solid from below: a box thrown up stops under it."""
        engine.set_collision_system(_Recorder())
        engine.initialize(Vector2(0, 0))
        ceiling = engine.create_body("ceiling", BodyType.STATIC, Vector2(100, 100))
        engine.add_shape(
            ceiling,
            ShapeType.BOX,
            [200, 10],
            Vector2(0, 0),
            SOLID,
            EVERYTHING,
            False,
            one_way=True,
            one_way_normal=Vector2(0, 1),
        )
        box = _box(engine, "box", Vector2(100, 200))
        box.velocity = Vector2(0, -300)
        _run(engine, 1.0)
        assert box.position.y == pytest.approx(115.0, abs=1.5)


class TestWhatRapierDoesNotDoYet:
    @pytest.fixture
    def rapier(self) -> Any:
        engine = RapierEngine()
        engine.initialize(Vector2(0, 0))
        return engine

    def test_polygons_are_refused(self, rapier: Any) -> None:
        body = rapier.create_body("p", BodyType.STATIC, Vector2(0, 0))
        with pytest.raises(NotImplementedError, match="POLYGON"):
            rapier.add_shape(
                body,
                ShapeType.POLYGON,
                [1, 2, 3],
                Vector2(0, 0),
                SOLID,
                EVERYTHING,
                False,
            )

    def test_a_body_before_initialize_is_refused(self) -> None:
        with pytest.raises(RuntimeError, match="initialize"):
            RapierEngine().create_body("x", BodyType.DYNAMIC, Vector2(0, 0))


def test_rapier_is_the_default(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from pyguara.application.bootstrap import create_headless_application
    from pyguara.config.types import PhysicsBackend, PhysicsConfig
    from pyguara.physics.protocols import IPhysicsEngine

    assert PhysicsConfig().backend is PhysicsBackend.RAPIER
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYGUARA_PHYSICS_BACKEND", raising=False)
    app = create_headless_application()
    try:
        assert isinstance(app.container.get(IPhysicsEngine), RapierEngine)
    finally:
        app.shutdown()


def test_pymunk_can_still_be_chosen(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pyguara.application.bootstrap import create_headless_application
    from pyguara.physics.protocols import IPhysicsEngine

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYGUARA_PHYSICS_BACKEND", "pymunk")
    app = create_headless_application()
    try:
        assert isinstance(app.container.get(IPhysicsEngine), PymunkEngine)
    finally:
        app.shutdown()


def test_the_config_chooses_rapier(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pyguara.application.bootstrap import create_headless_application
    from pyguara.config.manager import ConfigManager
    from pyguara.config.types import PhysicsBackend
    from pyguara.physics.protocols import IPhysicsEngine

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYGUARA_PHYSICS_BACKEND", "rapier")
    app = create_headless_application()
    try:
        assert (
            app.container.get(ConfigManager).config.physics.backend
            is PhysicsBackend.RAPIER
        )
        assert isinstance(app.container.get(IPhysicsEngine), RapierEngine)
    finally:
        app.shutdown()
