"""Spawn tables pick prefabs by weight, the same way for the same seed."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from pyguara.common.components import Tag, Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.prefabs import (
    ComponentRegistry,
    PrefabData,
    PrefabFactory,
    PrefabInstance,
    SpawnChoice,
    SpawnTable,
    load_spawn_table,
)

PREFABS = {
    "goblin": PrefabData(
        name="goblin",
        components={
            "Transform": {"position": {"x": 1, "y": 2}},
            "Tag": {"name": "goblin"},
        },
    ),
    "orc": PrefabData(name="orc", components={"Tag": {"name": "orc"}}),
}

TABLE = SpawnTable(
    (
        SpawnChoice("goblin", weight=3.0),
        SpawnChoice("orc", weight=1.0, overrides={"Tag": {"name": "big orc"}}),
    )
)


def _factory() -> tuple[PrefabFactory, EntityManager]:
    registry = ComponentRegistry()
    registry.register(Transform)
    registry.register(Tag)
    manager = EntityManager()
    return PrefabFactory(manager, registry, PREFABS.get), manager


class TestPicking:
    def test_the_odds_follow_the_weights(self) -> None:
        counts = Counter(c.prefab for c in TABLE.pick_many(RandomStream(1), 4000))
        assert 0.72 < counts["goblin"] / 4000 < 0.78

    def test_the_same_seed_picks_the_same(self) -> None:
        first = TABLE.pick_many(RandomStream(9), 50)
        assert TABLE.pick_many(RandomStream(9), 50) == first
        assert TABLE.pick_many(RandomStream(10), 50) != first

    def test_a_zero_weight_is_never_picked(self) -> None:
        table = SpawnTable((SpawnChoice("goblin"), SpawnChoice("orc", weight=0.0)))
        assert {c.prefab for c in table.pick_many(RandomStream(2), 500)} == {"goblin"}

    def test_unique_picks_each_choice_at_most_once(self) -> None:
        table = SpawnTable(tuple(SpawnChoice(f"p{i}", weight=i + 1) for i in range(5)))
        picked = table.pick_many(RandomStream(4), 5, unique=True)
        assert sorted(c.prefab for c in picked) == [f"p{i}" for i in range(5)]

    def test_unique_cannot_pick_more_than_there_are(self) -> None:
        with pytest.raises(ValueError, match="different"):
            TABLE.pick_many(RandomStream(1), 3, unique=True)

    def test_a_negative_count_is_refused(self) -> None:
        with pytest.raises(ValueError, match="-1"):
            TABLE.pick_many(RandomStream(1), -1)


class TestValidation:
    @pytest.mark.parametrize("weight", [-1.0, float("nan"), float("inf")])
    def test_a_bad_weight_is_refused(self, weight: float) -> None:
        with pytest.raises(ValueError, match="weight"):
            SpawnChoice("goblin", weight=weight)

    def test_an_empty_table_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            SpawnTable(())

    def test_a_table_of_zero_weights_is_refused(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            SpawnTable((SpawnChoice("goblin", weight=0.0),))


class TestData:
    def test_a_table_reads_from_data(self) -> None:
        table = SpawnTable.from_data(
            {
                "choices": [
                    {"prefab": "goblin", "weight": 3},
                    {"prefab": "orc", "overrides": {"Tag": {"name": "big orc"}}},
                ]
            }
        )
        assert table == SpawnTable(
            (
                SpawnChoice("goblin", 3.0),
                SpawnChoice("orc", 1.0, {"Tag": {"name": "big orc"}}),
            )
        )

    @pytest.mark.parametrize(
        ("data", "match"),
        [
            ({}, "choices"),
            ({"choices": [{"weight": 2}]}, "prefab"),
            ({"choices": [{"prefab": "goblin", "chance": 2}]}, "unknown keys"),
            ({"choices": [{"prefab": "goblin", "weight": "lots"}]}, "weight"),
            ({"choices": [{"prefab": "goblin", "weight": True}]}, "weight"),
        ],
    )
    def test_malformed_data_is_refused(
        self, data: dict[str, object], match: str
    ) -> None:
        with pytest.raises(ValueError, match=match):
            SpawnTable.from_data(data)

    def test_a_table_loads_from_a_file(self, tmp_path: Path) -> None:
        path = tmp_path / "wave.spawn.json"
        path.write_text(json.dumps({"choices": [{"prefab": "goblin"}]}))
        assert load_spawn_table(path) == SpawnTable((SpawnChoice("goblin"),))

    def test_a_bad_file_names_itself(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.spawn.json"
        path.write_text("{not json")
        with pytest.raises(ValueError, match="broken.spawn.json"):
            load_spawn_table(path)

    def test_a_missing_file_says_so(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="nowhere"):
            load_spawn_table(tmp_path / "nowhere.spawn.json")


class TestSpawning:
    def test_spawned_entities_follow_the_picks_and_overrides(self) -> None:
        factory, _ = _factory()
        entities = factory.spawn(TABLE, RandomStream(5), count=40)
        expected = TABLE.pick_many(RandomStream(5), 40)
        names = [e.get_component(Tag).name for e in entities]
        assert names == [
            "goblin" if c.prefab == "goblin" else "big orc" for c in expected
        ]
        assert {e.get_component(PrefabInstance).prefab_path for e in entities} == {
            "goblin",
            "orc",
        }

    def test_positions_place_each_spawn_in_order(self) -> None:
        factory, _ = _factory()
        points = [Vector2(10 * i, -i) for i in range(6)]
        entities = factory.spawn(TABLE, RandomStream(3), count=6, positions=points)
        assert [e.get_component(Transform).position for e in entities] == points

    def test_without_positions_a_prefab_stays_where_it_says(self) -> None:
        factory, _ = _factory()
        table = SpawnTable((SpawnChoice("goblin"),))
        (entity,) = factory.spawn(table, RandomStream(3))
        assert entity.get_component(Transform).position == Vector2(1, 2)

    def test_mismatched_positions_spawn_nothing(self) -> None:
        factory, manager = _factory()
        with pytest.raises(ValueError, match="positions"):
            factory.spawn(TABLE, RandomStream(3), count=2, positions=[Vector2(0, 0)])
        assert list(manager.get_all_entities()) == []

    def test_a_prefab_that_will_not_load_spawns_nothing(self) -> None:
        factory, manager = _factory()
        table = SpawnTable((SpawnChoice("goblin"), SpawnChoice("dragon")))
        with pytest.raises(ValueError, match="dragon"):
            factory.spawn(table, RandomStream(3), count=30)
        assert list(manager.get_all_entities()) == []
