"""The `resources` operation, against a real resource manager and real files.

Nothing here mocks the manager: the listing, the preview and the reload
are only worth having if they agree with what `ResourceManager` would
load, so each test indexes a directory on disk and asks about it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyguara.common.components import ResourceLink, Transform
from pyguara.ecs.manager import EntityManager
from pyguara.resources.loaders.data_loader import JsonLoader
from pyguara.resources.manager import ResourceManager
from pyguara.studio.ops.registry import OperationRegistry
from pyguara.studio.ops.resources import DATA_EXTENSIONS
from pyguara.studio.session import ApprovalMode, StudioSession

CRATE = {
    "Transform": {"position": {"x": 40, "y": 50}},
    "Tag": {"name": "Crate"},
    "notes": "not a component",
}


@pytest.fixture
def assets(tmp_path: Path) -> Path:
    """A small asset directory: two data files and one nothing can load."""
    root = tmp_path / "assets"
    (root / "props").mkdir(parents=True)
    (root / "props" / "crate.json").write_text(json.dumps(CRATE), encoding="utf-8")
    (root / "tuning.json").write_text(json.dumps({"speed": 3}), encoding="utf-8")
    (root / "readme.xyz").write_text("ignored", encoding="utf-8")
    return root


@pytest.fixture
def manager(assets: Path) -> ResourceManager:
    """A resource manager that loads JSON and has indexed the directory."""
    manager = ResourceManager()
    manager.register_loader(JsonLoader())
    manager.index_directory(str(assets))
    return manager


@pytest.fixture
def session(populated: EntityManager, core_registry, manager) -> StudioSession:
    """A session that can reach the resource manager."""
    return StudioSession(
        populated, component_registry=core_registry, resource_manager=manager
    )


def call(ops: OperationRegistry, session: StudioSession, **arguments: object):
    """Invoke `resources` and return the `OperationResult`."""
    return ops.invoke(session, "resources", dict(arguments))


class TestList:
    """What is indexed and what is loaded."""

    def test_each_file_is_listed_once_with_its_names(
        self, ops, session, assets
    ) -> None:
        result = call(ops, session, operation="list")
        assert result.ok, result.error
        by_path = {entry["path"]: entry["names"] for entry in result.result["indexed"]}
        assert by_path == {
            str(assets / "props" / "crate.json"): ["crate", "crate.json"],
            str(assets / "tuning.json"): ["tuning", "tuning.json"],
        }
        assert result.result["indexed_total"] == 2

    def test_nothing_is_loaded_by_listing(self, ops, session, manager) -> None:
        assert call(ops, session, operation="list").result["loaded"] == []
        assert list(manager.iter_cached()) == []

    def test_a_loaded_resource_reports_its_type(self, ops, session, assets) -> None:
        call(ops, session, operation="preview", name="tuning")
        loaded = call(ops, session, operation="list").result["loaded"]
        assert [(entry["path"], entry["type"]) for entry in loaded] == [
            (str(assets / "tuning.json"), "DataResource")
        ]

    def test_the_filter_matches_a_path_or_a_name(self, ops, session) -> None:
        result = call(ops, session, operation="list", filter="PROPS").result
        assert [Path(entry["path"]).name for entry in result["indexed"]] == [
            "crate.json"
        ]

    def test_a_limit_cuts_the_list_and_keeps_the_total(self, ops, session) -> None:
        result = call(ops, session, operation="list", limit=1).result
        assert len(result["indexed"]) == 1
        assert result["indexed_total"] == 2

    def test_the_result_is_json(self, ops, session) -> None:
        json.dumps(call(ops, session, operation="list").result)


class TestPreview:
    """Looking inside one resource."""

    def test_a_data_file_shows_its_contents(self, ops, session) -> None:
        result = call(ops, session, operation="preview", name="crate")
        assert result.ok, result.error
        assert result.result["loaded"] is True
        assert result.result["type"] == "DataResource"
        assert result.result["data"] == CRATE

    def test_a_path_works_as_well_as_a_name(self, ops, session, assets) -> None:
        path = str(assets / "tuning.json")
        result = call(ops, session, operation="preview", name=path)
        assert result.result["path"] == path
        assert result.result["data"] == {"speed": 3}

    def test_a_file_that_is_not_data_is_not_loaded_to_be_looked_at(
        self, ops, session, manager, assets
    ) -> None:
        result = call(ops, session, operation="preview", name=str(assets / "hero.png"))
        assert result.ok, result.error
        assert result.result == {"path": str(assets / "hero.png"), "loaded": False}
        assert list(manager.iter_cached()) == []

    def test_a_missing_data_file_says_so(self, ops, session, assets) -> None:
        result = call(ops, session, operation="preview", name=str(assets / "gone.json"))
        assert not result.ok
        assert "gone.json" in result.error

    def test_a_broken_data_file_says_so(self, ops, session, assets) -> None:
        (assets / "broken.json").write_text("{not json", encoding="utf-8")
        result = call(
            ops, session, operation="preview", name=str(assets / "broken.json")
        )
        assert not result.ok
        assert "broken.json" in result.error


class TestSpawn:
    """An entity from a data file."""

    def test_each_component_key_becomes_a_component(self, ops, session) -> None:
        result = call(ops, session, operation="spawn", name="crate")
        assert result.ok, result.error
        assert result.result["entity_id"] == "crate"
        entity = session.world.get_entity("crate")
        assert entity is not None
        transform = entity.get_component(Transform)
        assert (transform.position.x, transform.position.y) == (40, 50)

    def test_the_keys_that_were_not_components_are_reported(self, ops, session) -> None:
        result = call(ops, session, operation="spawn", name="crate")
        assert result.result["skipped"] == ["notes"]

    def test_the_entity_records_where_it_came_from(self, ops, session, assets) -> None:
        call(ops, session, operation="spawn", name="crate")
        link = session.world.get_entity("crate").get_component(ResourceLink)
        assert link.resource_path == str(assets / "props" / "crate.json")

    def test_it_is_one_undoable_entry(self, ops, session) -> None:
        call(ops, session, operation="spawn", name="crate")
        assert session.stack.undo_labels[-1:] != ()
        session.undo()
        assert session.world.get_entity("crate") is None
        session.redo()
        assert session.world.get_entity("crate") is not None

    def test_a_second_spawn_gets_a_free_id(self, ops, session) -> None:
        call(ops, session, operation="spawn", name="crate")
        second = call(ops, session, operation="spawn", name="crate")
        third = call(ops, session, operation="spawn", name="crate")
        assert second.result["entity_id"] == "crate_2"
        assert third.result["entity_id"] == "crate_3"

    def test_an_id_can_be_given(self, ops, session) -> None:
        result = call(ops, session, operation="spawn", name="crate", entity_id="box_a")
        assert result.result["entity_id"] == "box_a"
        assert session.world.get_entity("box_a") is not None

    def test_a_taken_id_is_refused(self, ops, session) -> None:
        result = call(ops, session, operation="spawn", name="crate", entity_id="root")
        assert not result.ok
        assert "root" in result.error

    def test_a_file_with_no_component_is_refused_naming_its_keys(
        self, ops, session
    ) -> None:
        before = sum(1 for _ in session.world.get_all_entities())
        result = call(ops, session, operation="spawn", name="tuning")
        assert not result.ok
        assert "speed" in result.error
        assert sum(1 for _ in session.world.get_all_entities()) == before

    def test_a_component_that_cannot_be_built_refuses_the_whole_spawn(
        self, ops, session, assets
    ) -> None:
        """Half an entity is not what was asked for."""
        (assets / "bad.json").write_text(
            json.dumps({"Transform": {}, "Tag": {"no_such_field": 1}}),
            encoding="utf-8",
        )
        result = call(ops, session, operation="spawn", name=str(assets / "bad.json"))
        assert not result.ok
        assert "Tag" in result.error
        assert session.world.get_entity("bad") is None

    def test_a_file_that_is_not_data_is_refused(self, ops, session) -> None:
        result = call(ops, session, operation="spawn", name="hero.png")
        assert not result.ok
        for suffix in DATA_EXTENSIONS:
            assert suffix in result.error

    def test_plan_mode_describes_and_creates_nothing(self, ops, session) -> None:
        session.set_approval_mode(ApprovalMode.PLAN)
        result = call(ops, session, operation="spawn", name="crate")
        assert result.ok, result.error
        assert result.result["status"] == "planned"
        assert session.world.get_entity("crate") is None


class TestReload:
    """Re-reading a loaded resource."""

    def test_it_picks_up_what_changed_on_disk(self, ops, session, assets) -> None:
        call(ops, session, operation="preview", name="tuning")
        (assets / "tuning.json").write_text(json.dumps({"speed": 9}), encoding="utf-8")

        result = call(ops, session, operation="reload", name="tuning")
        assert result.ok, result.error
        assert result.result["reloaded"] == str(assets / "tuning.json")
        preview = call(ops, session, operation="preview", name="tuning")
        assert preview.result["data"] == {"speed": 9}

    def test_something_not_loaded_is_refused(self, ops, session) -> None:
        result = call(ops, session, operation="reload", name="tuning")
        assert not result.ok
        assert "not loaded" in result.error

    def test_a_file_that_no_longer_parses_is_reported(
        self, ops, session, assets
    ) -> None:
        call(ops, session, operation="preview", name="tuning")
        (assets / "tuning.json").write_text("{", encoding="utf-8")
        result = call(ops, session, operation="reload", name="tuning")
        assert not result.ok
        assert "tuning.json" in result.error


class TestTheOperationItself:
    """The edges of the dispatch."""

    def test_an_unknown_verb_names_the_valid_ones(self, ops, session) -> None:
        result = call(ops, session, operation="delete")
        assert not result.ok
        assert "list, preview, spawn, reload" in result.error

    def test_a_missing_name_is_named(self, ops, session) -> None:
        result = call(ops, session, operation="preview")
        assert not result.ok
        assert "'name'" in result.error

    def test_a_session_without_a_resource_manager_says_so(
        self, ops, populated, core_registry
    ) -> None:
        bare = StudioSession(populated, component_registry=core_registry)
        result = call(ops, bare, operation="list")
        assert not result.ok
        assert "resource_manager" in result.error
