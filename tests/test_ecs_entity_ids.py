"""An entity id names one live entity per world."""

from __future__ import annotations

import pytest

from pyguara.common.components import Tag
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager


def test_creating_a_second_entity_with_a_taken_id_is_refused() -> None:
    manager = EntityManager()
    first = manager.create_entity("torch")
    first.add_component(Tag(name="first"))

    with pytest.raises(ValueError, match="'torch' already exists"):
        manager.create_entity("torch")

    # The first is untouched: reachable by id and by query, once.
    assert manager.get_entity("torch") is first
    assert list(manager.get_entities_with(Tag)) == [first]


def test_adding_an_entity_whose_id_is_taken_is_refused() -> None:
    manager = EntityManager()
    manager.create_entity("torch")
    with pytest.raises(ValueError, match="already exists"):
        manager.add_entity(Entity("torch"))


def test_adding_the_same_entity_twice_is_refused() -> None:
    manager = EntityManager()
    entity = manager.create_entity()
    with pytest.raises(ValueError, match="already exists"):
        manager.add_entity(entity)


def test_an_id_is_free_again_once_its_entity_is_removed() -> None:
    manager = EntityManager()
    manager.remove_entity(manager.create_entity("torch").id)

    again = manager.create_entity("torch")

    assert manager.get_entity("torch") is again


def test_a_clone_takes_a_fresh_id() -> None:
    manager = EntityManager()
    original = manager.create_entity("torch")
    original.add_component(Tag(name="t"))

    clone = original.clone()
    manager.add_entity(clone)

    assert clone.id != original.id
    assert len(list(manager.get_entities_with(Tag))) == 2
