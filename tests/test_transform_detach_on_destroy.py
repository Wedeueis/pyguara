"""A destroyed entity's `Transform` leaves the spatial hierarchy."""

from __future__ import annotations

import pytest

from pyguara.application.bootstrap import create_headless_application
from pyguara.common.components import Transform, set_parent
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.scene.base import Scene


class _Level(Scene):
    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        pass


@pytest.fixture(scope="module")
def container():  # noqa: ANN201
    return create_headless_application().container


def _scene(container) -> _Level:  # noqa: ANN001
    scene = _Level("level")
    scene.resolve_dependencies(container)
    return scene


def _with_transform(scene: Scene, x: float = 0.0) -> tuple[Entity, Transform]:
    entity = scene.entity_manager.create_entity()
    transform = Transform(position=Vector2(x, 0))
    entity.add_component(transform)
    return entity, transform


def test_a_destroyed_child_leaves_its_parents_children(container) -> None:  # noqa: ANN001
    scene = _scene(container)
    _, parent = _with_transform(scene)
    child_entity, child = _with_transform(scene)
    set_parent(child, parent)

    scene.entity_manager.remove_entity(child_entity.id)
    scene.entity_manager.flush_pending_removals()

    assert parent.children == []
    assert child.parent is None


def test_spawning_and_destroying_children_does_not_grow_the_list(container) -> None:  # noqa: ANN001
    scene = _scene(container)
    _, parent = _with_transform(scene)

    for _ in range(50):
        entity, child = _with_transform(scene)
        set_parent(child, parent)
        scene.entity_manager.remove_entity(entity.id)
        scene.entity_manager.flush_pending_removals()

    assert parent.children == []


def test_a_child_that_outlives_its_parent_stays_where_it_was(container) -> None:  # noqa: ANN001
    scene = _scene(container)
    parent_entity, parent = _with_transform(scene, x=100.0)
    _, child = _with_transform(scene, x=0.0)
    set_parent(child, parent, keep_world_transform=False)
    assert child.world_position == Vector2(100, 0)

    scene.entity_manager.remove_entity(parent_entity.id)
    scene.entity_manager.flush_pending_removals()

    assert child.parent is None
    assert child.world_position == Vector2(100, 0)


def test_an_owned_child_goes_with_its_parent_and_both_detach(container) -> None:  # noqa: ANN001
    scene = _scene(container)
    root_entity, root = _with_transform(scene)
    parent_entity, parent = _with_transform(scene)
    child_entity, child = _with_transform(scene)
    set_parent(parent, root)
    set_parent(child, parent)
    scene.entity_manager.set_parent(child_entity.id, parent_entity.id)

    scene.entity_manager.remove_entity(parent_entity.id)
    scene.entity_manager.flush_pending_removals()

    assert root.children == []
    assert parent.children == []
    assert root_entity.id in {e.id for e in scene.entity_manager.get_all_entities()}
