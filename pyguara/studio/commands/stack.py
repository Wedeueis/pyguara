"""Undo/redo over `EditCommand`s.

The engine had no command stack of any kind before this; `pyguara/tools`
and the ImGui Inspector both mutate components in place, so nothing was
reversible. Studio routes every edit through here instead.

Bound to one `EntityManager` for its lifetime. A history that spans a
scene switch would be undoing commands into a world that never saw them
applied, so `StudioSession` builds a new stack per scene rather than
carrying one across.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from pyguara.ecs.manager import EntityManager
from pyguara.log import get_logger
from pyguara.studio.commands.base import (
    CompositeCommand,
    EditCommand,
    EditError,
)

logger = get_logger(__name__)

DEFAULT_LIMIT = 256
"""How many undo entries to keep.

Finite because an editing session is long and a command holds the state it
captured -- `DestroyEntity` keeps a whole subtree alive for as long as it
is undoable. Dropping the oldest entry is the standard trade: a developer
who wants to undo 300 edits wants the file they saved, not the stack.
"""


class CommandStack:
    """Applies commands and remembers how to take them back."""

    def __init__(self, world: EntityManager, *, limit: int = DEFAULT_LIMIT) -> None:
        """Create an empty history over `world`.

        Args:
            world: The world every command on this stack acts on.
            limit: How many undo entries to keep before dropping the oldest.

        Raises:
            ValueError: If `limit` is not positive.
        """
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")

        self._world = world
        self._limit = limit
        self._undo: list[EditCommand] = []
        self._redo: list[EditCommand] = []
        self._listeners: list[Callable[[], None]] = []
        # Set while a transaction is open. Commands collect here instead of
        # going onto the undo stack, so the group lands as one entry.
        self._transaction: list[EditCommand] | None = None

    @property
    def world(self) -> EntityManager:
        """The world this stack acts on."""
        return self._world

    @property
    def can_undo(self) -> bool:
        """Whether there is anything to undo."""
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        """Whether there is anything to redo."""
        return bool(self._redo)

    @property
    def undo_labels(self) -> tuple[str, ...]:
        """Labels of the undoable commands, oldest first.

        The history panel's list. Oldest first so the index a user clicks
        is stable as new edits arrive at the end.
        """
        return tuple(command.label for command in self._undo)

    @property
    def redo_labels(self) -> tuple[str, ...]:
        """Labels of the redoable commands, next-to-redo first."""
        return tuple(command.label for command in reversed(self._redo))

    def do(self, command: EditCommand, *, coalesce: bool = False) -> None:
        """Apply `command` and make it undoable.

        A successful call clears the redo stack: the future that was
        redoable is no longer reachable from this state.

        Args:
            command: The change to make.
            coalesce: Offer the command to the previous one to merge with,
                so a continuous gesture is one undo entry. Opt-in because
                merging is only correct for a gesture -- a gizmo drag, a
                held arrow key -- and wrong for two deliberate edits that
                happen to touch the same field.

        Raises:
            EditError: If the command could not be applied. Nothing is
                changed and nothing is pushed.
        """
        command.apply(self._world)

        if self._transaction is not None:
            self._transaction.append(command)
            return

        if coalesce and self._undo:
            merged = command.coalesce_with(self._undo[-1])
            if merged is not None:
                # The merged command stands in for both. Both are already
                # applied to the world, and `merged` describes the combined
                # change, so it takes their place without re-applying.
                self._undo[-1] = merged
                self._redo.clear()
                self._notify()
                return

        self._push(command)
        self._redo.clear()
        self._notify()

    def undo(self) -> EditCommand | None:
        """Revert the most recent command.

        Returns:
            The command that was reverted, or None when the history is
            empty.
        """
        if self._transaction is not None:
            raise EditError(
                "Cannot undo while a transaction is open: the group has not "
                "landed on the stack yet, so there is no entry to take back."
            )
        if not self._undo:
            return None

        command = self._undo.pop()
        command.revert(self._world)
        self._redo.append(command)
        self._notify()
        return command

    def redo(self) -> EditCommand | None:
        """Re-apply the most recently undone command.

        Returns:
            The command that was re-applied, or None when there is nothing
            to redo.
        """
        if self._transaction is not None:
            raise EditError(
                "Cannot redo while a transaction is open: the group's own "
                "commands are still being collected."
            )
        if not self._redo:
            return None

        command = self._redo.pop()
        command.apply(self._world)
        self._undo.append(command)
        self._notify()
        return command

    def undo_to(self, index: int) -> int:
        """Undo until only the first `index` commands remain applied.

        What "undo to here" in the history panel does: clicking the third
        entry of eight reverts five commands in one action, newest first.

        Args:
            index: How many commands to leave applied. 0 reverts everything.

        Returns:
            How many commands were reverted.

        Raises:
            ValueError: If `index` is negative or beyond the history.
        """
        if not 0 <= index <= len(self._undo):
            raise ValueError(
                f"index {index} is outside the history, which holds "
                f"{len(self._undo)} undoable command(s)."
            )

        reverted = 0
        while len(self._undo) > index:
            if self.undo() is None:  # pragma: no cover - guarded by the loop
                break
            reverted += 1
        return reverted

    @contextmanager
    def transaction(self, label: str) -> Iterator[None]:
        """Group every command applied inside the block into one entry.

        What a multi-select edit needs: moving twelve entities is twelve
        commands that must undo together, because undoing a third of a move
        is not a state the user was ever in.

        An exception inside the block reverts whatever did apply and
        re-raises, so the world is left as it was and nothing reaches the
        history. An empty block adds nothing.

        Args:
            label: What the group reads as in the history.

        Yields:
            None.

        Raises:
            EditError: If a transaction is already open -- nesting would
                make the inner block's rollback ambiguous.
            Exception: Anything the block raises, after rollback.
        """
        if self._transaction is not None:
            raise EditError(
                f"A transaction ({label!r}) cannot be opened inside another. "
                f"Build the inner group separately and pass it as a "
                f"CompositeCommand."
            )

        collected: list[EditCommand] = []
        self._transaction = collected
        try:
            yield
        except Exception:
            self._transaction = None
            for command in reversed(collected):
                command.revert(self._world)
            raise
        else:
            self._transaction = None
            if not collected:
                return
            entry: EditCommand = (
                collected[0]
                if len(collected) == 1
                else _AppliedComposite(label, collected)
            )
            self._push(entry)
            self._redo.clear()
            self._notify()

    def clear(self) -> None:
        """Forget the history, leaving the world exactly as it is.

        Not an undo-all: what the world currently holds is kept, and simply
        stops being reversible. What saving a scene calls, so the history
        does not invite undoing past the last saved state.
        """
        if not self._undo and not self._redo:
            return
        self._undo.clear()
        self._redo.clear()
        self._notify()

    def subscribe(self, listener: Callable[[], None]) -> None:
        """Register `listener` to be called whenever the history changes.

        Takes no argument on purpose: a listener reads the stack it
        already holds. The journal and the history panel both use this.

        Args:
            listener: Called after any change to the undo or redo stack.
        """
        self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[], None]) -> None:
        """Remove a previously registered listener.

        Args:
            listener: The callback to drop. Unknown callbacks are ignored.
        """
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _push(self, command: EditCommand) -> None:
        """Add `command` to the undo stack, honouring the limit.

        Args:
            command: An already-applied command.
        """
        self._undo.append(command)
        while len(self._undo) > self._limit:
            dropped = self._undo.pop(0)
            logger.debug(f"Undo history full; dropped '{dropped.label}'.")

    def _notify(self) -> None:
        """Tell every listener the history changed.

        Iterates a copy, so a listener may subscribe or unsubscribe from
        inside the callback.
        """
        for listener in list(self._listeners):
            listener()


class _AppliedComposite(CompositeCommand):
    """A `CompositeCommand` whose members are already applied.

    `CommandStack.transaction` applies each command as it arrives, so that
    a failure is caught at the point it happens rather than at the end of
    the block. By the time the group is built, every member is applied --
    so the group must present itself as applied too, or the stack's first
    `undo()` would refuse it.
    """

    def __init__(self, label: str, commands: list[EditCommand]) -> None:
        """Group already-applied `commands`.

        Args:
            label: What the group reads as in the history.
            commands: The members, in the order they were applied.
        """
        super().__init__(label, commands)
        self._applied = True

    def _apply(self, world: EntityManager) -> None:
        """Re-apply every member, for a redo after this group was undone.

        Args:
            world: The world to change.
        """
        super()._apply(world)
