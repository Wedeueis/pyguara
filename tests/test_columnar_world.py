"""`ColumnarWorld`: what the native column store promises.

Not a parity suite -- there is no second store. The reference each
property is held to is stated in its test: the object ECS's ordering
rules for removal, Python's own float arithmetic for `add_scaled`, and
memory safety for everything about arrays.

**Setup is varied on purpose.** The audit's recurring finding was that a
suite building its subject one way hides every bug that needs another, so
the ordering tests below remove from the front, the middle and the end,
before and after a flush, with and without a re-add.
"""

from __future__ import annotations

import gc
from dataclasses import dataclass

import numpy as np
import pytest

from pyguara.columnar import TOMBSTONE, ColumnarWorld, schema_for
from pyguara.common.types import Vector2


@dataclass
class Position:
    value: Vector2


@dataclass
class Velocity:
    value: Vector2


@dataclass
class Stats:
    health: float
    level: int
    alive: bool


def _world_with(count: int) -> tuple[ColumnarWorld, list[int]]:
    world = ColumnarWorld()
    entities = world.spawn_many(count)
    for number, entity in enumerate(entities):
        world.add(entity, Position(Vector2(float(number), -float(number))))
    return world, entities


class TestSchema:
    def test_a_vector_field_is_two_float_columns(self) -> None:
        schema = schema_for(Position)

        assert schema.column_names == ("value.x", "value.y")
        assert schema.dtypes == ("f8", "f8")

    def test_bool_is_not_mistaken_for_int(self) -> None:
        # bool subclasses int; matched in the wrong order a flag becomes
        # an eight-byte integer and reads back as 1.
        assert schema_for(Stats).dtypes == ("f8", "i8", "u1")

    def test_an_unstorable_field_is_named(self) -> None:
        @dataclass
        class Named:
            label: str

        with pytest.raises(TypeError, match=r"Named\.label"):
            schema_for(Named)

    def test_a_plain_class_is_refused(self) -> None:
        class NotADataclass:
            pass

        with pytest.raises(TypeError, match="not a dataclass"):
            schema_for(NotADataclass)


class TestEntities:
    def test_a_despawned_id_never_resolves_again(self) -> None:
        world = ColumnarWorld()
        first = world.spawn()
        world.despawn(first)

        second = world.spawn()

        # Same slot, new generation: the stale id must not alias it.
        assert second != first
        assert second & 0xFFFFFFFF == first & 0xFFFFFFFF
        assert not world.is_alive(first)
        assert world.is_alive(second)

    def test_a_stale_id_cannot_read_the_new_occupant(self) -> None:
        world = ColumnarWorld()
        stale = world.spawn()
        world.add(stale, Stats(1.0, 1, True))
        world.despawn(stale)
        fresh = world.spawn()
        world.add(fresh, Stats(9.0, 9, True))

        assert not world.has(stale, Stats)
        with pytest.raises(KeyError):
            world.get(stale, Stats)

    def test_despawning_twice_reports_it(self) -> None:
        world = ColumnarWorld()
        entity = world.spawn()

        assert world.despawn(entity) is True
        assert world.despawn(entity) is False
        assert world.entity_count == 0


class TestValues:
    def test_what_goes_in_comes_out_with_its_type(self) -> None:
        world = ColumnarWorld()
        entity = world.spawn()
        world.add(entity, Stats(health=0.1, level=2**40, alive=True))

        stored = world.get(entity, Stats)

        assert stored == Stats(0.1, 2**40, True)
        assert type(stored.alive) is bool
        assert type(stored.level) is int

    def test_a_float_survives_exactly(self) -> None:
        # f8, not f4: 0.1 has no exact f32 and would read back changed.
        world = ColumnarWorld()
        entity = world.spawn()
        world.add(entity, Position(Vector2(0.1, 1e-300)))

        assert world.view(entity, Position).value == Vector2(0.1, 1e-300)

    def test_a_view_writes_through(self) -> None:
        world, entities = _world_with(3)

        world.view(entities[1], Position).value = Vector2(7.0, 8.0)

        assert world.get(entities[1], Position).value == Vector2(7.0, 8.0)
        assert world.get(entities[0], Position).value == Vector2(0.0, 0.0)

    def test_the_instance_passed_to_add_is_copied_not_kept(self) -> None:
        world = ColumnarWorld()
        entity = world.spawn()
        original = Stats(1.0, 1, False)
        world.add(entity, original)

        original.health = 99.0

        assert world.view(entity, Stats).health == 1.0

    def test_one_component_of_a_type_per_entity(self) -> None:
        world, entities = _world_with(1)

        with pytest.raises(ValueError, match="already has"):
            world.add(entities[0], Position(Vector2(0.0, 0.0)))

    def test_a_refused_value_leaves_every_column_the_same_length(self) -> None:
        world = ColumnarWorld()
        entity = world.spawn()

        # `health` is accepted and pushed before `level` is refused.
        with pytest.raises(TypeError):
            world.add(entity, Stats(1.0, "seven", True))  # type: ignore[arg-type]

        assert world.count(Stats) == 0
        world.add(entity, Stats(2.0, 7, True))
        arrays = world.arrays(Stats)
        assert [len(arrays[name]) for name in arrays] == [1, 1, 1]
        assert arrays["health"][0] == 2.0

    def test_a_view_of_a_missing_component_raises_on_use(self) -> None:
        world = ColumnarWorld()
        entity = world.spawn()
        world.register(Stats)

        with pytest.raises(KeyError, match="Stats"):
            _ = world.view(entity, Stats).health


class TestOrder:
    """Rows keep insertion order, which is what queries iterate in (#324)."""

    @pytest.mark.parametrize("victims", [[0], [4], [2], [0, 1], [1, 3], [0, 2, 4]])
    def test_removal_keeps_the_survivors_in_order(self, victims: list[int]) -> None:
        world, entities = _world_with(5)

        for victim in victims:
            world.remove(entities[victim], Position)
        world.flush()

        survivors = [entity for i, entity in enumerate(entities) if i not in victims]
        arrays = world.arrays(Position)
        assert arrays.entities.tolist() == survivors
        assert arrays["value.x"].tolist() == [
            float(i) for i in range(5) if i not in victims
        ]

    def test_a_readded_component_goes_to_the_end(self) -> None:
        # The object ECS's index is a dict used as an ordered set, where a
        # remove-then-add moves the key to the back. Same here.
        world, entities = _world_with(3)

        world.remove(entities[0], Position)
        world.add(entities[0], Position(Vector2(50.0, 50.0)))

        assert world.arrays(Position).entities.tolist() == [
            entities[1],
            entities[2],
            entities[0],
        ]

    def test_lookups_see_a_removal_before_the_flush(self) -> None:
        world, entities = _world_with(3)

        world.remove(entities[1], Position)

        assert not world.has(entities[1], Position)
        assert world.count(Position) == 2

    def test_lookups_still_find_rows_that_moved_in_a_flush(self) -> None:
        world, entities = _world_with(4)
        world.despawn(entities[0])
        world.flush()

        assert world.get(entities[3], Position).value == Vector2(3.0, -3.0)


class TestArrays:
    def test_an_array_is_the_column_not_a_copy(self) -> None:
        world, entities = _world_with(3)
        arrays = world.arrays(Position)

        arrays["value.x"][2] = 123.0
        world.view(entities[0], Position).value = Vector2(-1.0, -2.0)

        assert world.get(entities[2], Position).value.x == 123.0
        assert arrays["value.y"][0] == -2.0

    def test_dtypes_follow_the_schema(self) -> None:
        world = ColumnarWorld()
        world.add(world.spawn(), Stats(1.0, 2, True))
        arrays = world.arrays(Stats)

        assert [arrays[name].dtype for name in arrays] == [
            np.float64,
            np.int64,
            np.uint8,
        ]
        assert arrays.entities.dtype == np.uint64

    def test_the_entity_column_cannot_be_written(self) -> None:
        world, _ = _world_with(2)

        with pytest.raises(ValueError, match="read-only"):
            world.arrays(Position).entities[0] = 5

    def test_growing_under_a_live_array_is_refused(self) -> None:
        world, _ = _world_with(4)
        arrays = world.arrays(Position)

        # Enough inserts that the column must reallocate at some point.
        with pytest.raises(BufferError, match="Position"):
            for _ in range(1000):
                world.add(world.spawn(), Position(Vector2(0.0, 0.0)))

        # And the array still reads the memory it was given.
        assert arrays["value.x"][:4].tolist() == [0.0, 1.0, 2.0, 3.0]

    def test_dropping_the_array_releases_the_pin(self) -> None:
        world, _ = _world_with(4)
        arrays = world.arrays(Position)
        del arrays
        gc.collect()

        for _ in range(1000):
            world.add(world.spawn(), Position(Vector2(0.0, 0.0)))

        assert world.count(Position) == 1004

    def test_a_removal_under_a_live_array_is_a_tombstone(self) -> None:
        # The loop the engine actually runs: iterate, destroy, carry on.
        world, entities = _world_with(3)
        arrays = world.arrays(Position)

        world.despawn(entities[1])

        assert arrays.entities.tolist() == [entities[0], TOMBSTONE, entities[2]]
        with pytest.raises(BufferError):
            world.flush()
        del arrays
        gc.collect()
        world.flush()
        assert world.arrays(Position).entities.tolist() == [entities[0], entities[2]]

    def test_an_unknown_column_names_the_real_ones(self) -> None:
        world, _ = _world_with(1)

        with pytest.raises(KeyError, match=r"value\.x"):
            world.arrays(Position)["x"]


class TestVersions:
    def test_a_write_moves_only_its_own_column(self) -> None:
        world = ColumnarWorld()
        entity = world.spawn()
        world.add(entity, Stats(1.0, 1, True))
        health, level = world.version(Stats, "health"), world.version(Stats, "level")

        world.view(entity, Stats).health = 2.0

        assert world.version(Stats, "health") > health
        assert world.version(Stats, "level") == level

    def test_reading_does_not_move_it(self) -> None:
        world = ColumnarWorld()
        entity = world.spawn()
        world.add(entity, Stats(1.0, 1, True))
        before = world.version(Stats, "health")

        _ = world.view(entity, Stats).health
        _ = world.get(entity, Stats)

        assert world.version(Stats, "health") == before

    def test_a_native_write_moves_it(self) -> None:
        world, entities = _world_with(2)
        world.add(entities[0], Velocity(Vector2(1.0, 1.0)))
        before = world.version(Position, "value.x")

        world.add_scaled(Position, "value.x", Velocity, "value.x", 1.0)

        assert world.version(Position, "value.x") > before


class TestAddScaled:
    def test_it_is_the_same_arithmetic_python_does(self) -> None:
        # `==`, not approx: one multiply and one add in f64 has one answer.
        world = ColumnarWorld()
        entities = world.spawn_many(50)
        expected = []
        for number, entity in enumerate(entities):
            start, speed = number * 0.1, number * 0.37 - 3.0
            world.add(entity, Position(Vector2(start, 0.0)))
            world.add(entity, Velocity(Vector2(speed, 0.0)))
            expected.append(start + speed * (1 / 60))

        world.add_scaled(Position, "value.x", Velocity, "value.x", 1 / 60)

        assert world.arrays(Position)["value.x"].tolist() == expected

    def test_only_entities_holding_both_move(self) -> None:
        world, entities = _world_with(4)
        world.add(entities[1], Velocity(Vector2(10.0, 0.0)))
        world.add(entities[3], Velocity(Vector2(10.0, 0.0)))

        moved = world.add_scaled(Position, "value.x", Velocity, "value.x", 1.0)

        assert moved == 2
        assert world.arrays(Position)["value.x"].tolist() == [0.0, 11.0, 2.0, 13.0]

    def test_rows_in_different_orders_still_pair_by_entity(self) -> None:
        # Velocity is attached in reverse, so its rows run the other way
        # to Position's: pairing by row number would move the wrong ones.
        world, entities = _world_with(3)
        for number, entity in reversed(list(enumerate(entities))):
            world.add(entity, Velocity(Vector2(float(number) * 100, 0.0)))

        world.add_scaled(Position, "value.x", Velocity, "value.x", 1.0)

        assert world.arrays(Position)["value.x"].tolist() == [0.0, 101.0, 202.0]

    def test_a_removed_source_row_is_skipped(self) -> None:
        world, entities = _world_with(2)
        for entity in entities:
            world.add(entity, Velocity(Vector2(5.0, 0.0)))
        world.remove(entities[0], Velocity)

        assert world.add_scaled(Position, "value.x", Velocity, "value.x", 1.0) == 1
        assert world.arrays(Position)["value.x"].tolist() == [0.0, 6.0]

    def test_a_non_float_column_is_refused(self) -> None:
        world = ColumnarWorld()
        entity = world.spawn()
        world.add(entity, Stats(1.0, 1, True))
        world.add(entity, Position(Vector2(0.0, 0.0)))

        with pytest.raises(TypeError, match="f8"):
            world.add_scaled(Position, "value.x", Stats, "level", 1.0)
