"""The operation surface: one registry, three front ends.

A human picking an entry from the command palette, an agent calling a tool
over MCP, and a script piping JSON into `pyguara studio ops` all reach the
same `Operation` objects. That is the point. Three parallel surfaces
would drift, and the one that drifts is always the one the agent uses,
because nobody is looking at it.

Each operation declares its name, a one-line summary, a JSON Schema for
its arguments and a **risk class**. The risk class is what lets a caller
decide policy without knowing the operation: "read anything, ask before
writing to disk" is expressible without enumerating operations.

**The surface is kept small on purpose.** Mature editor integrations
converge on roughly twenty top-level tools, because a client has a limit
on how many it will present and an agent's accuracy falls as the list
grows. Rarer work goes behind one operation with an `operation`
parameter rather than ten more entries.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from pyguara.log import get_logger
from pyguara.studio.agent.journal import Actor
from pyguara.studio.commands.base import EditError

if TYPE_CHECKING:
    from pyguara.studio.session import StudioSession

logger = get_logger(__name__)


class RiskClass(str, Enum):
    """What kind of consequence an operation has.

    A `str` enum so it crosses a JSON boundary unaided; it appears in
    every tool description an agent reads.
    """

    READ = "read"
    """Reads state and changes nothing. Always safe to call."""

    EDIT = "edit"
    """Changes the scene. Undoable, journaled, and subject to the
    session's approval mode."""

    RUN = "run"
    """Runs the game loop. Changes the scene as the game would, which is
    *not* undoable -- a frame of physics is not an `EditCommand`."""

    WRITE_DISK = "write_disk"
    """Writes a file. Outside the undo stack entirely; the file system is
    not a world this session owns."""


class OperationError(Exception):
    """An operation could not be carried out.

    Carries a message meant for whoever asked -- a human in a toast, an
    agent as a tool error -- so it names what was wrong and, where there
    is one, the valid alternative. An agent's next call is usually a
    correction derived from this text, which is why it is worth writing
    properly.
    """


@dataclass(frozen=True)
class Operation:
    """One callable operation.

    Attributes:
        name: Its identifier, in `snake_case`. Also the MCP tool name.
        summary: One line, shown in the palette and as the tool
            description.
        risk: What kind of consequence it has.
        parameters: JSON Schema for its arguments.
        handler: Does the work. Receives the session and the validated
            arguments, and returns a JSON-serializable result.
        detail: Longer guidance appended to the tool description. Where to
            put the thing an agent gets wrong on its first attempt.
    """

    name: str
    summary: str
    risk: RiskClass
    parameters: dict[str, Any]
    handler: Callable[[StudioSession, dict[str, Any]], Any]
    detail: str | None = None

    @property
    def description(self) -> str:
        """The full text an agent reads, risk class included.

        The risk is in the prose and not only in a field because the field
        is easy for a client to drop, and "this writes a file" belongs
        where it will actually be read.
        """
        parts = [self.summary, f"Risk: {self.risk.value}."]
        if self.detail:
            parts.insert(1, self.detail)
        return " ".join(parts)

    def to_tool_definition(self) -> dict[str, Any]:
        """Return the MCP-shaped tool definition.

        Returns:
            A dict with `name`, `description` and `inputSchema`, which is
            what the Model Context Protocol calls a tool.
        """
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.parameters,
        }


@dataclass(frozen=True)
class OperationResult:
    """What an operation returned.

    Attributes:
        name: The operation called.
        ok: Whether it succeeded.
        result: Its return value, when it succeeded.
        error: Why it failed, when it did.
    """

    name: str
    ok: bool
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form.

        Returns:
            The result as a plain dict. `ok` is always present, so a
            caller never has to infer success from the shape.
        """
        if self.ok:
            return {"ok": True, "operation": self.name, "result": self.result}
        return {"ok": False, "operation": self.name, "error": self.error}


@dataclass
class OperationRegistry:
    """Every operation Studio offers, by name."""

    _operations: dict[str, Operation] = field(default_factory=dict)

    def register(self, operation: Operation) -> None:
        """Add an operation.

        Args:
            operation: The operation to add.

        Raises:
            ValueError: If the name is taken. Unlike `ComponentRegistry`,
                which warns and overwrites, a duplicate here is refused:
                the registry is built once at import time from a fixed
                set, so a collision is a programming error rather than a
                game legitimately replacing an engine default.
        """
        if operation.name in self._operations:
            raise ValueError(
                f"An operation named '{operation.name}' is already registered."
            )
        self._operations[operation.name] = operation

    def get(self, name: str) -> Operation | None:
        """Look an operation up.

        Args:
            name: The operation name.

        Returns:
            The operation, or None.
        """
        return self._operations.get(name)

    def require(self, name: str) -> Operation:
        """Look an operation up, or raise naming the near misses.

        Args:
            name: The operation name.

        Returns:
            The operation.

        Raises:
            OperationError: If there is no such operation. Names that
                share a prefix or a word with the request are suggested,
                because a wrong name is almost always a near miss and an
                agent can correct itself from the suggestion without
                another round trip to list everything.
        """
        operation = self._operations.get(name)
        if operation is not None:
            return operation

        suggestions = self._similar(name)
        if suggestions:
            raise OperationError(
                f"No operation '{name}'. Did you mean {', '.join(suggestions)}?"
            )
        raise OperationError(
            f"No operation '{name}'. Call 'list_operations' for the full set."
        )

    def names(self) -> tuple[str, ...]:
        """Every registered name, sorted."""
        return tuple(sorted(self._operations))

    def __len__(self) -> int:
        """How many operations are registered.

        Returns:
            The count.
        """
        return len(self._operations)

    def __iter__(self) -> Iterator[Operation]:
        """Iterate the operations in name order.

        Returns:
            An iterator over the operations.
        """
        return iter(self._operations[name] for name in self.names())

    def by_risk(self, risk: RiskClass) -> tuple[Operation, ...]:
        """Every operation of a given risk class, in name order.

        Args:
            risk: The class to filter by.

        Returns:
            The matching operations.
        """
        return tuple(operation for operation in self if operation.risk is risk)

    def tool_definitions(self) -> list[dict[str, Any]]:
        """Return every operation as an MCP tool definition.

        Returns:
            Tool definitions in name order, so a client's tool list is
            stable between runs.
        """
        return [operation.to_tool_definition() for operation in self]

    def invoke(
        self,
        session: StudioSession,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        actor: Actor = Actor.AGENT,
    ) -> OperationResult:
        """Call an operation and wrap whatever happens.

        Exceptions are turned into a failed `OperationResult` rather than
        propagating. A caller here is a protocol boundary -- an MCP server
        or a JSON-lines loop -- and a traceback crossing it kills a
        session that should have reported one bad call and carried on. The
        failure is journaled, so an agent's mistakes are in the record
        next to its successes.

        Args:
            session: The session to act on.
            name: The operation to call.
            arguments: Its arguments.
            actor: Who is calling, for the journal.

        Returns:
            The result, successful or not.
        """
        arguments = dict(arguments or {})

        try:
            operation = self.require(name)
        except OperationError as exc:
            session.journal.record(actor, name, ok=False, error=str(exc))
            return OperationResult(name=name, ok=False, error=str(exc))

        try:
            _reject_unknown_arguments(operation, arguments)
            # So every edit the handler makes is attributed to the caller,
            # rather than to whatever each handler happened to hardcode.
            with session.acting_as(actor):
                result = operation.handler(session, arguments)
        except (OperationError, EditError, ValueError, KeyError, TypeError) as exc:
            message = str(exc)
            # An operation's own handler journals its successes with the
            # detail it has; failures are journaled here so that no handler
            # can forget to.
            session.journal.record(actor, name, ok=False, error=message)
            return OperationResult(name=name, ok=False, error=message)
        except Exception as exc:  # pragma: no cover - a bug in a handler
            logger.exception(exc, f"Operation '{name}' raised unexpectedly")
            message = f"{type(exc).__name__}: {exc}"
            session.journal.record(actor, name, ok=False, error=message)
            return OperationResult(name=name, ok=False, error=message)

        return OperationResult(name=name, ok=True, result=result)

    def _similar(self, name: str) -> list[str]:
        """Return registered names close to `name`.

        Args:
            name: The name that did not resolve.

        Returns:
            Up to three candidates, sorted.
        """
        lowered = name.lower()
        words = set(lowered.replace("-", "_").split("_"))
        scored: list[tuple[int, str]] = []
        for candidate in self.names():
            candidate_words = set(candidate.split("_"))
            shared = len(words & candidate_words)
            if shared or candidate.startswith(lowered[:4]):
                scored.append((-shared, candidate))
        scored.sort()
        return [candidate for _, candidate in scored[:3]]


def _reject_unknown_arguments(operation: Operation, arguments: dict[str, Any]) -> None:
    """Refuse an argument the operation does not declare.

    A typo'd argument name is otherwise silently ignored, and the caller
    sees an operation that reported success and did not do what was asked
    -- the single most confusing failure for an agent, because the reply
    says it worked.

    Only applied when the schema forbids extra properties, which every
    operation here does; a schema that allows them is taken at its word.

    Args:
        operation: The operation being called.
        arguments: The supplied arguments.

    Raises:
        OperationError: If an argument is not in the schema, naming the
            ones that are.
    """
    schema = operation.parameters
    if schema.get("additionalProperties", True):
        return

    declared = set(schema.get("properties", {}))
    unknown = sorted(set(arguments) - declared)
    if not unknown:
        return

    raise OperationError(
        f"'{operation.name}' has no argument(s) {unknown}. "
        f"Valid arguments: {sorted(declared) or 'none'}."
    )
