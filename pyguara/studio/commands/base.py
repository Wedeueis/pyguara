"""The edit command: the one way authored state changes in Studio.

Everything that mutates a scene -- a human dragging a gizmo, a command
palette entry, an agent calling a tool over MCP -- produces one of these
and hands it to a `CommandStack`. That single seam is what makes undo,
a reviewable journal and diffable agent edits the same mechanism rather
than three parallel ones.

**Commands capture their own inverse, at apply time.** They are mementos,
not descriptions: `SetField` records the old value as it writes the new
one, and `DestroyEntity` snapshots the subtree it is about to cascade
through. The alternative -- deriving an inverse from the engine's event
stream -- was considered and rejected when `EventDispatcher._event_history`
was audited: engine events carry no inverse, so nothing in that stream can
say what a value was before it changed.

A consequence of capturing at apply time: a command instance is a record
of one application. `apply()` twice without an intervening `revert()`
raises, because the second call would overwrite the captured inverse with
state the first call already produced, and the undo would restore the
wrong thing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pyguara.ecs.manager import EntityManager


class EditError(Exception):
    """A command cannot be applied, and nothing was changed.

    Raised by `apply()` **before** it mutates anything, so a failed command
    never leaves half an edit behind and is never pushed onto the stack.
    The message is shown to whoever asked for the edit -- a human in a
    toast, an agent as a tool error -- so it names what was wrong and, where
    there is one, the valid alternative.
    """


class EditCommand(ABC):
    """One reversible change to a world.

    Subclasses are small and specific. Each one owns the knowledge of how
    to undo itself, which is the only reason the stack can be generic.
    """

    def __init__(self) -> None:
        """Start un-applied."""
        self._applied = False

    @property
    def applied(self) -> bool:
        """Whether this command is currently applied to a world."""
        return self._applied

    @property
    @abstractmethod
    def label(self) -> str:
        """A short description, shown in the history panel and the journal.

        Phrased as the action taken -- "Move hero", "Add Sprite to tree_03"
        -- because it is what an undo menu entry reads as.
        """
        ...

    @abstractmethod
    def _apply(self, world: EntityManager) -> None:
        """Perform the change, capturing whatever `_revert` will need.

        Args:
            world: The world to change.

        Raises:
            EditError: If the change cannot be made. Must be raised before
                anything is mutated.
        """
        ...

    @abstractmethod
    def _revert(self, world: EntityManager) -> None:
        """Undo the change, using what `_apply` captured.

        Called only after a successful `_apply`, and against the same world.

        Args:
            world: The world to restore.
        """
        ...

    def apply(self, world: EntityManager) -> None:
        """Apply this command to `world`.

        Args:
            world: The world to change.

        Raises:
            EditError: If the change cannot be made, or if this command is
                already applied.
        """
        if self._applied:
            raise EditError(
                f"{type(self).__name__} is already applied. A command captures "
                f"its inverse when it is applied, so applying it twice would "
                f"overwrite that inverse with state the first application "
                f"produced, and the undo would restore the wrong value."
            )
        self._apply(world)
        self._applied = True

    def revert(self, world: EntityManager) -> None:
        """Undo this command against `world`.

        Args:
            world: The world to restore.

        Raises:
            EditError: If this command is not currently applied.
        """
        if not self._applied:
            raise EditError(
                f"{type(self).__name__} is not applied, so there is nothing to revert."
            )
        self._revert(world)
        self._applied = False

    def coalesce_with(self, previous: EditCommand) -> EditCommand | None:
        """Merge this command into `previous`, or decline.

        What keeps a gizmo drag from filling the undo stack with one entry
        per mouse-motion event. A drag issues a `SetField` per frame; the
        stack asks each to fold into the last, so the whole drag undoes in
        one step -- which is what a user means by "undo that move".

        Declining is the default and the safe answer: a merge is only
        correct when the pair describes one continuous gesture on the same
        target.

        Args:
            previous: The command currently on top of the stack.

        Returns:
            A single command replacing both, or None to keep them separate.
        """
        return None

    def describe(self) -> dict[str, Any]:
        """Structured detail for the journal and for an agent's reply.

        The default names the command and its label. Subclasses add the
        fields that identify what they touched, so a reviewer -- or an
        agent checking its own work -- can see what changed without
        re-reading the world.

        Returns:
            A JSON-serializable description.
        """
        return {"command": type(self).__name__, "label": self.label}


class CompositeCommand(EditCommand):
    """Several commands that undo and redo as one entry.

    What a transaction becomes, and what a multi-select edit produces:
    moving twelve selected entities is twelve `SetField`s that must undo
    together, because undoing a third of a move is not a state the user
    was ever in.
    """

    def __init__(self, label: str, commands: list[EditCommand]) -> None:
        """Group `commands` under one label.

        Args:
            label: What the group reads as in the history.
            commands: The members, in the order they should apply.
        """
        super().__init__()
        self._label = label
        self._commands = list(commands)

    @property
    def label(self) -> str:
        """The group's label."""
        return self._label

    @property
    def commands(self) -> tuple[EditCommand, ...]:
        """The grouped commands, in apply order."""
        return tuple(self._commands)

    def _apply(self, world: EntityManager) -> None:
        """Apply each member in order, rolling back on the first failure.

        A partially applied group is not a state anything should observe,
        so the members that did succeed are reverted before the error
        propagates. The group as a whole then counts as never applied.

        Args:
            world: The world to change.

        Raises:
            EditError: From whichever member failed, after rollback.
        """
        done: list[EditCommand] = []
        try:
            for command in self._commands:
                command.apply(world)
                done.append(command)
        except EditError:
            for command in reversed(done):
                command.revert(world)
            raise

    def _revert(self, world: EntityManager) -> None:
        """Revert every member, in reverse order.

        Args:
            world: The world to restore.
        """
        for command in reversed(self._commands):
            command.revert(world)

    def describe(self) -> dict[str, Any]:
        """Describe the group and each member.

        Returns:
            A JSON-serializable description.
        """
        return {
            "command": type(self).__name__,
            "label": self.label,
            "children": [command.describe() for command in self._commands],
        }
