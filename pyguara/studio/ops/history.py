"""Operations over the session's record: undo history, journal and approvals."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyguara.studio.ops._args import (
    require,
    schema,
)
from pyguara.studio.ops.registry import Operation, OperationError, RiskClass

if TYPE_CHECKING:
    from pyguara.studio.session import StudioSession


def _history(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Inspect or move the undo history."""
    operation = str(arguments.get("operation", "list"))

    if operation == "list":
        return {
            "undo": list(session.stack.undo_labels),
            "redo": list(session.stack.redo_labels),
        }
    if operation == "undo":
        outcome = session.undo()
        if outcome is None:
            return {"status": "nothing_to_undo"}
        return outcome.to_dict()
    if operation == "redo":
        outcome = session.redo()
        if outcome is None:
            return {"status": "nothing_to_redo"}
        return outcome.to_dict()
    if operation == "undo_to":
        index = arguments.get("index")
        if not isinstance(index, int):
            raise OperationError("'undo_to' needs an integer 'index'.")
        before = session.snapshot()
        reverted = session.stack.undo_to(index)
        session.journal.record(
            session.actor, "undo_to", detail={"index": index, "reverted": reverted}
        )
        from pyguara.studio.model.snapshot import diff_snapshots

        return {
            "reverted": reverted,
            "diff": diff_snapshots(before, session.snapshot()).to_dict(),
        }

    raise OperationError(
        f"Unknown history operation '{operation}'. Valid: list, undo, redo, undo_to."
    )


def _journal(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Read back what has been done this session."""
    if arguments.get("failures_only"):
        entries = session.journal.failures()
    else:
        entries = session.journal.tail(int(arguments.get("count", 20)))
    return {"entries": [entry.to_dict() for entry in entries]}


def _approvals(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """List, approve or reject edits waiting for a person."""
    operation = str(arguments.get("operation", "list"))

    if operation == "list":
        return {
            "approval_mode": session.approval_mode.value,
            "pending": [entry.to_dict() for entry in session.pending],
        }
    if operation == "approve":
        pending_id = str(require(arguments, "pending_id"))
        return session.approve(pending_id).to_dict()
    if operation == "reject":
        pending_id = str(require(arguments, "pending_id"))
        return session.reject(pending_id, str(arguments.get("reason", ""))).to_dict()

    raise OperationError(
        f"Unknown approvals operation '{operation}'. Valid: list, approve, reject."
    )


OPERATIONS: tuple[Operation, ...] = (
    Operation(
        name="history",
        summary="List, undo, redo or rewind the edit history.",
        detail=(
            "operation: 'list' shows the stacks, 'undo'/'redo' move one "
            "step, 'undo_to' takes an 'index' and rewinds to it."
        ),
        risk=RiskClass.EDIT,
        parameters=schema(
            {
                "operation": {
                    "type": "string",
                    "enum": ["list", "undo", "redo", "undo_to"],
                },
                "index": {
                    "type": "integer",
                    "description": "For 'undo_to': how many edits to leave applied.",
                },
            }
        ),
        handler=_history,
    ),
    Operation(
        name="journal",
        summary="Read back the actions taken this session, newest last.",
        detail=(
            "Includes failures, and who asked for each action. The place to "
            "look when something went wrong several edits ago."
        ),
        risk=RiskClass.READ,
        parameters=schema(
            {
                "count": {
                    "type": "integer",
                    "description": "How many recent entries to return.",
                },
                "failures_only": {
                    "type": "boolean",
                    "description": "Return only the actions that failed.",
                },
            }
        ),
        handler=_journal,
    ),
    Operation(
        name="approvals",
        summary="List, approve or reject edits waiting for a person.",
        detail=(
            "Only used when the session's approval mode is 'ask', in which "
            "case every edit is queued with the diff it would make."
        ),
        risk=RiskClass.EDIT,
        parameters=schema(
            {
                "operation": {
                    "type": "string",
                    "enum": ["list", "approve", "reject"],
                },
                "pending_id": {
                    "type": "string",
                    "description": "The handle from the queued edit's result.",
                },
                "reason": {
                    "type": "string",
                    "description": "For 'reject': why, recorded in the journal.",
                },
            }
        ),
        handler=_approvals,
    ),
)
