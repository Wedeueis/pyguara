"""Shared fixtures for the Studio tests."""

from __future__ import annotations

import pytest

from pyguara.common.components import Tag, Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.studio.commands.stack import CommandStack


@pytest.fixture
def world() -> EntityManager:
    """An empty world.

    A bare `EntityManager`, with no scene, container, window or renderer.
    Everything in `pyguara/studio/commands` and `pyguara/studio/model`
    works against one directly, which is what keeps these tests fast and
    free of a bootstrap.
    """
    return EntityManager()


@pytest.fixture
def populated(world: EntityManager) -> EntityManager:
    """A world with a small hierarchy, tags and a disabled entity.

    Deliberately varied rather than uniform: the subsystem audit's
    recurring finding is that every test building its subject the same way
    is what hides bugs. A parent with two children, one of them with its
    own child, so a cascade has something to cascade through.
    """
    root = world.create_entity("root")
    root.add_component(Transform(position=Vector2(10, 20)))
    root.add_component(Tag("Root"))
    root.tags.add("level")

    child_a = world.create_entity("child_a")
    child_a.add_component(Transform(position=Vector2(1, 2)))
    world.set_parent("child_a", "root")

    child_b = world.create_entity("child_b")
    child_b.add_component(Transform(position=Vector2(3, 4)))
    child_b.tags.update({"enemy", "spawned"})
    world.set_parent("child_b", "root")

    grandchild = world.create_entity("grandchild")
    grandchild.add_component(Transform())
    world.set_parent("grandchild", "child_b")

    loose = world.create_entity("loose")
    loose.add_component(Transform())
    world.set_entity_enabled("loose", False)

    return world


@pytest.fixture
def stack(populated: EntityManager) -> CommandStack:
    """A command stack over the populated world."""
    return CommandStack(populated)


@pytest.fixture
def core_registry():
    """A component registry wired as `create_application()` wires it."""
    from pyguara.application.bootstrap import _register_core_components
    from pyguara.prefabs.registry import ComponentRegistry

    registry = ComponentRegistry()
    _register_core_components(registry)
    return registry


@pytest.fixture
def session(populated: EntityManager, core_registry):
    """A Studio session over the populated world, applying edits at once."""
    from pyguara.studio.session import StudioSession

    return StudioSession(
        populated, scene_name="test_scene", component_registry=core_registry
    )


@pytest.fixture
def ops():
    """A fresh operation registry, isolated from the process-wide one."""
    from pyguara.studio.ops.builtin import build_registry

    return build_registry()
