"""The MCP front end over Studio's operation surface.

A thin adapter, and deliberately thin. Every operation, its schema and
its error text already exist in `pyguara.studio.ops`; this module's whole
job is to present them as Model Context Protocol tools and hand the
results back. Nothing here decides what an operation does, validates an
argument, or writes an error message -- if it did, the MCP front end and
the JSON-lines one would start to disagree, and the one that drifts is
always the one nobody is watching.

Built on the SDK's **low-level** `Server` rather than `MCPServer` (what
1.x called `FastMCP`). `MCPServer` derives a tool's schema from a Python
function's type hints, which is the wrong direction here: the schemas are
already written, emitted from the component model, and carry enum members
and field documentation that a hint cannot express. The low-level server
takes an explicit `inputSchema`, which is exactly what there is.

Results go back as JSON text **and** as structured content. A client that
understands structured output gets a real object; one that does not still
gets readable JSON rather than a Python `repr`.

Field names here are the SDK's Python-side ones -- `input_schema`,
`structured_content`, `is_error` -- which pydantic serialises to the
protocol's camelCase on the wire. The camelCase spellings are accepted as
aliases at runtime but are not what the type stubs declare, so using them
type-checks as an error while working perfectly, which is the worst of
both.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pyguara.log import get_logger
from pyguara.studio.agent.journal import Actor
from pyguara.studio.mcp.availability import require_mcp
from pyguara.studio.ops.builtin import default_registry
from pyguara.studio.ops.registry import OperationRegistry
from pyguara.studio.session import StudioSession

if TYPE_CHECKING:
    from mcp.server.lowlevel import Server

logger = get_logger(__name__)

SERVER_NAME = "pyguara-studio"
"""How the server identifies itself to a client."""

INSTRUCTIONS = """\
PyGuara Studio: author a game scene in a running PyGuara engine.

Start with `project_overview` in an unfamiliar project, then
`scene_summary` for the open scene. `component_schema` tells you what a
component's fields are, their types, and an enum field's valid members --
read it before setting a field on a type you have not used.

Entities are named by id, and ids are stable across undo and redo, so an
id from one call still means the same entity in the next.

Every edit returns the diff it produced, so you can check your own work
without a second call. Every edit is undoable through `history`, and
every action -- including the ones that failed -- is in `journal`.

If the session's approval mode is `ask`, your edits are queued rather
than applied and a person approves them; `approvals` shows the queue. If
it is `plan`, edits are described and nothing changes.
"""


def build_server(
    session: StudioSession,
    *,
    registry: OperationRegistry | None = None,
    actor: Actor = Actor.AGENT,
) -> Server[None]:
    """Build an MCP server exposing `session` through `registry`.

    Args:
        session: The session every tool call acts on.
        registry: The operations to expose. Defaults to the built-in set.
        actor: Who tool calls are attributed to in the journal.

    Returns:
        A configured, unstarted server.

    Raises:
        RuntimeError: If the MCP SDK is not installed.
    """
    require_mcp()

    import mcp.types as types
    from mcp.server.context import ServerRequestContext
    from mcp.server.lowlevel import Server

    operations = registry if registry is not None else default_registry()

    async def on_list_tools(
        context: ServerRequestContext[None],
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        """Return every operation as a tool.

        Not paginated: the surface is twenty operations by design, and a
        cursor would be ceremony over a list that fits in one response.

        Args:
            context: The request context, unused.
            params: Pagination parameters, unused.

        Returns:
            The tool list.
        """
        return types.ListToolsResult(
            tools=[
                types.Tool(
                    name=operation.name,
                    description=operation.description,
                    input_schema=operation.parameters,
                )
                for operation in operations
            ]
        )

    async def on_call_tool(
        context: ServerRequestContext[None],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        """Run one operation and return its result.

        `OperationRegistry.invoke` does not raise, so a failed operation
        arrives here as a result rather than an exception. It is reported
        with `isError` set and the message in the text -- the message is
        the agent's recovery path, so it must reach the model rather than
        being swallowed into a transport-level failure.

        Args:
            context: The request context, unused.
            params: The tool name and arguments.

        Returns:
            The tool result.
        """
        outcome = operations.invoke(
            session, params.name, params.arguments or {}, actor=actor
        )
        payload = outcome.to_dict()
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=_as_text(payload))],
            structured_content=payload,
            is_error=not outcome.ok,
        )

    return Server[None](
        SERVER_NAME,
        version=_engine_version(),
        title="PyGuara Studio",
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def serve_stdio(
    session: StudioSession,
    *,
    registry: OperationRegistry | None = None,
    actor: Actor = Actor.AGENT,
    stdin: Any = None,
    stdout: Any = None,
) -> None:
    """Run the MCP server over stdin and stdout until the client leaves.

    The transport an editor or CLI configures a local MCP server with.

    Args:
        session: The session every tool call acts on.
        registry: The operations to expose.
        actor: Who tool calls are attributed to.
        stdin: An `anyio` async file to read from, or None for the
            process's own stdin.
        stdout: An `anyio` async file to write to, or None for the
            process's own stdout. The CLI passes the *real* stdout here
            after pointing `sys.stdout` at stderr, because pygame's import
            banner and the engine's console logger would otherwise write
            prose into the protocol stream.

    Raises:
        RuntimeError: If the MCP SDK is not installed.
    """
    require_mcp()

    from mcp.server.stdio import stdio_server

    server = build_server(session, registry=registry, actor=actor)
    async with stdio_server(stdin, stdout) as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def _as_text(payload: dict[str, Any]) -> str:
    """Render a result as the text a client without structured output sees.

    Indented, because this is read by a model and sometimes by a person
    debugging a session; the few extra tokens buy a great deal of
    legibility over one dense line.

    Args:
        payload: The result to render.

    Returns:
        JSON text. Anything that will not encode falls back to `repr`
        rather than failing the whole call -- a result the model cannot
        read in full beats no result at all.
    """
    try:
        return json.dumps(payload, indent=2)
    except (TypeError, ValueError):  # pragma: no cover - ops encode already
        return repr(payload)


def _engine_version() -> str:
    """Return the installed engine version, for the server handshake.

    Returns:
        The version, or "0" when the package metadata is unavailable --
        which is the case when running from a source checkout that was
        never installed.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("pyguara")
    except PackageNotFoundError:  # pragma: no cover - installed in dev
        return "0"
