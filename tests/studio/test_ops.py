"""The operation surface, as an agent actually hits it.

Two things get the most cover, because they are what makes the surface
usable by a machine rather than merely callable:

- **The surface stays small and self-describing.** A client has a limit on
  how many tools it will present, and an agent's accuracy falls as the
  list grows.
- **Every error names the alternative.** "No entity 'playr'" is a dead
  end; "Did you mean 'player'?" is a correction. The error text *is* the
  recovery path, so it is asserted like any other output.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Tag, Transform
from pyguara.ecs.manager import EntityManager
from pyguara.studio.agent.journal import Actor
from pyguara.studio.ops.registry import (
    Operation,
    OperationError,
    OperationRegistry,
    RiskClass,
)
from pyguara.studio.session import ApprovalMode, StudioSession


def _call(
    ops: OperationRegistry,
    session: StudioSession,
    name: str,
    **arguments: object,
) -> object:
    """Invoke an operation and return its result, asserting it succeeded."""
    outcome = ops.invoke(session, name, dict(arguments))
    assert outcome.ok, outcome.error
    return outcome.result


def _error(
    ops: OperationRegistry,
    session: StudioSession,
    name: str,
    **arguments: object,
) -> str:
    """Invoke an operation and return its error, asserting it failed."""
    outcome = ops.invoke(session, name, dict(arguments))
    assert not outcome.ok, f"expected a failure, got {outcome.result!r}"
    assert outcome.error is not None
    return outcome.error


class TestTheSurface:
    """Shape and self-description."""

    def test_stays_around_twenty_operations(self, ops: OperationRegistry) -> None:
        """A guard rail, not a law. If this fails because the surface grew
        past about two dozen, the fix is usually to fold the new work
        behind an existing operation's `operation` argument rather than to
        raise the number."""
        assert 10 <= len(ops) <= 24

    def test_every_operation_has_a_summary_and_a_risk(
        self, ops: OperationRegistry
    ) -> None:
        for operation in ops:
            assert operation.summary, operation.name
            assert isinstance(operation.risk, RiskClass), operation.name

    def test_every_operation_names_itself_in_snake_case(
        self, ops: OperationRegistry
    ) -> None:
        for operation in ops:
            assert operation.name.islower(), operation.name
            assert " " not in operation.name, operation.name

    def test_every_schema_refuses_unknown_arguments(
        self, ops: OperationRegistry
    ) -> None:
        """A typo'd argument name silently ignored is the most confusing
        failure an agent can get, because the reply says it worked."""
        for operation in ops:
            assert operation.parameters.get("additionalProperties") is False, (
                operation.name
            )

    def test_every_description_states_the_risk(self, ops: OperationRegistry) -> None:
        """In the prose, not only in a field: a field is easy for a client
        to drop, and "this writes a file" belongs where it is read."""
        for operation in ops:
            assert operation.risk.value in operation.description

    def test_tool_definitions_are_mcp_shaped(self, ops: OperationRegistry) -> None:
        for definition in ops.tool_definitions():
            assert set(definition) == {"name", "description", "inputSchema"}
            assert definition["inputSchema"]["type"] == "object"

    def test_tool_definitions_are_in_a_stable_order(
        self, ops: OperationRegistry
    ) -> None:
        """So a client's tool list does not churn between runs."""
        names = [definition["name"] for definition in ops.tool_definitions()]
        assert names == sorted(names)

    def test_list_operations_describes_the_whole_surface(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(ops, session, "list_operations")
        assert len(result["operations"]) == len(ops)

    def test_read_operations_are_separable_by_risk(
        self, ops: OperationRegistry
    ) -> None:
        """What lets a caller express "read anything, ask before writing"
        without enumerating operations."""
        reads = {operation.name for operation in ops.by_risk(RiskClass.READ)}
        assert "scene_tree" in reads
        assert "set_field" not in reads


class TestReadingTheScene:
    """The read operations."""

    def test_scene_summary_is_counts_only(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(ops, session, "scene_summary")
        assert result["entity_count"] == 5
        assert "entities" not in result

    def test_scene_tree_omits_field_values_by_default(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        """Large on a real scene, and most questions do not need them."""
        result = _call(ops, session, "scene_tree")
        root = next(e for e in result["entities"] if e["id"] == "root")
        assert root["components"]["Transform"] == {}

    def test_scene_tree_includes_fields_on_request(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(ops, session, "scene_tree", include_fields=True)
        root = next(e for e in result["entities"] if e["id"] == "root")
        assert root["components"]["Transform"]["position"] == {
            "x": 10.0,
            "y": 20.0,
        }

    def test_get_entity_returns_one_entity_in_full(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(ops, session, "get_entity", entity_id="child_b")
        assert result["tags"] == ["enemy", "spawned"]
        assert result["parent"] == "root"

    def test_find_entities_by_tag(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(ops, session, "find_entities", tag="enemy")
        assert result["entity_ids"] == ["child_b"]

    def test_find_entities_by_component(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(ops, session, "find_entities", component="Tag")
        assert result["entity_ids"] == ["root"]

    def test_find_entities_by_id_substring(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(ops, session, "find_entities", id_contains="child")
        # "grandchild" matches too: it is a substring test, not a prefix
        # one, which is what makes it useful on ids like "enemy_spawn_03".
        assert result["entity_ids"] == ["child_a", "child_b", "grandchild"]

    def test_find_entities_combines_filters(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(
            ops, session, "find_entities", tag="enemy", component="Transform"
        )
        assert result["entity_ids"] == ["child_b"]

    def test_find_entities_with_no_filter_is_refused(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        """Listing everything is what `scene_tree` is for."""
        assert "at least one" in _error(ops, session, "find_entities")

    def test_find_entities_validates_the_component_name(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        """A misspelled name must not read as "no entity has this", which
        sends an agent looking for the wrong problem."""
        assert "Did you mean 'Transform'" in _error(
            ops, session, "find_entities", component="Transfrom"
        )


class TestSchemaOperations:
    """Learning what can be set, before trying to set it."""

    def test_list_components_is_names_only_by_default(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(ops, session, "list_components")
        assert "Transform" in result["components"]
        assert isinstance(result["components"], list)

    def test_list_components_can_include_schemas(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(ops, session, "list_components", with_schemas=True)
        assert result["components"]["Tag"]["fields"][0]["name"] == "name"

    def test_component_schema_carries_the_json_schema(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(ops, session, "component_schema", component="Tag")
        assert result["json_schema"]["type"] == "object"
        assert result["schema"]["name"] == "Tag"

    def test_component_schema_suggests_a_near_miss(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        assert "Did you mean 'Transform'" in _error(
            ops, session, "component_schema", component="Transfrom"
        )


class TestEditing:
    """The edit operations, and the diffs they return."""

    def test_create_entity_applies(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        result = _call(
            ops,
            session,
            "create_entity",
            entity_id="mob",
            components={"Transform": {"position": {"x": 5, "y": 5}}},
            tags=["enemy"],
            parent_id="root",
        )

        assert result["status"] == "applied"
        entity = populated.get_entity("mob")
        assert entity is not None
        assert entity.get_component(Transform).position.x == 5
        assert populated.parent_of("mob") == "root"

    def test_create_entity_refuses_a_taken_id(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        assert "already exists" in _error(
            ops, session, "create_entity", entity_id="root"
        )

    def test_create_entity_reports_a_bad_component_field(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        """Routed through `ComponentRegistry.create`, whose own error
        already enumerates the valid field names."""
        message = _error(
            ops,
            session,
            "create_entity",
            entity_id="mob",
            components={"Tag": {"nmae": "x"}},
        )
        assert "valid fields" in message

    def test_destroy_entity_reports_the_cascade(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(ops, session, "destroy_entity", entity_id="child_b")
        assert result["diff"]["removed"] == ["child_b", "grandchild"]

    def test_add_component_applies(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        _call(
            ops,
            session,
            "add_component",
            entity_id="child_a",
            component="Tag",
            fields={"name": "Named"},
        )
        entity = populated.get_entity("child_a")
        assert entity is not None
        assert entity.get_component(Tag).name == "Named"

    def test_add_component_uses_defaults_for_omitted_fields(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        _call(ops, session, "add_component", entity_id="child_a", component="Tag")
        entity = populated.get_entity("child_a")
        assert entity is not None
        assert entity.get_component(Tag).name == "Entity"

    def test_add_component_refuses_a_duplicate_type(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        assert "already has a Tag" in _error(
            ops, session, "add_component", entity_id="root", component="Tag"
        )

    def test_remove_component_applies(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        _call(ops, session, "remove_component", entity_id="root", component="Tag")
        entity = populated.get_entity("root")
        assert entity is not None
        assert not entity.has_component(Tag)

    def test_set_field_applies(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        _call(
            ops,
            session,
            "set_field",
            entity_id="root",
            component="Transform",
            field="position",
            value={"x": 99, "y": 1},
        )
        entity = populated.get_entity("root")
        assert entity is not None
        assert entity.get_component(Transform).position.x == 99

    def test_set_field_returns_both_values(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(
            ops,
            session,
            "set_field",
            entity_id="root",
            component="Transform",
            field="rotation",
            value=1.5,
        )
        change = result["diff"]["fields"][0]
        assert change["before"] == 0.0
        assert change["after"] == 1.5

    def test_set_field_accepts_an_enum_member_name(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        from pyguara.physics.components import RigidBody
        from pyguara.physics.types import BodyType

        populated.get_entity("root").add_component(RigidBody())
        _call(
            ops,
            session,
            "set_field",
            entity_id="root",
            component="RigidBody",
            field="body_type",
            value="STATIC",
        )
        entity = populated.get_entity("root")
        assert entity is not None
        assert entity.get_component(RigidBody).body_type is BodyType.STATIC

    def test_set_parent_applies(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        _call(ops, session, "set_parent", entity_id="child_a", parent_id="child_b")
        assert populated.parent_of("child_a") == "child_b"

    def test_set_parent_detaches_with_null(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        _call(ops, session, "set_parent", entity_id="child_a", parent_id=None)
        assert populated.parent_of("child_a") is None

    def test_set_parent_refuses_a_cycle(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        assert _error(
            ops, session, "set_parent", entity_id="root", parent_id="grandchild"
        )

    def test_set_enabled_applies(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        _call(ops, session, "set_enabled", entity_id="root", enabled=False)
        assert populated.is_entity_enabled("root") is False

    def test_set_enabled_refuses_a_non_boolean(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        assert "true or false" in _error(
            ops, session, "set_enabled", entity_id="root", enabled="yes"
        )

    def test_set_tags_replaces_the_set(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        _call(ops, session, "set_tags", entity_id="child_b", tags=["boss"])
        entity = populated.get_entity("child_b")
        assert entity is not None
        assert entity.tags == {"boss"}

    def test_set_tags_refuses_a_non_list(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        assert "list of strings" in _error(
            ops, session, "set_tags", entity_id="root", tags="boss"
        )


class TestErrorsCarryTheCorrection:
    """The error text is the agent's recovery path."""

    def test_a_near_miss_entity_id_is_suggested(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        populated.create_entity("player").add_component(Transform())
        assert "Did you mean 'player'" in _error(
            ops, session, "get_entity", entity_id="playr"
        )

    def test_an_unrecognisable_entity_id_points_at_scene_tree(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        message = _error(ops, session, "get_entity", entity_id="zzzzzz")
        assert "scene_tree" in message

    def test_a_near_miss_component_name_is_suggested(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        assert "Did you mean 'Transform'" in _error(
            ops,
            session,
            "set_field",
            entity_id="root",
            component="Transfrom",
            field="rotation",
            value=1,
        )

    def test_a_near_miss_field_name_is_suggested(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        assert "Did you mean 'rotation'" in _error(
            ops,
            session,
            "set_field",
            entity_id="root",
            component="Transform",
            field="rotatoin",
            value=1,
        )

    def test_an_unrecognisable_field_lists_the_stateful_ones(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        """Derived fields are left out of the suggestion:
        `previous_position` is settable but is rewritten every fixed tick,
        so an agent nudged towards it would watch its edit vanish."""
        message = _error(
            ops,
            session,
            "set_field",
            entity_id="root",
            component="Transform",
            field="zzzzzzzz",
            value=1,
        )
        assert "position" in message
        assert "previous_position" not in message

    def test_a_bad_enum_value_lists_the_members(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        from pyguara.physics.components import RigidBody

        populated.get_entity("root").add_component(RigidBody())
        message = _error(
            ops,
            session,
            "set_field",
            entity_id="root",
            component="RigidBody",
            field="body_type",
            value="FLOATY",
        )
        assert "DYNAMIC" in message and "STATIC" in message

    def test_a_non_editable_field_says_why(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        from pyguara.graphics.components.sprite import Sprite
        from tests.test_scene_serializer import FakeTexture

        populated.get_entity("root").add_component(Sprite(texture=FakeTexture("x.png")))
        message = _error(
            ops,
            session,
            "set_field",
            entity_id="root",
            component="Sprite",
            field="texture",
            value="other.png",
        )
        assert "no JSON form" in message

    def test_a_read_only_field_says_so(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        message = _error(
            ops,
            session,
            "set_field",
            entity_id="root",
            component="Transform",
            field="world_scale",
            value={"x": 2, "y": 2},
        )
        assert "read-only" in message

    def test_a_typo_in_an_argument_name_is_an_error(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        """Rather than a silently ignored key and a success that did
        nothing."""
        message = _error(ops, session, "get_entity", entty_id="root")
        assert "has no argument(s) ['entty_id']" in message
        assert "entity_id" in message

    def test_a_missing_required_argument_names_it(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        assert "Missing required argument 'entity_id'" in _error(
            ops, session, "get_entity"
        )

    def test_an_unknown_operation_suggests_a_near_miss(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        assert "scene_tree" in _error(ops, session, "scene_tre")

    def test_an_unrecognisable_operation_points_at_the_list(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        assert "list_operations" in _error(ops, session, "zzzzzzzzzz")


class TestInvokeNeverRaises:
    """A protocol boundary must not let a traceback through."""

    def test_a_failing_operation_returns_a_result(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        outcome = ops.invoke(session, "get_entity", {"entity_id": "nope"})
        assert outcome.ok is False
        assert outcome.error

    def test_a_handler_that_raises_unexpectedly_is_contained(
        self, session: StudioSession
    ) -> None:
        """A bug in one operation must not kill a session that should
        have reported one bad call and carried on."""

        def explode(session: StudioSession, arguments: dict) -> object:
            raise RuntimeError("handler bug")

        registry = OperationRegistry()
        registry.register(
            Operation(
                name="explode",
                summary="Raise.",
                risk=RiskClass.READ,
                parameters={"type": "object", "additionalProperties": False},
                handler=explode,
            )
        )

        outcome = registry.invoke(session, "explode")
        assert outcome.ok is False
        assert "handler bug" in (outcome.error or "")

    def test_every_failure_is_journaled(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        """So an agent's mistakes sit in the record next to its
        successes, and no handler can forget to log one."""
        ops.invoke(session, "get_entity", {"entity_id": "nope"})
        assert session.journal.failures()


class TestHistoryOperation:
    """One operation covering four verbs, to keep the surface small."""

    def test_list_reports_both_stacks(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        _call(
            ops,
            session,
            "set_field",
            entity_id="root",
            component="Transform",
            field="rotation",
            value=1.0,
        )
        result = _call(ops, session, "history", operation="list")
        assert result["undo"] == ["Set Transform.rotation on root"]
        assert result["redo"] == []

    def test_undo_reverts(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        _call(
            ops,
            session,
            "set_field",
            entity_id="root",
            component="Transform",
            field="rotation",
            value=1.0,
        )
        _call(ops, session, "history", operation="undo")

        entity = populated.get_entity("root")
        assert entity is not None
        assert entity.get_component(Transform).rotation == 0.0

    def test_undo_with_nothing_to_undo_says_so(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        result = _call(ops, session, "history", operation="undo")
        assert result["status"] == "nothing_to_undo"

    def test_redo_reapplies(
        self, ops: OperationRegistry, session: StudioSession, populated: EntityManager
    ) -> None:
        _call(
            ops,
            session,
            "set_field",
            entity_id="root",
            component="Transform",
            field="rotation",
            value=1.0,
        )
        _call(ops, session, "history", operation="undo")
        _call(ops, session, "history", operation="redo")

        entity = populated.get_entity("root")
        assert entity is not None
        assert entity.get_component(Transform).rotation == 1.0

    def test_undo_to_rewinds_several(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        for value in (1.0, 2.0, 3.0):
            _call(
                ops,
                session,
                "set_field",
                entity_id="root",
                component="Transform",
                field="rotation",
                value=value,
            )
        result = _call(ops, session, "history", operation="undo_to", index=1)
        assert result["reverted"] == 2

    def test_undo_to_needs_an_index(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        assert "integer 'index'" in _error(ops, session, "history", operation="undo_to")

    def test_an_unknown_sub_operation_lists_the_valid_ones(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        message = _error(ops, session, "history", operation="rewind")
        assert "list, undo, redo, undo_to" in message


class TestJournalOperation:
    """Reading back what has been done."""

    def test_returns_recent_entries(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        _call(ops, session, "set_enabled", entity_id="root", enabled=False)
        result = _call(ops, session, "journal")
        actions = [entry["action"] for entry in result["entries"]]
        assert "set_enabled" in actions

    def test_failures_only_filters(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        """The first thing worth looking at when a run went wrong."""
        ops.invoke(session, "get_entity", {"entity_id": "nope"})
        _call(ops, session, "set_enabled", entity_id="root", enabled=False)

        result = _call(ops, session, "journal", failures_only=True)
        assert all(not entry["ok"] for entry in result["entries"])
        assert result["entries"]

    def test_the_actor_is_recorded(
        self, ops: OperationRegistry, session: StudioSession
    ) -> None:
        """Telling an agent's edits apart from a human's afterwards."""
        ops.invoke(
            session,
            "set_enabled",
            {"entity_id": "root", "enabled": False},
            actor=Actor.AGENT,
        )
        result = _call(ops, session, "journal")
        assert result["entries"][-1]["actor"] == "agent"


class TestApprovalsOperation:
    """Driving the approval queue from the agent side."""

    @pytest.fixture
    def asking(self, populated: EntityManager, core_registry) -> StudioSession:
        return StudioSession(
            populated,
            component_registry=core_registry,
            approval_mode=ApprovalMode.ASK,
        )

    def test_an_edit_comes_back_pending(
        self, ops: OperationRegistry, asking: StudioSession
    ) -> None:
        result = _call(ops, asking, "set_enabled", entity_id="root", enabled=False)
        assert result["status"] == "pending"
        assert result["pending_id"]

    def test_list_shows_the_queue_and_the_mode(
        self, ops: OperationRegistry, asking: StudioSession
    ) -> None:
        _call(ops, asking, "set_enabled", entity_id="root", enabled=False)
        result = _call(ops, asking, "approvals", operation="list")
        assert result["approval_mode"] == "ask"
        assert len(result["pending"]) == 1

    def test_approving_applies_it(
        self, ops: OperationRegistry, asking: StudioSession, populated: EntityManager
    ) -> None:
        queued = _call(ops, asking, "set_enabled", entity_id="root", enabled=False)
        _call(
            ops,
            asking,
            "approvals",
            operation="approve",
            pending_id=queued["pending_id"],
        )
        assert populated.is_entity_enabled("root") is False

    def test_rejecting_discards_it(
        self, ops: OperationRegistry, asking: StudioSession, populated: EntityManager
    ) -> None:
        queued = _call(ops, asking, "set_enabled", entity_id="root", enabled=False)
        _call(
            ops,
            asking,
            "approvals",
            operation="reject",
            pending_id=queued["pending_id"],
            reason="not yet",
        )
        assert populated.is_entity_enabled("root") is True

    def test_an_unknown_sub_operation_lists_the_valid_ones(
        self, ops: OperationRegistry, asking: StudioSession
    ) -> None:
        assert "list, approve, reject" in _error(
            ops, asking, "approvals", operation="bless"
        )


class TestPlanModeThroughOps:
    """Plan mode is visible from the agent side."""

    @pytest.fixture
    def planning(self, populated: EntityManager, core_registry) -> StudioSession:
        return StudioSession(
            populated,
            component_registry=core_registry,
            approval_mode=ApprovalMode.PLAN,
        )

    def test_an_edit_reports_planned_and_changes_nothing(
        self, ops: OperationRegistry, planning: StudioSession, populated: EntityManager
    ) -> None:
        result = _call(
            ops,
            planning,
            "set_field",
            entity_id="root",
            component="Transform",
            field="rotation",
            value=1.0,
        )
        assert result["status"] == "planned"

        entity = populated.get_entity("root")
        assert entity is not None
        assert entity.get_component(Transform).rotation == 0.0

    def test_the_plan_carries_the_real_diff(
        self, ops: OperationRegistry, planning: StudioSession
    ) -> None:
        result = _call(ops, planning, "destroy_entity", entity_id="child_b")
        assert result["diff"]["removed"] == ["child_b", "grandchild"]


class TestRegistryMechanics:
    """The registry itself."""

    def test_a_duplicate_name_is_refused(self) -> None:
        """A collision here is a programming error, not a game replacing
        an engine default -- the surface is built once from a fixed set."""
        registry = OperationRegistry()
        operation = Operation(
            name="thing",
            summary="A thing.",
            risk=RiskClass.READ,
            parameters={"type": "object"},
            handler=lambda session, arguments: None,
        )
        registry.register(operation)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(operation)

    def test_require_raises_for_an_unknown_name(self) -> None:
        with pytest.raises(OperationError):
            OperationRegistry().require("nothing")

    def test_build_registry_returns_an_isolated_instance(self) -> None:
        from pyguara.studio.ops.builtin import build_registry, default_registry

        first = build_registry()
        assert first is not build_registry()
        assert first is not default_registry()

    def test_default_registry_is_shared(self) -> None:
        from pyguara.studio.ops.builtin import default_registry

        assert default_registry() is default_registry()
