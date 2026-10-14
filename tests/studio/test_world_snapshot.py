"""Copying a world and putting it back -- what Stop restores.

`PlayControlsPanel` used to say outright that there was no "reset to where
play began", and the reason was good: the only mechanism for restoring a
world was `SceneSerializer`, which silently skips any component the
registry does not know -- which is every component a *game* defines unless
it registered them. A reset that quietly dropped the player's controller
would be worse than no reset.

`WorldSnapshot` does not go through the serializer. It copies the live
components, the way the command stack already captures a subtree, so a
component it has never heard of is copied exactly as well as one it has.
Measured on `guara_falcao`: 252 entities, 14 ms each way, nothing lost.
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
