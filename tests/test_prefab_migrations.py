"""Old prefab files upgrade as they load, and a bad version says which file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from pyguara.common.components import Tag, Transform
from pyguara.ecs.manager import EntityManager
from pyguara.persistence.migration import Migration, MigrationManager
from pyguara.prefabs import (
    ComponentRegistry,
    PrefabCache,
    PrefabFactory,
    PrefabLoader,
)


def _rename_label(data: dict[str, Any]) -> dict[str, Any]:
    """v1 -> v2: the `Label` component became `Tag`."""
    components = data.setdefault("components", {})
    if "Label" in components:
        components["Tag"] = {"name": components.pop("Label")["text"]}
    return data


def _scale_up(data: dict[str, Any]) -> dict[str, Any]:
    """v2 -> v3: every tag gained a prefix."""
    tag = data.get("components", {}).get("Tag")
    if tag is not None:
        tag["name"] = f"v3:{tag['name']}"
    return data


def _manager() -> MigrationManager:
    manager = MigrationManager(current_version=3)
    manager.register(Migration(1, 2, _rename_label, "Label -> Tag"))
    manager.register(Migration(2, 3, _scale_up, "prefix tags"))
    return manager


def _write(directory: Path, name: str, data: dict[str, Any]) -> str:
    path = directory / f"{name}.prefab.json"
    path.write_text(json.dumps(data))
    return str(path)


def test_an_old_file_upgrades_through_every_step(tmp_path: Path) -> None:
    path = _write(
        tmp_path, "goblin", {"name": "goblin", "components": {"Label": {"text": "gob"}}}
    )

    data = PrefabLoader(_manager()).load(path).data

    assert data.version == 3
    assert data.components == {"Tag": {"name": "v3:gob"}}


def test_a_file_part_way_takes_only_the_steps_left(tmp_path: Path) -> None:
    path = _write(
        tmp_path, "orc", {"version": 2, "components": {"Tag": {"name": "orc"}}}
    )
    assert PrefabLoader(_manager()).load(path).data.components == {
        "Tag": {"name": "v3:orc"}
    }


def test_a_current_file_is_left_as_it_is(tmp_path: Path) -> None:
    path = _write(
        tmp_path, "imp", {"version": 3, "components": {"Tag": {"name": "imp"}}}
    )
    assert PrefabLoader(_manager()).load(path).data.components == {
        "Tag": {"name": "imp"}
    }


def test_without_migrations_a_file_loads_as_written(tmp_path: Path) -> None:
    path = _write(
        tmp_path, "old", {"version": 7, "components": {"Label": {"text": "x"}}}
    )
    data = PrefabLoader().load(path).data
    assert (data.version, data.components) == (7, {"Label": {"text": "x"}})


@pytest.mark.parametrize(
    ("version", "match"),
    [(4, "newer"), (0, "whole number"), ("2", "whole number"), (True, "whole number")],
)
def test_a_version_the_loader_cannot_reach_names_the_file(
    tmp_path: Path, version: object, match: str
) -> None:
    path = _write(tmp_path, "future", {"version": version, "components": {}})
    with pytest.raises(ValueError, match=match) as raised:
        PrefabLoader(_manager()).load(path)
    assert "future.prefab.json" in str(raised.value)


def test_a_missing_step_names_the_file(tmp_path: Path) -> None:
    manager = MigrationManager(current_version=3)
    manager.register(Migration(2, 3, _scale_up))
    path = _write(tmp_path, "gap", {"version": 1, "components": {}})
    with pytest.raises(ValueError, match="gap.prefab.json.*No migration"):
        PrefabLoader(manager).load(path)


def test_a_failing_step_names_the_file(tmp_path: Path) -> None:
    def broken(data: dict[str, Any]) -> dict[str, Any]:
        raise KeyError("hp")

    manager = MigrationManager(current_version=2)
    manager.register(Migration(1, 2, broken))
    path = _write(tmp_path, "broken", {"components": {}})
    with pytest.raises(ValueError, match="broken.prefab.json.*v1 -> v2 failed"):
        PrefabLoader(manager).load(path)


def test_a_parent_upgrades_too_when_a_child_extends_it(tmp_path: Path) -> None:
    parent = _write(
        tmp_path,
        "base",
        {"name": "base", "components": {"Label": {"text": "base"}, "Transform": {}}},
    )
    child = _write(
        tmp_path, "elite", {"version": 3, "name": "elite", "extends": parent}
    )
    registry = ComponentRegistry()
    registry.register(Transform)
    registry.register(Tag)
    cache = PrefabCache(PrefabLoader(_manager()))
    factory = PrefabFactory(EntityManager(), registry, cache.load)

    entity = factory.create_from_path(child)

    assert entity is not None
    assert entity.get_component(Tag).name == "v3:base"


def test_the_application_shares_its_prefab_loader() -> None:
    from pyguara.application.bootstrap import create_headless_application
    from pyguara.resources.manager import ResourceManager

    application = create_headless_application()
    loader = application.container.get(PrefabLoader)
    assert isinstance(loader, PrefabLoader)
    resources = application.container.get(ResourceManager)
    # The same object the resource manager loads prefabs with, so migrations
    # set on it reach every prefab the game loads.
    assert any(registered is loader for registered in resources._extension_map.values())


def test_migrations_set_on_the_application_reach_a_scenes_spawns(
    tmp_path: Path,
) -> None:
    from pyguara.application.bootstrap import create_headless_application
    from pyguara.scene.base import Scene

    path = _write(
        tmp_path, "goblin", {"name": "goblin", "components": {"Label": {"text": "gob"}}}
    )
    application = create_headless_application()
    application.container.get(PrefabLoader).migrations = _manager()

    class _Level(Scene):
        def on_enter(self) -> None:
            pass

        def on_exit(self) -> None:
            pass

        def update(self, dt: float) -> None:
            pass

    scene = _Level("level")
    scene.resolve_dependencies(application.container)

    entity = scene.prefab_factory.create_from_path(path)

    assert entity is not None
    assert entity.get_component(Tag).name == "v3:gob"
