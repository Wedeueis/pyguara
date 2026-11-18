"""Copying a world and putting it back -- what Stop restores.

`WorldSnapshot` copies the live components and does not go through
`SceneSerializer`, which skips any component the registry does not
know. So a component a game defines and never registered is copied
like any other, and a reset loses nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.ecs.manager import EntityManager
from pyguara.studio.model.worldsnapshot import WorldSnapshot


@dataclass
class Unregistered(BaseComponent):
    """A component no registry has ever heard of.

    The case the serializer could not carry, and the reason this module
    exists.
    """

    notes: str = ""
    extras: list[int] | None = None


@dataclass
class WithHandle(BaseComponent):
    """Stands in for `RigidBody`, which holds the physics backend's body."""

    mass: float = 1.0
    _body_handle: object | None = None


class _Uncopyable:
    """A live engine object that refuses to be copied, as Rapier's does."""

    def __reduce_ex__(self, protocol: object) -> object:
        raise TypeError("cannot pickle a native world")


@pytest.fixture
def world() -> EntityManager:
    """A world with a hierarchy, tags, a disabled entity and oddities."""
    manager = EntityManager()
    root = manager.create_entity("root")
    root.add_component(Transform(position=Vector2(10, 20)))
    root.add_component(Unregistered(notes="hand written", extras=[1, 2]))
    root.tags.add("level")

    child = manager.create_entity("child")
    child.add_component(Transform(position=Vector2(5, 5)))
    manager.set_parent("child", "root")

    grandchild = manager.create_entity("grandchild")
    grandchild.add_component(Transform())
    manager.set_parent("grandchild", "child")

    loner = manager.create_entity("loner")
    loner.add_component(Transform())
    manager.set_entity_enabled("loner", False)
    return manager


@pytest.mark.unit
class TestCapture:
    def test_it_holds_every_entity(self, world: EntityManager) -> None:
        snapshot = WorldSnapshot.capture(world)

        assert snapshot.count == 4

    def test_a_component_no_registry_knows_survives(self, world: EntityManager) -> None:
        """The whole reason not to go through the serializer."""
        snapshot = WorldSnapshot.capture(world)
        world.clear()

        snapshot.restore(world)

        notes = world.get_entity("root").get_component(Unregistered)
        assert notes.notes == "hand written"
        assert notes.extras == [1, 2]

    def test_it_copies_rather_than_references(self, world: EntityManager) -> None:
        """The obvious mistake: holding the live component means the game
        mutates the very object the snapshot is meant to restore, and Stop
        puts back exactly what play left behind."""
        snapshot = WorldSnapshot.capture(world)

        world.get_entity("root").get_component(Transform).position = Vector2(999, 999)
        snapshot.restore(world)

        assert world.get_entity("root").get_component(Transform).position == Vector2(
            10, 20
        )

    def test_a_nested_value_is_copied_too(self, world: EntityManager) -> None:
        """A shallow copy would share the list and the move would survive."""
        snapshot = WorldSnapshot.capture(world)

        world.get_entity("root").get_component(Unregistered).extras.append(3)
        snapshot.restore(world)

        assert world.get_entity("root").get_component(Unregistered).extras == [1, 2]

    def test_an_engine_handle_is_cleared(self) -> None:
        """A copied body handle points at a body the backend removed with
        the entity. Cleared, the physics system builds a fresh one -- which
        is exactly what it does for an entity it has not seen."""
        world = EntityManager()
        entity = world.create_entity("body")
        entity.add_component(Transform())
        entity.add_component(WithHandle(mass=3.0, _body_handle=object()))

        snapshot = WorldSnapshot.capture(world)
        world.clear()
        snapshot.restore(world)

        restored = world.get_entity("body").get_component(WithHandle)
        assert restored.mass == 3.0
        assert restored._body_handle is None

    def test_a_handle_that_cannot_be_copied_is_not_copied(self) -> None:
        """Rapier's body refers to a native world that cannot be pickled,
        and Play failed copying it -- only to throw the copy away."""
        world = EntityManager()
        world.create_entity("body").add_component(
            WithHandle(mass=1.0, _body_handle=_Uncopyable())
        )

        snapshot = WorldSnapshot.capture(world)

        (component,) = snapshot.entities[0].components
        assert component._body_handle is None  # type: ignore[attr-defined]

    def test_a_duplicated_component_has_no_body(self) -> None:
        """Duplicating an entity copies its components the same way. With
        the handle copied, the physics system took the duplicate for one
        it had already built and never gave it a body."""
        from pyguara.studio.commands.entity import copy_component

        original = WithHandle(mass=2.0, _body_handle=_Uncopyable())

        duplicate = copy_component(original)

        assert duplicate.mass == 2.0  # type: ignore[attr-defined]
        assert duplicate._body_handle is None  # type: ignore[attr-defined]
        assert original._body_handle is not None


@pytest.mark.unit
class TestRestore:
    def test_the_hierarchy_comes_back(self, world: EntityManager) -> None:
        snapshot = WorldSnapshot.capture(world)
        world.clear()

        snapshot.restore(world)

        assert world.parent_of("child") == "root"
        assert world.parent_of("grandchild") == "child"
        assert world.parent_of("root") is None

    def test_tags_and_enabled_state_come_back(self, world: EntityManager) -> None:
        """Both live outside the components, which is how they were lost
        before anyone noticed."""
        snapshot = WorldSnapshot.capture(world)
        world.clear()

        snapshot.restore(world)

        assert "level" in world.get_entity("root").tags
        assert world.is_entity_enabled("loner") is False

    def test_whatever_play_created_is_gone(self, world: EntityManager) -> None:
        """A restore that merged would leave it behind, which is the half
        of "reset" people notice missing."""
        snapshot = WorldSnapshot.capture(world)
        spawned = world.create_entity("bullet")
        spawned.add_component(Transform())

        snapshot.restore(world)

        assert world.get_entity("bullet") is None

    def test_whatever_play_destroyed_comes_back(self, world: EntityManager) -> None:
        snapshot = WorldSnapshot.capture(world)
        world.remove_entity("child")

        snapshot.restore(world)

        assert world.get_entity("child") is not None
        assert world.parent_of("grandchild") == "child"

    def test_it_can_restore_twice(self, world: EntityManager) -> None:
        """Stop, Play, Stop. The second restore must not hand back objects
        the first run already mutated."""
        snapshot = WorldSnapshot.capture(world)

        snapshot.restore(world)
        world.get_entity("root").get_component(Transform).position = Vector2(1, 1)
        snapshot.restore(world)

        assert world.get_entity("root").get_component(Transform).position == Vector2(
            10, 20
        )

    def test_an_empty_world_round_trips(self) -> None:
        world = EntityManager()
        snapshot = WorldSnapshot.capture(world)

        snapshot.restore(world)

        assert list(world.get_all_entities()) == []
