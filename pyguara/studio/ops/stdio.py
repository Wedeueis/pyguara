"""Driving the operation surface over JSON lines on stdin and stdout.

The dependency-free way in. One JSON object per input line, one per
output line:

    {"op": "scene_summary"}
    {"op": "set_field", "args": {"entity_id": "hero", ...}, "id": 3}

Why this exists alongside the MCP adapter, rather than only MCP: the
engine's hard-won rule is that an undeclared dependency is how a whole
subsystem comes to be dead code -- the first `pyguara/editor` imported
PyOpenGL, which was a dependency nowhere, and never executed once in any
install. The operation surface is the contract; MCP is one transport over
it, behind an optional extra. This one needs nothing but the standard
library, so it works in every install, in a shell pipe, and from a test.

It is also the honest testing seam. A test here exercises the same
dispatch an agent hits, with no protocol library in between.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Iterator
from typing import IO, Any

from pyguara.log import get_logger
from pyguara.studio.agent.journal import Actor
from pyguara.studio.ops.builtin import default_registry
from pyguara.studio.ops.registry import OperationRegistry
from pyguara.studio.session import StudioSession

logger = get_logger(__name__)


def handle_line(
    session: StudioSession,
    line: str,
    *,
    registry: OperationRegistry | None = None,
    actor: Actor = Actor.AGENT,
) -> dict[str, Any] | None:
    """Handle one request line and return the response object.

    Args:
        session: The session to act on.
        line: One line of input.
        registry: The operations available. Defaults to the built-in set.
        actor: Who is calling, for the journal.

    Returns:
        The response, or None for a blank line -- which is skipped rather
        than answered, so a human typing into the pipe is not punished for
        pressing enter.
    """
    line = line.strip()
    if not line:
        return None

    registry = registry if registry is not None else default_registry()

    try:
        request = json.loads(line)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "error": f"Not valid JSON: {exc}. One JSON object per line.",
        }

    if not isinstance(request, dict):
        return {
            "ok": False,
            "error": (
                f"Expected a JSON object, got {type(request).__name__}. "
                f'Each line looks like {{"op": "scene_summary"}}.'
            ),
        }

    # `op` with `operation` accepted too: `operation` is already an
    # argument name on two operations, and a caller conflating the two is
    # a mistake worth absorbing rather than rejecting.
    name = request.get("op") or request.get("operation")
    if not isinstance(name, str) or not name:
        return {
            "ok": False,
            "error": (
                'Each request needs a string "op" naming the operation. '
                'Call {"op": "list_operations"} to see them.'
            ),
        }

    arguments = request.get("args", request.get("arguments", {}))
    if not isinstance(arguments, dict):
        return {
            "ok": False,
            "operation": name,
            "error": f'"args" must be an object, got {type(arguments).__name__}.',
        }

    response = registry.invoke(session, name, arguments, actor=actor).to_dict()
    # Echoed back when supplied, so a caller issuing several requests
    # without waiting can match responses to them.
    if "id" in request:
        response["id"] = request["id"]
    return response


def handle_lines(
    session: StudioSession,
    lines: Iterable[str],
    *,
    registry: OperationRegistry | None = None,
    actor: Actor = Actor.AGENT,
) -> Iterator[dict[str, Any]]:
    """Handle each line, yielding one response per non-blank line.

    Args:
        session: The session to act on.
        lines: The request lines.
        registry: The operations available.
        actor: Who is calling.

    Yields:
        One response object per handled line.
    """
    for line in lines:
        response = handle_line(session, line, registry=registry, actor=actor)
        if response is not None:
            yield response


def serve(
    session: StudioSession,
    *,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
    registry: OperationRegistry | None = None,
    actor: Actor = Actor.AGENT,
) -> int:
    """Read requests until end of input, writing a response per request.

    Each response is flushed as it is written. Without that a caller
    waiting on a reply before sending its next request deadlocks against
    a half-full buffer -- which is the normal way an agent drives this.

    Args:
        session: The session to act on.
        stdin: Where to read. Defaults to `sys.stdin`.
        stdout: Where to write. Defaults to `sys.stdout`.
        registry: The operations available.
        actor: Who is calling.

    Returns:
        A process exit code: 0 always, since a failed operation is a
        response rather than a crash. A malformed stream is the caller's
        problem to read in the replies.
    """
    source = stdin if stdin is not None else sys.stdin
    sink = stdout if stdout is not None else sys.stdout

    for line in source:
        response = handle_line(session, line, registry=registry, actor=actor)
        if response is None:
            continue
        sink.write(json.dumps(response) + "\n")
        sink.flush()

    return 0
