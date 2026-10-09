"""One editing session: a world, its history, its journal, its rules.

Everything that edits a scene goes through a `StudioSession`, which is
what makes a human's drag and an agent's tool call indistinguishable to
the layers underneath. The session owns the four things an edit needs:

- the `EntityManager` being edited,
- the `CommandStack` that can take any edit back,
- the `Journal` that records who asked for what,
- and the **approval mode**, which decides whether an edit applies at
  once, waits for a person, or is only described.

The approval modes mirror the permission model coding agents already have,
because the problem is the same one: a capable agent acting on a shared
artefact needs a setting between "ask me about everything" and "do what
you like". `PLAN` is the interesting one, and it is free here -- an edit
is applied, its diff captured, and then reverted. The world ends exactly
as it started and the caller gets the precise consequence rather than a
prediction of it. That only works because every command carries its own
inverse.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pyguara.ecs.manager import EntityManager
from pyguara.log import get_logger
from pyguara.prefabs.registry import ComponentRegistry, get_component_registry
from pyguara.studio.agent.journal import Actor, Journal
from pyguara.studio.commands.base import EditCommand, EditError
from pyguara.studio.commands.stack import CommandStack
from pyguara.studio.model.snapshot import (
    SceneDiff,
    SceneSnapshot,
    diff_snapshots,
    snapshot_scene,
)

logger = get_logger(__name__)


class ApprovalMode(str, Enum):
    """How an edit requested by an actor is handled.

    A `str` enum so it crosses a JSON boundary without an encoder hook --
    the mode is part of an agent's reply, so it has to.
    """

    AUTO = "auto"
    """Apply it. The default for a human at the keyboard."""

    ASK = "ask"
    """Hold it for a person to approve or reject.

    What to run an unfamiliar agent under: every edit becomes a queued
    `PendingEdit` carrying the diff it *would* produce, so the reviewer
    sees the consequence rather than the request.
    """

    PLAN = "plan"
    """Describe it and change nothing.

    Implemented by applying the edit, capturing the diff and reverting, so
    the description is the real consequence and not a guess at it.
    """


@dataclass(frozen=True)
class PendingEdit:
    """An edit waiting for a person's decision.

    Attributes:
        pending_id: Its handle, for `approve()` and `reject()`.
        actor: Who asked.
        label: The command's label.
        description: The command's `describe()`.
        diff: What applying it would change.
        command: The command itself, already reverted and ready to re-apply.
    """

    pending_id: str
    actor: Actor
    label: str
    description: dict[str, Any]
    diff: SceneDiff
    command: EditCommand

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form.

        Returns:
            The pending edit as a plain dict.
        """
        return {
            "pending_id": self.pending_id,
            "actor": self.actor.value,
            "label": self.label,
            "description": self.description,
            "diff": self.diff.to_dict(),
        }


@dataclass(frozen=True)
class EditOutcome:
    """What happened when an edit was requested.

    Attributes:
        status: `applied`, `pending`, `planned` or `rejected`.
        label: The command's label.
        description: The command's `describe()`.
        diff: What changed -- or, for `pending` and `planned`, what would.
        pending_id: Set when the edit is queued for approval.
    """

    status: str
    label: str
    description: dict[str, Any] = field(default_factory=dict)
    diff: SceneDiff = field(default_factory=SceneDiff)
    pending_id: str | None = None

    @property
    def applied(self) -> bool:
        """Whether the world actually changed."""
        return self.status == "applied"

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form.

        Returns:
            The outcome as a plain dict.
        """
        data: dict[str, Any] = {
            "status": self.status,
            "label": self.label,
            "description": self.description,
            "diff": self.diff.to_dict(),
        }
        if self.pending_id is not None:
            data["pending_id"] = self.pending_id
        return data


class StudioSession:
    """A world being edited, with its history, journal and rules."""

    def __init__(
        self,
        world: EntityManager,
        *,
        scene_name: str | None = None,
        project_root: Path | None = None,
        component_registry: ComponentRegistry | None = None,
        journal: Journal | None = None,
        approval_mode: ApprovalMode = ApprovalMode.AUTO,
    ) -> None:
        """Open a session over `world`.

        Args:
            world: The world to edit. A session is bound to one: an undo
                history that spanned a scene switch would be reverting
                commands into a world that never saw them applied.
            scene_name: The scene's name, for snapshots and the journal.
            project_root: The project directory, for operations that read
                or write files.
            component_registry: Resolves component names. Defaults to the
                global registry, which is the one `create_application()`
                puts in the container.
            journal: Where to record actions. Defaults to an in-memory
                journal.
            approval_mode: How edits are handled.
        """
        self._world = world
        self._scene_name = scene_name
        self._project_root = project_root
        self._registry = (
            component_registry
            if component_registry is not None
            else get_component_registry()
        )
        self._journal = journal if journal is not None else Journal()
        self._stack = CommandStack(world)
        self._approval_mode = approval_mode
        self._pending: dict[str, PendingEdit] = {}
        # Who the session attributes an edit to when a caller does not say.
        # Set for the duration of one operation by `acting_as`, so a
        # handler does not have to thread the actor through every call --
        # and, more to the point, cannot forget to. Handlers that
        # hardcoded `Actor.AGENT` recorded a script's edits as an agent's,
        # which makes the provenance the field exists for a fiction.
        self._actor = Actor.HUMAN

        self._journal.record(
            Actor.SYSTEM,
            "session_open",
            detail={
                "scene": scene_name,
                "project_root": str(project_root) if project_root else None,
                "approval_mode": approval_mode.value,
            },
        )

    @property
    def world(self) -> EntityManager:
        """The world being edited."""
        return self._world

    @property
    def scene_name(self) -> str | None:
        """The edited scene's name, when known."""
        return self._scene_name

    @property
    def project_root(self) -> Path | None:
        """The project directory, when the session was given one."""
        return self._project_root

    @property
    def registry(self) -> ComponentRegistry:
        """The component registry that resolves names to classes."""
        return self._registry

    @property
    def stack(self) -> CommandStack:
        """The undo history."""
        return self._stack

    @property
    def journal(self) -> Journal:
        """The action record."""
        return self._journal

    @property
    def approval_mode(self) -> ApprovalMode:
        """How edits are currently handled."""
        return self._approval_mode

    @property
    def actor(self) -> Actor:
        """Who edits are attributed to when a caller does not say."""
        return self._actor

    @contextmanager
    def acting_as(self, actor: Actor) -> Iterator[None]:
        """Attribute edits made inside the block to `actor`.

        What a transport wraps one operation in. Restores the previous
        actor on the way out, including on an exception, so a failed
        agent call cannot leave the session attributing a person's next
        edit to the agent.

        Args:
            actor: Who to attribute to.

        Yields:
            None.
        """
        previous = self._actor
        self._actor = actor
        try:
            yield
        finally:
            self._actor = previous

    def set_approval_mode(self, mode: ApprovalMode) -> None:
        """Change how edits are handled.

        Queued edits are left queued: switching to `AUTO` is a statement
        about future edits, not a blanket approval of the ones a person
        has not looked at yet. Approving those is a separate, deliberate
        act.

        Args:
            mode: The new mode.
        """
        if mode is self._approval_mode:
            return
        previous = self._approval_mode
        self._approval_mode = mode
        self._journal.record(
            Actor.SYSTEM,
            "approval_mode",
            detail={"from": previous.value, "to": mode.value},
        )

    # ----------------------------------------------------------------
    # Editing
    # ----------------------------------------------------------------

    def apply(
        self,
        command: EditCommand,
        *,
        actor: Actor | None = None,
        action: str | None = None,
        coalesce: bool = False,
    ) -> EditOutcome:
        """Request `command`, honouring the approval mode.

        Args:
            command: The edit to make.
            actor: Who is asking. Defaults to the session's current actor,
                which a transport sets with `acting_as` -- so a handler
                cannot misattribute an edit by forgetting to pass this.
            action: The operation name to journal this under. Defaults to
                the command's class name.
            coalesce: Offer the command to the previous one to merge with,
                so a continuous gesture is one undo entry.

        Returns:
            What happened, including the diff.

        Raises:
            EditError: If the command could not be applied. The failure is
                journaled before it propagates -- a failed agent call is
                exactly what a reviewer wants to see.
        """
        action = action or type(command).__name__
        actor = actor if actor is not None else self._actor

        if self._approval_mode is ApprovalMode.PLAN:
            return self._plan(command, actor=actor, action=action)
        if self._approval_mode is ApprovalMode.ASK:
            return self._queue(command, actor=actor, action=action)
        return self._commit(command, actor=actor, action=action, coalesce=coalesce)

    def _commit(
        self,
        command: EditCommand,
        *,
        actor: Actor,
        action: str,
        coalesce: bool = False,
    ) -> EditOutcome:
        """Apply `command` for real, journaling the result either way.

        Args:
            command: The edit to make.
            actor: Who is asking.
            action: The operation name to journal under.
            coalesce: Merge into the previous command where possible.

        Returns:
            The outcome.

        Raises:
            EditError: If the command could not be applied.
        """
        before = self.snapshot()
        try:
            self._stack.do(command, coalesce=coalesce)
        except EditError as exc:
            self._journal.record(actor, action, ok=False, error=str(exc))
            raise

        description = command.describe()
        self._journal.record(actor, action, detail=description)
        return EditOutcome(
            status="applied",
            label=command.label,
            description=description,
            diff=diff_snapshots(before, self.snapshot()),
        )

    def _plan(self, command: EditCommand, *, actor: Actor, action: str) -> EditOutcome:
        """Report what `command` would do, and change nothing.

        Applied and reverted rather than predicted. The diff is then the
        real consequence, which is only possible because every command
        carries its own inverse. The cost is that anything watching
        component changes sees the edit and its undo go past -- physics
        bodies and the spatial index are rebuilt twice and end where they
        started.

        Args:
            command: The edit to describe.
            actor: Who is asking.
            action: The operation name to journal under.

        Returns:
            The outcome, with `status` of "planned".

        Raises:
            EditError: If the command could not be applied, which is worth
                knowing in plan mode too -- an edit that cannot be made is
                the most useful thing a plan can report.
        """
        before = self.snapshot()
        try:
            command.apply(self._world)
        except EditError as exc:
            self._journal.record(actor, action, ok=False, error=str(exc))
            raise

        description = command.describe()
        diff = diff_snapshots(before, self.snapshot())
        command.revert(self._world)

        self._journal.record(actor, action, detail={"planned": True, **description})
        return EditOutcome(
            status="planned",
            label=command.label,
            description=description,
            diff=diff,
        )

    def _queue(self, command: EditCommand, *, actor: Actor, action: str) -> EditOutcome:
        """Hold `command` for a person, carrying the diff it would make.

        The diff is obtained the same way `_plan` does, so a reviewer sees
        the consequence rather than the request. The command is left
        reverted and re-applied on approval.

        Args:
            command: The edit to queue.
            actor: Who is asking.
            action: The operation name to journal under.

        Returns:
            The outcome, with `status` of "pending" and a `pending_id`.

        Raises:
            EditError: If the command could not be applied. An edit that
                cannot be made is not worth a person's attention.
        """
        before = self.snapshot()
        try:
            command.apply(self._world)
        except EditError as exc:
            self._journal.record(actor, action, ok=False, error=str(exc))
            raise

        description = command.describe()
        diff = diff_snapshots(before, self.snapshot())
        command.revert(self._world)

        pending_id = uuid.uuid4().hex[:12]
        self._pending[pending_id] = PendingEdit(
            pending_id=pending_id,
            actor=actor,
            label=command.label,
            description=description,
            diff=diff,
            command=command,
        )
        self._journal.record(
            actor,
            action,
            detail={"pending_id": pending_id, **description},
        )
        return EditOutcome(
            status="pending",
            label=command.label,
            description=description,
            diff=diff,
            pending_id=pending_id,
        )

    # ----------------------------------------------------------------
    # Approval
    # ----------------------------------------------------------------

    @property
    def pending(self) -> tuple[PendingEdit, ...]:
        """Edits waiting for a decision, oldest first."""
        return tuple(self._pending.values())

    def approve(self, pending_id: str) -> EditOutcome:
        """Apply a queued edit.

        Args:
            pending_id: The handle from the `EditOutcome` that queued it.

        Returns:
            The outcome, now applied.

        Raises:
            EditError: If there is no such pending edit, or it no longer
                applies -- the world may have moved since it was queued,
                and an edit that was reviewed against a different state
                must fail rather than land on a surprise.
        """
        entry = self._pending.pop(pending_id, None)
        if entry is None:
            raise EditError(
                f"No pending edit '{pending_id}'. It may have been approved, "
                f"rejected, or belong to an earlier session."
            )

        outcome = self._commit(entry.command, actor=entry.actor, action="approve")
        return EditOutcome(
            status="applied",
            label=outcome.label,
            description=outcome.description,
            diff=outcome.diff,
            pending_id=pending_id,
        )

    def reject(self, pending_id: str, reason: str = "") -> EditOutcome:
        """Discard a queued edit.

        Args:
            pending_id: The handle from the `EditOutcome` that queued it.
            reason: Why, recorded in the journal so an agent reading it
                back can learn what not to propose again.

        Returns:
            The outcome, with `status` of "rejected".

        Raises:
            EditError: If there is no such pending edit.
        """
        entry = self._pending.pop(pending_id, None)
        if entry is None:
            raise EditError(f"No pending edit '{pending_id}'.")

        self._journal.record(
            Actor.HUMAN,
            "reject",
            detail={
                "pending_id": pending_id,
                "label": entry.label,
                "reason": reason,
            },
        )
        return EditOutcome(
            status="rejected",
            label=entry.label,
            description=entry.description,
            pending_id=pending_id,
        )

    # ----------------------------------------------------------------
    # History
    # ----------------------------------------------------------------

    def undo(self, *, actor: Actor | None = None) -> EditOutcome | None:
        """Revert the most recent edit.

        Args:
            actor: Who is asking. Defaults to the session's current actor.

        Returns:
            The outcome, or None when the history is empty.
        """
        actor = actor if actor is not None else self._actor
        before = self.snapshot()
        command = self._stack.undo()
        if command is None:
            return None

        self._journal.record(actor, "undo", detail={"label": command.label})
        return EditOutcome(
            status="applied",
            label=f"Undo {command.label}",
            description=command.describe(),
            diff=diff_snapshots(before, self.snapshot()),
        )

    def redo(self, *, actor: Actor | None = None) -> EditOutcome | None:
        """Re-apply the most recently undone edit.

        Args:
            actor: Who is asking. Defaults to the session's current actor.

        Returns:
            The outcome, or None when there is nothing to redo.
        """
        actor = actor if actor is not None else self._actor
        before = self.snapshot()
        command = self._stack.redo()
        if command is None:
            return None

        self._journal.record(actor, "redo", detail={"label": command.label})
        return EditOutcome(
            status="applied",
            label=f"Redo {command.label}",
            description=command.describe(),
            diff=diff_snapshots(before, self.snapshot()),
        )

    # ----------------------------------------------------------------
    # Reading
    # ----------------------------------------------------------------

    def snapshot(self, *, include_components: bool = True) -> SceneSnapshot:
        """Read the world as it is now.

        Args:
            include_components: Read component field values too.

        Returns:
            The snapshot.
        """
        return snapshot_scene(
            self._world,
            scene_name=self._scene_name,
            include_components=include_components,
        )

    def measure(self, change: Callable[[], None]) -> SceneDiff:
        """Run `change` and report what it did to the world.

        For edits that do not go through a command -- a scene load, a
        system running a frame -- where the question is still "what moved?".

        Args:
            change: The thing to do.

        Returns:
            The difference the call made.
        """
        before = self.snapshot()
        change()
        return diff_snapshots(before, self.snapshot())
