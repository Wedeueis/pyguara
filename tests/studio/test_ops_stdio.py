"""The JSON-lines transport, and the whole agent loop through it.

This is the dependency-free way in, and deliberately the one the tests
drive: it exercises the same dispatch an agent hits with no protocol
library in between. The engine's hard-won rule is behind that choice --
the first `pyguara/editor` imported PyOpenGL, which was a dependency
nowhere, and never executed once in any install. The operation surface is
the contract; MCP is one transport over it.
"""

from __future__ import annotations

import io
import json

from pyguara.ecs.manager import EntityManager
from pyguara.studio.agent.journal import Actor
from pyguara.studio.ops.registry import OperationRegistry
from pyguara.studio.ops.stdio import handle_line, handle_lines, serve
from pyguara.studio.session import StudioSession


def _run(session: StudioSession, ops: OperationRegistry, *requests: dict) -> list[dict]:
    """Serve a list of requests and return the decoded responses."""
    stdin = io.StringIO("\n".join(json.dumps(request) for request in requests))
    stdout = io.StringIO()
    assert serve(session, stdin=stdin, stdout=stdout, registry=ops) == 0
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


class TestOneLine:
    """Dispatching a single request."""

    def test_a_valid_request_succeeds(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        response = handle_line(session, '{"op": "scene_summary"}', registry=ops)
        assert response is not None
        assert response["ok"] is True
        assert response["result"]["entity_count"] == 5

    def test_arguments_are_passed_through(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        response = handle_line(
            session,
            '{"op": "get_entity", "args": {"entity_id": "root"}}',
            registry=ops,
        )
        assert response is not None
        assert response["result"]["id"] == "root"

    def test_a_blank_line_is_skipped_not_answered(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """So a human typing into the pipe is not punished for pressing
        enter."""
        assert handle_line(session, "   ", registry=ops) is None
        assert handle_line(session, "", registry=ops) is None

    def test_an_id_is_echoed_back(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """So a caller issuing several requests without waiting can match
        responses to them."""
        response = handle_line(
            session, '{"op": "scene_summary", "id": 7}', registry=ops
        )
        assert response is not None
        assert response["id"] == 7

    def test_no_id_means_no_id_key(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        response = handle_line(session, '{"op": "scene_summary"}', registry=ops)
        assert response is not None
        assert "id" not in response

    def test_operation_is_accepted_as_an_alias_for_op(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """`operation` is already an argument name on two operations, so a
        caller conflating the two is a mistake worth absorbing."""
        response = handle_line(session, '{"operation": "scene_summary"}', registry=ops)
        assert response is not None
        assert response["ok"] is True

    def test_arguments_is_accepted_as_an_alias_for_args(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        response = handle_line(
            session,
            '{"op": "get_entity", "arguments": {"entity_id": "root"}}',
            registry=ops,
        )
        assert response is not None
        assert response["ok"] is True


class TestMalformedInput:
    """Every bad line gets an answer that says how to fix it."""

    def test_invalid_json_explains_the_format(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        response = handle_line(session, "{not json", registry=ops)
        assert response is not None
        assert response["ok"] is False
        assert "One JSON object per line" in response["error"]

    def test_a_json_array_is_refused_with_an_example(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        response = handle_line(session, '["scene_summary"]', registry=ops)
        assert response is not None
        assert "Expected a JSON object" in response["error"]
        assert '{"op": "scene_summary"}' in response["error"]

    def test_a_missing_op_points_at_list_operations(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        response = handle_line(session, "{}", registry=ops)
        assert response is not None
        assert "list_operations" in response["error"]

    def test_a_non_string_op_is_refused(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        response = handle_line(session, '{"op": 3}', registry=ops)
        assert response is not None
        assert response["ok"] is False

    def test_non_object_args_are_refused(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        response = handle_line(
            session, '{"op": "get_entity", "args": "root"}', registry=ops
        )
        assert response is not None
        assert '"args" must be an object' in response["error"]
        assert response["operation"] == "get_entity"

    def test_a_malformed_line_does_not_end_the_stream(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """One bad line must not kill a session that should have reported
        it and carried on."""
        stdin = io.StringIO('{bad\n{"op": "scene_summary"}\n')
        stdout = io.StringIO()
        serve(session, stdin=stdin, stdout=stdout, registry=ops)

        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
        assert responses[0]["ok"] is False
        assert responses[1]["ok"] is True


class TestServe:
    """The read loop."""

    def test_one_response_per_request(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        responses = _run(
            session,
            ops,
            {"op": "scene_summary"},
            {"op": "list_components"},
            {"op": "list_operations"},
        )
        assert len(responses) == 3

    def test_blank_lines_produce_no_response(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        stdin = io.StringIO('\n\n{"op": "scene_summary"}\n\n')
        stdout = io.StringIO()
        serve(session, stdin=stdin, stdout=stdout, registry=ops)
        assert len(stdout.getvalue().splitlines()) == 1

    def test_each_response_is_one_line(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """A multi-line response would desynchronise a line-oriented
        reader on the other end."""
        stdin = io.StringIO('{"op": "scene_tree", "include_fields": true}\n')
        stdout = io.StringIO()
        serve(session, stdin=stdin, stdout=stdout, registry=ops)
        assert len(stdout.getvalue().rstrip("\n").splitlines()) == 1

    def test_a_failed_operation_is_not_a_crash(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """Exit code 0: a failed operation is a response, and the caller
        reads its replies."""
        stdin = io.StringIO('{"op": "get_entity", "args": {"entity_id": "x"}}\n')
        stdout = io.StringIO()
        assert serve(session, stdin=stdin, stdout=stdout, registry=ops) == 0

    def test_responses_are_flushed_as_they_are_written(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """Without this a caller waiting on a reply before sending its
        next request deadlocks against a half-full buffer -- which is the
        normal way an agent drives this."""
        flushes: list[int] = []

        class _CountingSink(io.StringIO):
            def flush(self) -> None:
                flushes.append(len(self.getvalue()))
                super().flush()

        stdin = io.StringIO('{"op": "scene_summary"}\n{"op": "list_components"}\n')
        sink = _CountingSink()
        serve(session, stdin=stdin, stdout=sink, registry=ops)
        assert len(flushes) == 2

    def test_handle_lines_yields_one_per_non_blank(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        responses = list(
            handle_lines(
                session,
                ['{"op": "scene_summary"}', "", '{"op": "list_operations"}'],
                registry=ops,
            )
        )
        assert len(responses) == 2


class TestActorAttribution:
    """Who the transport says is calling."""

    def test_the_default_actor_is_the_agent(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """This transport exists for agents; a human edits through the UI."""
        handle_line(
            session,
            '{"op": "set_enabled", "args": {"entity_id": "root", "enabled": false}}',
            registry=ops,
        )
        assert session.journal.entries[-1].actor is Actor.AGENT

    def test_the_actor_can_be_overridden(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """A test harness or a script is not an agent."""
        handle_line(
            session,
            '{"op": "set_enabled", "args": {"entity_id": "root", "enabled": false}}',
            registry=ops,
            actor=Actor.SCRIPT,
        )
        assert session.journal.entries[-1].actor is Actor.SCRIPT


class TestTheWholeAgentLoop:
    """Read, edit, verify, undo -- over the wire, as an agent would."""

    def test_an_edit_and_its_undo_restore_the_scene(
        self, session: StudioSession, ops: OperationRegistry, populated: EntityManager
    ) -> None:
        responses = _run(
            session,
            ops,
            {"op": "scene_summary", "id": 1},
            {
                "op": "set_field",
                "id": 2,
                "args": {
                    "entity_id": "root",
                    "component": "Transform",
                    "field": "position",
                    "value": {"x": 99, "y": 1},
                },
            },
            {"op": "get_entity", "id": 3, "args": {"entity_id": "root"}},
            {"op": "history", "id": 4, "args": {"operation": "undo"}},
            {"op": "get_entity", "id": 5, "args": {"entity_id": "root"}},
        )

        assert all(response["ok"] for response in responses)
        assert [response["id"] for response in responses] == [1, 2, 3, 4, 5]

        moved = responses[2]["result"]["components"]["Transform"]["position"]
        assert moved == {"x": 99.0, "y": 1.0}

        restored = responses[4]["result"]["components"]["Transform"]["position"]
        assert restored == {"x": 10.0, "y": 20.0}

    def test_an_agent_can_discover_the_surface_then_use_it(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """The cold-start path: list the operations, learn a component's
        schema, then edit a field of it."""
        responses = _run(
            session,
            ops,
            {"op": "list_operations"},
            {"op": "component_schema", "args": {"component": "Transform"}},
            {
                "op": "set_field",
                "args": {
                    "entity_id": "root",
                    "component": "Transform",
                    "field": "rotation",
                    "value": 1.25,
                },
            },
        )

        assert all(response["ok"] for response in responses)
        names = {op["name"] for op in responses[0]["result"]["operations"]}
        assert "component_schema" in names
        fields = {field["name"] for field in responses[1]["result"]["schema"]["fields"]}
        assert "rotation" in fields
        assert responses[2]["result"]["diff"]["fields"][0]["after"] == 1.25

    def test_a_mistake_is_recoverable_from_the_error_alone(
        self, session: StudioSession, ops: OperationRegistry, populated: EntityManager
    ) -> None:
        """The property the error messages exist for: an agent that gets a
        name wrong can fix it from the reply without another lookup."""
        wrong, *_ = _run(
            session,
            ops,
            {
                "op": "set_field",
                "args": {
                    "entity_id": "root",
                    "component": "Transfrom",
                    "field": "rotation",
                    "value": 1.0,
                },
            },
        )
        assert wrong["ok"] is False
        assert "Transform" in wrong["error"]

        corrected, *_ = _run(
            session,
            ops,
            {
                "op": "set_field",
                "args": {
                    "entity_id": "root",
                    "component": "Transform",
                    "field": "rotation",
                    "value": 1.0,
                },
            },
        )
        assert corrected["ok"] is True

    def test_failures_are_visible_in_the_journal_afterwards(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        responses = _run(
            session,
            ops,
            {"op": "get_entity", "args": {"entity_id": "nope"}},
            {"op": "journal", "args": {"failures_only": True}},
        )
        entries = responses[1]["result"]["entries"]
        assert any(entry["action"] == "get_entity" for entry in entries)
