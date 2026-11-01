"""A map's objects become entities, through prefabs (#345)."""

from __future__ import annotations

import math
import subprocess
import sys
from dataclasses import dataclass

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.ecs.manager import EntityManager
from pyguara.physics.components import Collider
from pyguara.physics.trigger_volume import TriggerVolume
from pyguara.physics.types import ShapeType
from pyguara.prefabs.factory import PrefabFactory
from pyguara.prefabs.registry import ComponentRegistry
from pyguara.prefabs.types import PrefabData
from pyguara.tilemap import (
    MapObject,
    ObjectLayer,
    ObjectShape,
    Tilemap,
    load_tmx,
)
from pyguara.tilemap.spawning import MapSpawnError, spawn_objects


@dataclass
class Health(BaseComponent):
    max: int = 10


@pytest.fixture
def factory() -> PrefabFactory:
    registry = ComponentRegistry()
    for component in (Transform, Collider, TriggerVolume, Health):
        registry.register(component)
    return PrefabFactory(EntityManager(), registry)


BAT = PrefabData("bat", components={"Transform": {}, "Health": {"max": 5}})
DOOR = PrefabData("door", components={"Transform": {}, "TriggerVolume": {}})
WALL = PrefabData("wall", components={"Transform": {}, "Collider": {}})


def _map(*objects: MapObject, name: str = "things", visible: bool = True) -> Tilemap:
    tilemap = Tilemap(16)
    tilemap.add_object_layer(ObjectLayer(name, list(objects), visible=visible))
    return tilemap


def _rect(id_: int = 1, type_: str = "Bat", **fields: object) -> MapObject:
    values: dict[str, object] = {"x": 10.0, "y": 20.0, "width": 30.0, "height": 40.0}
    return MapObject(id_, type=type_, **{**values, **fields})  # type: ignore[arg-type]


class TestPlacement:
    def test_a_rectangle_is_placed_at_its_centre_not_its_corner(
        self, factory: PrefabFactory
    ) -> None:
        """Using `(x, y)` offsets every trigger by half its size."""
        [spawned] = spawn_objects(_map(_rect()), factory, {"Bat": BAT})

        assert spawned.entity.get_component(Transform).position == Vector2(25, 40)

    def test_a_tile_objects_corner_is_its_bottom_left(
        self, factory: PrefabFactory
    ) -> None:
        obj = _rect(shape=ObjectShape.TILE)

        [spawned] = spawn_objects(_map(obj), factory, {"Bat": BAT})

        assert spawned.entity.get_component(Transform).position == Vector2(25, 0)

    def test_a_point_is_placed_at_its_position(self, factory: PrefabFactory) -> None:
        obj = MapObject(1, type="Bat", x=7.0, y=9.0, shape=ObjectShape.POINT)

        [spawned] = spawn_objects(_map(obj), factory, {"Bat": BAT})

        assert spawned.entity.get_component(Transform).position == Vector2(7, 9)

    def test_rotation_turns_about_tileds_corner_and_arrives_in_radians(
        self, factory: PrefabFactory
    ) -> None:
        obj = _rect(x=0.0, y=0.0, width=20.0, height=0.0, rotation=90.0)

        [spawned] = spawn_objects(_map(obj), factory, {"Bat": BAT})

        transform = spawned.entity.get_component(Transform)
        assert transform.rotation == pytest.approx(math.pi / 2)
        assert transform.position.x == pytest.approx(0.0)
        assert transform.position.y == pytest.approx(10.0)

    def test_an_offset_moves_a_whole_room(self, factory: PrefabFactory) -> None:
        [spawned] = spawn_objects(
            _map(_rect()), factory, {"Bat": BAT}, offset=Vector2(100, 200)
        )

        assert spawned.entity.get_component(Transform).position == Vector2(125, 240)


class TestShapes:
    def test_a_rectangle_sizes_a_trigger(self, factory: PrefabFactory) -> None:
        [spawned] = spawn_objects(_map(_rect(type_="Door")), factory, {"Door": DOOR})

        volume = spawned.entity.get_component(TriggerVolume)
        assert volume.shape_type is ShapeType.BOX
        assert volume.dimensions == [30.0, 40.0]

    def test_a_circle_sizes_a_collider_by_radius(self, factory: PrefabFactory) -> None:
        obj = _rect(type_="Wall", shape=ObjectShape.ELLIPSE, width=30.0, height=30.0)

        [spawned] = spawn_objects(_map(obj), factory, {"Wall": WALL})

        collider = spawned.entity.get_component(Collider)
        assert collider.shape_type is ShapeType.CIRCLE
        assert collider.dimensions == [15.0]

    def test_a_point_keeps_the_prefabs_own_collider(
        self, factory: PrefabFactory
    ) -> None:
        wall = PrefabData(
            "w", components={"Transform": {}, "Collider": {"dimensions": [8.0, 9.0]}}
        )
        obj = MapObject(1, type="Wall", x=1.0, y=1.0, shape=ObjectShape.POINT)

        [spawned] = spawn_objects(_map(obj), factory, {"Wall": wall})

        assert spawned.entity.get_component(Collider).dimensions == [8.0, 9.0]

    def test_a_prefab_with_no_collider_does_not_gain_one(
        self, factory: PrefabFactory
    ) -> None:
        [spawned] = spawn_objects(_map(_rect()), factory, {"Bat": BAT})

        assert not spawned.entity.has_component(Collider)

    def test_a_shape_reaches_a_collider_the_prefab_inherits(self) -> None:
        registry = ComponentRegistry()
        for component in (Transform, Collider):
            registry.register(component)
        factory = PrefabFactory(EntityManager(), registry)
        factory.set_prefab_resolver(lambda path: WALL if path == "wall" else None)
        child = PrefabData("child", extends="wall")

        [spawned] = spawn_objects(_map(_rect()), factory, {"Bat": child})

        assert spawned.entity.get_component(Collider).dimensions == [30.0, 40.0]

    @pytest.mark.parametrize("shape", [ObjectShape.POLYGON, ObjectShape.POLYLINE])
    def test_vertices_on_a_collider_are_refused(
        self, factory: PrefabFactory, shape: ObjectShape
    ) -> None:
        obj = _rect(type_="Wall", shape=shape, points=((0.0, 0.0), (5.0, 5.0)))

        with pytest.raises(MapSpawnError, match="cannot carry vertices"):
            spawn_objects(_map(obj), factory, {"Wall": WALL})

    def test_a_polygon_without_a_collider_is_fine(self, factory: PrefabFactory) -> None:
        obj = _rect(shape=ObjectShape.POLYGON, points=((0.0, 0.0), (5.0, 5.0)))

        assert spawn_objects(_map(obj), factory, {"Bat": BAT})

    def test_a_squashed_ellipse_on_a_collider_is_refused(
        self, factory: PrefabFactory
    ) -> None:
        obj = _rect(type_="Wall", shape=ObjectShape.ELLIPSE)

        with pytest.raises(MapSpawnError, match="only a circle"):
            spawn_objects(_map(obj), factory, {"Wall": WALL})


class TestProperties:
    def test_a_dotted_property_overrides_a_field(self, factory: PrefabFactory) -> None:
        obj = _rect(properties={"Health.max": 30})

        [spawned] = spawn_objects(_map(obj), factory, {"Bat": BAT})

        assert spawned.entity.get_component(Health).max == 30

    def test_a_property_can_reach_a_nested_field(self, factory: PrefabFactory) -> None:
        obj = _rect(properties={"Transform.scale.x": 2.0, "Transform.scale.y": 3.0})

        [spawned] = spawn_objects(_map(obj), factory, {"Bat": BAT})

        assert spawned.entity.get_component(Transform).scale == Vector2(2, 3)

    def test_a_stated_shape_beats_the_objects_own(self, factory: PrefabFactory) -> None:
        obj = _rect(type_="Door", properties={"TriggerVolume.dimensions": [1.0, 2.0]})

        [spawned] = spawn_objects(_map(obj), factory, {"Door": DOOR})

        assert spawned.entity.get_component(TriggerVolume).dimensions == [1.0, 2.0]

    def test_an_undotted_property_stays_the_games(self, factory: PrefabFactory) -> None:
        obj = _rect(properties={"loot_table": "cave"})

        [spawned] = spawn_objects(_map(obj), factory, {"Bat": BAT})

        assert spawned.source.properties["loot_table"] == "cave"

    def test_an_unknown_component_is_refused(self, factory: PrefabFactory) -> None:
        obj = _rect(properties={"Healht.max": 30})

        with pytest.raises(MapSpawnError, match="Healht"):
            spawn_objects(_map(obj), factory, {"Bat": BAT})

    def test_an_unknown_field_is_refused(self, factory: PrefabFactory) -> None:
        obj = _rect(properties={"Health.maximum": 30})

        with pytest.raises(ValueError, match="maximum"):
            spawn_objects(_map(obj), factory, {"Bat": BAT})


class TestTheLoudFailures:
    def test_an_unmatched_type_is_refused_by_name(self, factory: PrefabFactory) -> None:
        with pytest.raises(MapSpawnError, match="'Goblin'"):
            spawn_objects(_map(_rect(type_="Goblin")), factory, {"Bat": BAT})

    def test_every_problem_is_listed_and_nothing_is_spawned(
        self, factory: PrefabFactory
    ) -> None:
        tilemap = _map(
            _rect(1), _rect(2, type_="Goblin"), _rect(3, type_="Ogre", name="boss")
        )

        with pytest.raises(MapSpawnError) as raised:
            spawn_objects(tilemap, factory, {"Bat": BAT})

        assert "Goblin" in str(raised.value)
        assert "Object 3 'boss'" in str(raised.value)
        assert not list(factory._entity_manager.get_entities_with(Transform))

    def test_a_layer_the_map_does_not_have_is_refused(
        self, factory: PrefabFactory
    ) -> None:
        with pytest.raises(MapSpawnError, match="enemies"):
            spawn_objects(_map(_rect()), factory, {"Bat": BAT}, layers=["enemies"])


class TestWhatIsSkipped:
    def test_an_object_with_no_type_names_nothing(self, factory: PrefabFactory) -> None:
        assert spawn_objects(_map(_rect(type_="")), factory, {}) == []

    def test_an_ignored_type_is_left_for_the_game(self, factory: PrefabFactory) -> None:
        tilemap = _map(_rect(type_="CameraBounds"))

        assert spawn_objects(tilemap, factory, {}, ignore_types={"CameraBounds"}) == []

    def test_a_hidden_object_is_skipped_unless_asked_for(
        self, factory: PrefabFactory
    ) -> None:
        tilemap = _map(_rect(visible=False))

        assert spawn_objects(tilemap, factory, {"Bat": BAT}) == []
        assert spawn_objects(tilemap, factory, {"Bat": BAT}, include_hidden=True)

    def test_a_hidden_layer_is_skipped_unless_asked_for(
        self, factory: PrefabFactory
    ) -> None:
        tilemap = _map(_rect(), visible=False)

        assert spawn_objects(tilemap, factory, {"Bat": BAT}) == []
        assert spawn_objects(tilemap, factory, {"Bat": BAT}, include_hidden=True)

    def test_layers_choose_what_is_read(self, factory: PrefabFactory) -> None:
        tilemap = _map(_rect(1), name="a")
        tilemap.add_object_layer(ObjectLayer("b", [_rect(2)]))

        spawned = spawn_objects(tilemap, factory, {"Bat": BAT}, layers=["b"])

        assert [s.source.id for s in spawned] == [2]


def test_a_real_tmx_file_all_the_way_to_an_entity(
    factory: PrefabFactory, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "room.tmx"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<map version="1.10" orientation="orthogonal" width="4" height="4"
     tilewidth="16" tileheight="16">
  <objectgroup id="1" name="things">
    <object id="1" name="door" type="Door" x="16" y="32" width="32" height="16">
      <properties><property name="Health.max" type="int" value="7"/></properties>
    </object>
  </objectgroup>
</map>
"""
    )
    door = PrefabData(
        "d", components={"Transform": {}, "TriggerVolume": {}, "Health": {}}
    )

    [spawned] = spawn_objects(load_tmx(str(path)), factory, {"Door": door})

    entity = spawned.entity
    assert entity.get_component(Transform).position == Vector2(32, 40)
    assert entity.get_component(TriggerVolume).dimensions == [32.0, 16.0]
    assert entity.get_component(Health).max == 7
    assert spawned.source.name == "door"


def test_reading_a_map_does_not_import_the_world() -> None:
    """The reason the spawner is its own module: a map stays testable alone."""
    code = (
        "import sys, pyguara.tilemap; "
        "sys.exit(any(m in sys.modules for m in "
        "('pyguara.prefabs.factory', 'pyguara.tilemap.spawning')))"
    )

    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0
