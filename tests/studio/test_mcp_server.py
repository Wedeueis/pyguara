"""The MCP front end, driven by a real MCP client over memory streams.

Not mocked. The whole risk this module carries is protocol-shaped -- a
field named `inputSchema` where the SDK wants `input_schema`, a result
whose error never reaches the model -- and a fake client would reproduce
whatever misunderstanding the implementation already has.

The adapter is deliberately thin: schemas, validation and error text all
live in `pyguara.studio.ops`. So these tests check the *adaptation*, and
leave the behaviour of each operation to `test_ops.py`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

pytest.importorskip("mcp")

import anyio  # noqa: E402
from mcp import ClientSession  # noqa: E402
from mcp.shared.memory import create_client_server_memory_streams  # noqa: E402

from pyguara.common.components import Transform  # noqa: E402
from pyguara.ecs.manager import EntityManager  # noqa: E402
from pyguara.studio.agent.journal import Actor  # noqa: E402
from pyguara.studio.mcp.server import (  # noqa: E402
    INSTRUCTIONS,
    SERVER_NAME,
    build_server,
)
from pyguara.studio.ops.registry import OperationRegistry  # noqa: E402
from pyguara.studio.session import ApprovalMode, StudioSession  # noqa: E402


@asynccontextmanager
async def _client(
    session: StudioSession,
    *,
    registry: OperationRegistry | None = None,
    actor: Actor = Actor.AGENT,
) -> AsyncIterator[ClientSession]:
    """Run the server and yield an initialised client talking to it."""
    server = build_server(session, registry=registry, actor=actor)
    async with (
        create_client_server_memory_streams() as (
            (client_read, client_write),
            (server_read, server_write),
        ),
        anyio.create_task_group() as task_group,
    ):
        task_group.start_soon(
            lambda: server.run(
                server_read,
                server_write,
                server.create_initialization_options(),
                raise_exceptions=True,
            )
        )
        async with ClientSession(client_read, client_write) as client:
            await client.initialize()
            yield client
        task_group.cancel_scope.cancel()


def _run(coroutine: Any) -> Any:
    """Run an async test body on anyio's default backend."""
    return anyio.run(coroutine)


class TestHandshake:
    """What a client learns before it calls anything."""

    def test_the_server_names_itself(self, session: StudioSession) -> None:
        async def body() -> None:
            async with _client(session) as client:
                result = await client.initialize()
                assert result.server_info.name == SERVER_NAME

        _run(body)

    def test_the_instructions_tell_an_agent_where_to_start(
        self, session: StudioSession
    ) -> None:
        """A cold-start agent reads these before any tool call, so they
        name the entry points rather than describing the architecture."""
        assert "project_overview" in INSTRUCTIONS
        assert "scene_summary" in INSTRUCTIONS
        assert "component_schema" in INSTRUCTIONS

    def test_the_instructions_explain_the_approval_modes(self) -> None:
        """Otherwise an agent whose edits come back `pending` has no idea
        why nothing changed."""
        assert "ask" in INSTRUCTIONS
        assert "plan" in INSTRUCTIONS

    def test_the_instructions_reach_the_client(self, session: StudioSession) -> None:
        async def body() -> None:
            async with _client(session) as client:
                result = await client.initialize()
                assert result.instructions is not None
                assert "PyGuara Studio" in result.instructions

        _run(body)


class TestToolListing:
    """Every operation, presented as a tool."""

    def test_every_operation_is_listed(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        async def body() -> None:
            async with _client(session, registry=ops) as client:
                listed = await client.list_tools()
                assert {tool.name for tool in listed.tools} == set(ops.names())

        _run(body)

    def test_a_schema_survives_the_crossing(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """The field is `input_schema` in Python and `inputSchema` on the
        wire. Getting that backwards type-checks as an error while
        working, or works while type-checking cleanly and sending the
        wrong key -- so it is asserted on the client's side of the wire."""

        async def body() -> None:
            async with _client(session, registry=ops) as client:
                listed = await client.list_tools()
                tool = next(t for t in listed.tools if t.name == "set_field")
                assert set(tool.input_schema["properties"]) == {
                    "entity_id",
                    "component",
                    "field",
                    "value",
                    "coalesce",
                }

        _run(body)

    def test_additional_properties_false_survives(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """A client validating arguments against the schema is the first
        line of defence against a typo'd argument name."""

        async def body() -> None:
            async with _client(session, registry=ops) as client:
                listed = await client.list_tools()
                for tool in listed.tools:
                    assert tool.input_schema["additionalProperties"] is False

        _run(body)

    def test_the_risk_class_is_in_the_description(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        async def body() -> None:
            async with _client(session, registry=ops) as client:
                listed = await client.list_tools()
                tool = next(t for t in listed.tools if t.name == "set_field")
                assert tool.description is not None
                assert "Risk: edit" in tool.description

        _run(body)

    def test_required_arguments_survive(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        async def body() -> None:
            async with _client(session, registry=ops) as client:
                listed = await client.list_tools()
                tool = next(t for t in listed.tools if t.name == "get_entity")
                assert tool.input_schema["required"] == ["entity_id"]

        _run(body)


class TestCallingTools:
    """Results, in both forms."""

    def test_a_read_returns_structured_content(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        async def body() -> None:
            async with _client(session, registry=ops) as client:
                result = await client.call_tool("scene_summary", {})
                assert result.is_error is False
                assert result.structured_content is not None
                assert result.structured_content["result"]["entity_count"] == 5

        _run(body)

    def test_the_text_form_is_readable_json(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """A client without structured output still gets something a
        model can read, rather than a Python repr."""

        async def body() -> None:
            async with _client(session, registry=ops) as client:
                result = await client.call_tool("scene_summary", {})
                decoded = json.loads(result.content[0].text)
                assert decoded["ok"] is True

        _run(body)

    def test_an_edit_applies_and_returns_its_diff(
        self, session: StudioSession, ops: OperationRegistry, populated: EntityManager
    ) -> None:
        async def body() -> None:
            async with _client(session, registry=ops) as client:
                result = await client.call_tool(
                    "set_field",
                    {
                        "entity_id": "root",
                        "component": "Transform",
                        "field": "rotation",
                        "value": 1.5,
                    },
                )
                assert result.is_error is False
                assert result.structured_content is not None
                change = result.structured_content["result"]["diff"]["fields"][0]
                assert change["after"] == 1.5

            entity = populated.get_entity("root")
            assert entity is not None
            assert entity.get_component(Transform).rotation == 1.5

        _run(body)

    def test_tool_calls_are_attributed_to_the_agent(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        async def body() -> None:
            async with _client(session, registry=ops) as client:
                await client.call_tool(
                    "set_enabled", {"entity_id": "root", "enabled": False}
                )
            assert session.journal.entries[-1].actor is Actor.AGENT

        _run(body)

    def test_the_actor_can_be_overridden(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        async def body() -> None:
            async with _client(session, registry=ops, actor=Actor.SCRIPT) as client:
                await client.call_tool(
                    "set_enabled", {"entity_id": "root", "enabled": False}
                )
            assert session.journal.entries[-1].actor is Actor.SCRIPT

        _run(body)


class TestErrorsReachTheModel:
    """The error text is the agent's recovery path, so it has to arrive."""

    def test_a_failure_is_flagged_as_an_error(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        async def body() -> None:
            async with _client(session, registry=ops) as client:
                result = await client.call_tool("get_entity", {"entity_id": "nope"})
                assert result.is_error is True

        _run(body)

    def test_the_suggestion_survives_the_crossing(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """Reported as a tool result rather than a transport failure,
        precisely so the model can read it and correct itself."""

        async def body() -> None:
            async with _client(session, registry=ops) as client:
                result = await client.call_tool(
                    "set_field",
                    {
                        "entity_id": "root",
                        "component": "Transfrom",
                        "field": "rotation",
                        "value": 1.0,
                    },
                )
                assert result.structured_content is not None
                error = result.structured_content["error"]
                assert "Did you mean 'Transform'" in error
                assert "Did you mean 'Transform'" in result.content[0].text

        _run(body)

    def test_an_unknown_tool_is_a_result_not_a_crash(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """One bad call must not end the session."""

        async def body() -> None:
            async with _client(session, registry=ops) as client:
                result = await client.call_tool("no_such_tool", {})
                assert result.is_error is True

                # And the session is still usable afterwards.
                good = await client.call_tool("scene_summary", {})
                assert good.is_error is False

        _run(body)


class TestApprovalModesOverMcp:
    """The session's rules apply to a tool call like any other edit."""

    def test_plan_mode_changes_nothing(
        self, populated: EntityManager, core_registry, ops: OperationRegistry
    ) -> None:
        planning = StudioSession(
            populated,
            component_registry=core_registry,
            approval_mode=ApprovalMode.PLAN,
        )

        async def body() -> None:
            async with _client(planning, registry=ops) as client:
                result = await client.call_tool(
                    "destroy_entity", {"entity_id": "child_b"}
                )
                assert result.structured_content is not None
                payload = result.structured_content["result"]
                assert payload["status"] == "planned"
                assert payload["diff"]["removed"] == ["child_b", "grandchild"]

            assert populated.get_entity("child_b") is not None

        _run(body)

    def test_ask_mode_queues_the_edit(
        self, populated: EntityManager, core_registry, ops: OperationRegistry
    ) -> None:
        asking = StudioSession(
            populated,
            component_registry=core_registry,
            approval_mode=ApprovalMode.ASK,
        )

        async def body() -> None:
            async with _client(asking, registry=ops) as client:
                result = await client.call_tool(
                    "set_enabled", {"entity_id": "root", "enabled": False}
                )
                assert result.structured_content is not None
                assert result.structured_content["result"]["status"] == "pending"

            assert populated.is_entity_enabled("root") is True
            assert len(asking.pending) == 1

        _run(body)


class TestTheWholeLoopOverMcp:
    """Read, edit, verify, undo -- through the protocol."""

    def test_an_edit_and_its_undo_restore_the_scene(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        async def body() -> None:
            async with _client(session, registry=ops) as client:
                before = await client.call_tool("get_entity", {"entity_id": "root"})
                assert before.structured_content is not None
                original = before.structured_content["result"]["components"][
                    "Transform"
                ]["position"]

                await client.call_tool(
                    "set_field",
                    {
                        "entity_id": "root",
                        "component": "Transform",
                        "field": "position",
                        "value": {"x": 99, "y": 1},
                    },
                )
                await client.call_tool("history", {"operation": "undo"})

                after = await client.call_tool("get_entity", {"entity_id": "root"})
                assert after.structured_content is not None
                restored = after.structured_content["result"]["components"][
                    "Transform"
                ]["position"]
                assert restored == original

        _run(body)

    def test_an_agent_can_discover_a_schema_then_use_it(
        self, session: StudioSession, ops: OperationRegistry
    ) -> None:
        """The cold-start path over the protocol."""

        async def body() -> None:
            async with _client(session, registry=ops) as client:
                schema = await client.call_tool(
                    "component_schema", {"component": "Tag"}
                )
                assert schema.structured_content is not None
                fields = schema.structured_content["result"]["schema"]["fields"]
                field_name = fields[0]["name"]

                applied = await client.call_tool(
                    "set_field",
                    {
                        "entity_id": "root",
                        "component": "Tag",
                        "field": field_name,
                        "value": "Renamed",
                    },
                )
                assert applied.is_error is False

        _run(body)
