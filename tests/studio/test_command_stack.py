"""`CommandStack`: undo, redo, coalescing, transactions and the limit.

The engine had no command stack at all before Studio, so none of this is
regression cover -- it is the contract being established.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Tag, Transform
from pyguara.ecs.manager import EntityManager
from pyguara.studio.commands.base import EditCommand, EditError
from pyguara.studio.commands.entity import (
    AddComponent,
    CreateEntity,
    SetEnabled,
    SetField,
)
from pyguara.studio.commands.stack import CommandStack


def _rotation(world: EntityManager, entity_id: str = "root") -> float:
    """Read an entity's rotation, for terse assertions."""
    entity = world.get_entity(entity_id)
    assert entity is not None
    return entity.get_component(Transform).rotation


class TestBasics:
    """Applying and taking back."""

    def test_starts_empty(self, stack: CommandStack) -> None:
        assert stack.can_undo is False
        assert stack.can_redo is False
        assert stack.undo_labels == ()

    def test_do_applies_and_records(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        stack.do(SetField("root", Transform, "rotation", 1.0))
        assert _rotation(populated) == 1.0
        assert stack.can_undo is True

    def test_undo_reverts(self, stack: CommandStack, populated: EntityManager) -> None:
        stack.do(SetField("root", Transform, "rotation", 1.0))
        stack.undo()
        assert _rotation(populated) == 0.0

    def test_redo_reapplies(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        stack.do(SetField("root", Transform, "rotation", 1.0))
        stack.undo()
        stack.redo()
        assert _rotation(populated) == 1.0

    def test_undo_on_an_empty_stack_returns_none(self, stack: CommandStack) -> None:
        assert stack.undo() is None

    def test_redo_with_nothing_undone_returns_none(self, stack: CommandStack) -> None:
        stack.do(SetEnabled("root", False))
        assert stack.redo() is None

    def test_undo_returns_the_command_it_reverted(self, stack: CommandStack) -> None:
        command = SetEnabled("root", False)
        stack.do(command)
        assert stack.undo() is command

    def test_many_edits_undo_in_reverse_order(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        for value in (1.0, 2.0, 3.0):
            stack.do(SetField("root", Transform, "rotation", value))

        assert _rotation(populated) == 3.0
        stack.undo()
        assert _rotation(populated) == 2.0
        stack.undo()
        assert _rotation(populated) == 1.0
        stack.undo()
        assert _rotation(populated) == 0.0

    def test_labels_are_oldest_first(self, stack: CommandStack) -> None:
        """So the index a user clicks in the history panel stays stable
        as new edits arrive at the end."""
        stack.do(CreateEntity("a"))
        stack.do(CreateEntity("b"))
        assert stack.undo_labels == ("Create a", "Create b")

    def test_redo_labels_are_next_first(self, stack: CommandStack) -> None:
        stack.do(CreateEntity("a"))
        stack.do(CreateEntity("b"))
        stack.undo()
        stack.undo()
        assert stack.redo_labels == ("Create a", "Create b")


class TestFailedCommands:
    """A command that cannot apply must leave no trace."""

    def test_a_failure_propagates(self, stack: CommandStack) -> None:
        with pytest.raises(EditError):
            stack.do(CreateEntity("root"))

    def test_a_failure_is_not_recorded(self, stack: CommandStack) -> None:
        """Otherwise the history offers an undo for a change that never
        happened."""
        with pytest.raises(EditError):
            stack.do(CreateEntity("root"))
        assert stack.can_undo is False

    def test_a_failure_does_not_clear_the_redo_stack(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        """The redo future is still reachable: nothing moved."""
        stack.do(SetField("root", Transform, "rotation", 1.0))
        stack.undo()
        assert stack.can_redo is True

        with pytest.raises(EditError):
            stack.do(CreateEntity("root"))

        assert stack.can_redo is True
        stack.redo()
        assert _rotation(populated) == 1.0


class TestRedoInvalidation:
    """A new edit abandons the redo future."""

    def test_doing_something_new_clears_redo(self, stack: CommandStack) -> None:
        stack.do(SetField("root", Transform, "rotation", 1.0))
        stack.undo()
        assert stack.can_redo is True

        stack.do(SetEnabled("root", False))
        assert stack.can_redo is False


class TestCoalescing:
    """One gesture, one entry."""

    def test_coalesced_writes_make_one_entry(self, stack: CommandStack) -> None:
        for value in (1.0, 2.0, 3.0):
            stack.do(SetField("root", Transform, "rotation", value), coalesce=True)
        assert len(stack.undo_labels) == 1

    def test_one_undo_takes_back_the_whole_gesture(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        """A drag undoes to where it began, not to the previous frame."""
        for value in (1.0, 2.0, 3.0):
            stack.do(SetField("root", Transform, "rotation", value), coalesce=True)
        stack.undo()
        assert _rotation(populated) == 0.0

    def test_a_coalesced_gesture_redoes_to_its_end(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        for value in (1.0, 2.0, 3.0):
            stack.do(SetField("root", Transform, "rotation", value), coalesce=True)
        stack.undo()
        stack.redo()
        assert _rotation(populated) == 3.0

    def test_coalescing_is_off_by_default(self, stack: CommandStack) -> None:
        """Two deliberate edits to the same field are two undo steps."""
        stack.do(SetField("root", Transform, "rotation", 1.0))
        stack.do(SetField("root", Transform, "rotation", 2.0))
        assert len(stack.undo_labels) == 2

    def test_an_unrelated_command_breaks_the_gesture(self, stack: CommandStack) -> None:
        stack.do(SetField("root", Transform, "rotation", 1.0), coalesce=True)
        stack.do(SetEnabled("root", False), coalesce=True)
        stack.do(SetField("root", Transform, "rotation", 2.0), coalesce=True)
        assert len(stack.undo_labels) == 3

    def test_coalescing_onto_an_empty_stack_just_records(
        self, stack: CommandStack
    ) -> None:
        stack.do(SetField("root", Transform, "rotation", 1.0), coalesce=True)
        assert len(stack.undo_labels) == 1


class TestUndoTo:
    """ "Undo to here" in the history panel."""

    def test_reverts_down_to_the_index(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        for value in (1.0, 2.0, 3.0, 4.0):
            stack.do(SetField("root", Transform, "rotation", value))

        reverted = stack.undo_to(1)

        assert reverted == 3
        assert _rotation(populated) == 1.0
        assert len(stack.undo_labels) == 1

    def test_index_zero_reverts_everything(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        for value in (1.0, 2.0):
            stack.do(SetField("root", Transform, "rotation", value))
        stack.undo_to(0)
        assert _rotation(populated) == 0.0
        assert stack.can_undo is False

    def test_the_reverted_commands_are_redoable(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        for value in (1.0, 2.0, 3.0):
            stack.do(SetField("root", Transform, "rotation", value))
        stack.undo_to(1)

        stack.redo()
        stack.redo()
        assert _rotation(populated) == 3.0

    def test_the_current_index_is_a_no_op(self, stack: CommandStack) -> None:
        stack.do(SetEnabled("root", False))
        assert stack.undo_to(1) == 0

    def test_an_out_of_range_index_raises(self, stack: CommandStack) -> None:
        stack.do(SetEnabled("root", False))
        with pytest.raises(ValueError, match="outside the history"):
            stack.undo_to(5)
        with pytest.raises(ValueError, match="outside the history"):
            stack.undo_to(-1)


class TestTransactions:
    """Grouping several edits into one entry."""

    def test_a_transaction_is_one_undo_entry(self, stack: CommandStack) -> None:
        with stack.transaction("Move both"):
            stack.do(SetField("child_a", Transform, "rotation", 1.0))
            stack.do(SetField("child_b", Transform, "rotation", 1.0))

        assert stack.undo_labels == ("Move both",)

    def test_undoing_it_reverts_every_member(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        """Undoing a third of a move is not a state the user was in."""
        with stack.transaction("Move both"):
            stack.do(SetField("child_a", Transform, "rotation", 1.0))
            stack.do(SetField("child_b", Transform, "rotation", 1.0))

        stack.undo()

        assert _rotation(populated, "child_a") == 0.0
        assert _rotation(populated, "child_b") == 0.0

    def test_redoing_it_reapplies_every_member(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        with stack.transaction("Move both"):
            stack.do(SetField("child_a", Transform, "rotation", 1.0))
            stack.do(SetField("child_b", Transform, "rotation", 1.0))

        stack.undo()
        stack.redo()

        assert _rotation(populated, "child_a") == 1.0
        assert _rotation(populated, "child_b") == 1.0

    def test_a_single_command_is_not_wrapped(self, stack: CommandStack) -> None:
        """No point in a group of one; the command's own label is better."""
        with stack.transaction("Group"):
            stack.do(CreateEntity("solo"))
        assert stack.undo_labels == ("Create solo",)

    def test_an_empty_transaction_records_nothing(self, stack: CommandStack) -> None:
        with stack.transaction("Nothing"):
            pass
        assert stack.can_undo is False

    def test_an_exception_rolls_the_whole_group_back(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        with pytest.raises(EditError), stack.transaction("Partly impossible"):
            stack.do(SetField("child_a", Transform, "rotation", 1.0))
            stack.do(AddComponent("root", Tag("Duplicate")))

        assert _rotation(populated, "child_a") == 0.0

    def test_a_failed_transaction_records_nothing(self, stack: CommandStack) -> None:
        with pytest.raises(EditError), stack.transaction("Partly impossible"):
            stack.do(SetField("child_a", Transform, "rotation", 1.0))
            stack.do(AddComponent("root", Tag("Duplicate")))

        assert stack.can_undo is False

    def test_an_arbitrary_exception_also_rolls_back(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        """Not only `EditError` -- a bug in the calling code too."""
        with pytest.raises(ZeroDivisionError), stack.transaction("Buggy caller"):
            stack.do(SetField("child_a", Transform, "rotation", 1.0))
            raise ZeroDivisionError

        assert _rotation(populated, "child_a") == 0.0
        assert stack.can_undo is False

    def test_the_stack_is_usable_after_a_failed_transaction(
        self, stack: CommandStack
    ) -> None:
        """The open-transaction flag must be cleared on the error path."""
        with pytest.raises(ZeroDivisionError), stack.transaction("Buggy caller"):
            raise ZeroDivisionError

        stack.do(CreateEntity("after"))
        assert stack.undo_labels == ("Create after",)

    def test_nesting_is_refused(self, stack: CommandStack) -> None:
        """Nesting would make the inner block's rollback ambiguous.

        Deliberately nested `with`s: that is the thing under test, so it
        cannot be flattened into a single statement.
        """
        with stack.transaction("Outer"):  # noqa: SIM117
            with pytest.raises(EditError, match="cannot be opened inside"):
                with stack.transaction("Inner"):
                    pass

    def test_undo_during_a_transaction_is_refused(self, stack: CommandStack) -> None:
        """The group has not landed yet, so there is no entry to take back."""
        with pytest.raises(EditError, match="Cannot undo"), stack.transaction("Open"):
            stack.do(CreateEntity("a"))
            stack.undo()

    def test_redo_during_a_transaction_is_refused(self, stack: CommandStack) -> None:
        with pytest.raises(EditError, match="Cannot redo"), stack.transaction("Open"):
            stack.redo()


class TestClear:
    """Forgetting the history without changing the world."""

    def test_clear_keeps_the_world(
        self, stack: CommandStack, populated: EntityManager
    ) -> None:
        """Not an undo-all: saving a scene calls this."""
        stack.do(SetField("root", Transform, "rotation", 1.0))
        stack.clear()
        assert _rotation(populated) == 1.0

    def test_clear_empties_both_stacks(self, stack: CommandStack) -> None:
        stack.do(SetField("root", Transform, "rotation", 1.0))
        stack.undo()
        stack.clear()
        assert stack.can_undo is False
        assert stack.can_redo is False


class TestLimit:
    """Bounded history."""

    def test_the_oldest_entry_is_dropped(self, populated: EntityManager) -> None:
        stack = CommandStack(populated, limit=2)
        for value in (1.0, 2.0, 3.0):
            stack.do(SetField("root", Transform, "rotation", value))

        assert len(stack.undo_labels) == 2

    def test_dropping_does_not_revert_anything(self, populated: EntityManager) -> None:
        """The edit stays applied; it just stops being undoable."""
        stack = CommandStack(populated, limit=1)
        for value in (1.0, 2.0):
            stack.do(SetField("root", Transform, "rotation", value))

        assert _rotation(populated) == 2.0
        stack.undo()
        assert _rotation(populated) == 1.0
        assert stack.can_undo is False

    def test_a_non_positive_limit_is_refused(self, populated: EntityManager) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            CommandStack(populated, limit=0)


class TestListeners:
    """Change notification, for the history panel and the journal."""

    def test_do_notifies(self, stack: CommandStack) -> None:
        calls: list[int] = []
        stack.subscribe(lambda: calls.append(1))
        stack.do(CreateEntity("a"))
        assert len(calls) == 1

    def test_undo_and_redo_notify(self, stack: CommandStack) -> None:
        calls: list[int] = []
        stack.do(CreateEntity("a"))
        stack.subscribe(lambda: calls.append(1))
        stack.undo()
        stack.redo()
        assert len(calls) == 2

    def test_a_transaction_notifies_once(self, stack: CommandStack) -> None:
        """One entry landed, so one notification."""
        calls: list[int] = []
        stack.subscribe(lambda: calls.append(1))
        with stack.transaction("Group"):
            stack.do(CreateEntity("a"))
            stack.do(CreateEntity("b"))
        assert len(calls) == 1

    def test_a_failed_command_does_not_notify(self, stack: CommandStack) -> None:
        calls: list[int] = []
        stack.subscribe(lambda: calls.append(1))
        with pytest.raises(EditError):
            stack.do(CreateEntity("root"))
        assert calls == []

    def test_clearing_an_empty_history_is_silent(self, stack: CommandStack) -> None:
        calls: list[int] = []
        stack.subscribe(lambda: calls.append(1))
        stack.clear()
        assert calls == []

    def test_unsubscribe_stops_notifications(self, stack: CommandStack) -> None:
        calls: list[int] = []

        def listener() -> None:
            calls.append(1)

        stack.subscribe(listener)
        stack.unsubscribe(listener)
        stack.do(CreateEntity("a"))
        assert calls == []

    def test_a_listener_may_unsubscribe_from_inside_the_callback(
        self, stack: CommandStack
    ) -> None:
        calls: list[int] = []

        def once() -> None:
            calls.append(1)
            stack.unsubscribe(once)

        stack.subscribe(once)
        stack.do(CreateEntity("a"))
        stack.do(CreateEntity("b"))
        assert len(calls) == 1


class TestWorldBinding:
    """A stack belongs to one world."""

    def test_the_world_is_exposed(self, populated: EntityManager) -> None:
        """So a command built elsewhere can be checked against it."""
        stack = CommandStack(populated)
        assert stack.world is populated


class TestCustomCommands:
    """The stack is generic over `EditCommand`."""

    def test_a_hand_written_command_works(self, populated: EntityManager) -> None:
        """Nothing about the stack knows the concrete command set."""
        log: list[str] = []

        class Noisy(EditCommand):
            @property
            def label(self) -> str:
                return "Noisy"

            def _apply(self, world: EntityManager) -> None:
                log.append("apply")

            def _revert(self, world: EntityManager) -> None:
                log.append("revert")

        stack = CommandStack(populated)
        stack.do(Noisy())
        stack.undo()
        stack.redo()

        assert log == ["apply", "revert", "apply"]
