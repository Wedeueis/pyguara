"""`StudioSession`: the approval modes, the history and the journal.

The interesting behaviour is `PLAN`, which reports what an edit *would* do
by applying it, capturing the diff and reverting. That is only sound
because every command carries its own inverse, and these tests are what
hold it to being sound -- a plan that leaves the world changed is worse
than no plan at all.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Tag, Transform
from pyguara.ecs.manager import EntityManager
from pyguara.studio.agent.journal import Actor
from pyguara.studio.commands.base import EditError
from pyguara.studio.commands.entity import (
    AddComponent,
    CreateEntity,
    SetEnabled,
    SetField,
)
from pyguara.studio.model.snapshot import diff_snapshots
from pyguara.studio.session import ApprovalMode, StudioSession


def _rotation(world: EntityManager, entity_id: str = "root") -> float:
    """Read an entity's rotation, for terse assertions."""
    entity = world.get_entity(entity_id)
    assert entity is not None
    return entity.get_component(Transform).rotation


class TestAutoMode:
    """The default: apply it."""

    def test_an_edit_applies(
        self, session: StudioSession, populated: EntityManager
    ) -> None:
        outcome = session.apply(SetField("root", Transform, "rotation", 1.0))
        assert outcome.status == "applied"
        assert outcome.applied is True
        assert _rotation(populated) == 1.0

    def test_the_outcome_carries_the_diff(self, session: StudioSession) -> None:
        """So "did that do what I meant?" is answered in the reply, and
        does not cost another call."""
        outcome = session.apply(SetField("root", Transform, "rotation", 1.0))
        assert outcome.diff.fields[0].field_name == "rotation"
        assert outcome.diff.fields[0].after == 1.0

    def test_the_edit_is_undoable(self, session: StudioSession) -> None:
        session.apply(SetField("root", Transform, "rotation", 1.0))
        assert session.stack.can_undo is True

    def test_the_edit_is_journaled(self, session: StudioSession) -> None:
        session.apply(
            SetField("root", Transform, "rotation", 1.0),
            actor=Actor.AGENT,
            action="set_field",
        )
        entry = session.journal.entries[-1]
        assert entry.action == "set_field"
        assert entry.actor is Actor.AGENT
        assert entry.ok is True

    def test_a_failure_is_journaled_before_it_propagates(
        self, session: StudioSession
    ) -> None:
        """A failed agent call is exactly what a reviewer wants to see."""
        with pytest.raises(EditError):
            session.apply(CreateEntity("root"), action="create_entity")

        entry = session.journal.entries[-1]
        assert entry.ok is False
        assert entry.action == "create_entity"

    def test_a_failure_leaves_no_history_entry(self, session: StudioSession) -> None:
        with pytest.raises(EditError):
            session.apply(CreateEntity("root"))
        assert session.stack.can_undo is False


class TestPlanMode:
    """Describe it and change nothing."""

    @pytest.fixture
    def planning(self, populated: EntityManager, core_registry) -> StudioSession:
        return StudioSession(
            populated,
            component_registry=core_registry,
            approval_mode=ApprovalMode.PLAN,
        )

    def test_the_world_is_unchanged(
        self, planning: StudioSession, populated: EntityManager
    ) -> None:
        """The property that makes plan mode worth having."""
        before = planning.snapshot()
        planning.apply(SetField("root", Transform, "rotation", 1.0))
        assert diff_snapshots(before, planning.snapshot()).is_empty

    def test_the_status_says_planned(self, planning: StudioSession) -> None:
        outcome = planning.apply(SetField("root", Transform, "rotation", 1.0))
        assert outcome.status == "planned"
        assert outcome.applied is False

    def test_the_diff_is_the_real_consequence(self, planning: StudioSession) -> None:
        """Not a prediction: the edit really was applied and reverted, so
        the diff is exactly what would happen."""
        outcome = planning.apply(SetField("root", Transform, "rotation", 1.0))
        assert outcome.diff.fields[0].before == 0.0
        assert outcome.diff.fields[0].after == 1.0

    def test_a_cascade_is_reported_in_full(self, planning: StudioSession) -> None:
        """What makes this better than a description: destroying an entity
        removes its owned subtree, and the plan names every id."""
        from pyguara.studio.commands.entity import DestroyEntity

        outcome = planning.apply(DestroyEntity("child_b"))
        assert outcome.diff.removed == ("child_b", "grandchild")

    def test_nothing_becomes_undoable(self, planning: StudioSession) -> None:
        planning.apply(SetField("root", Transform, "rotation", 1.0))
        assert planning.stack.can_undo is False

    def test_an_impossible_edit_still_fails(self, planning: StudioSession) -> None:
        """An edit that cannot be made is the most useful thing a plan can
        report."""
        with pytest.raises(EditError):
            planning.apply(CreateEntity("root"))

    def test_the_plan_is_journaled_as_a_plan(self, planning: StudioSession) -> None:
        planning.apply(SetField("root", Transform, "rotation", 1.0))
        assert planning.journal.entries[-1].detail["planned"] is True


class TestAskMode:
    """Hold it for a person."""

    @pytest.fixture
    def asking(self, populated: EntityManager, core_registry) -> StudioSession:
        return StudioSession(
            populated,
            component_registry=core_registry,
            approval_mode=ApprovalMode.ASK,
        )

    def test_the_edit_is_queued_not_applied(
        self, asking: StudioSession, populated: EntityManager
    ) -> None:
        outcome = asking.apply(SetField("root", Transform, "rotation", 1.0))
        assert outcome.status == "pending"
        assert _rotation(populated) == 0.0

    def test_the_queued_edit_carries_its_diff(self, asking: StudioSession) -> None:
        """So a reviewer sees the consequence rather than the request."""
        outcome = asking.apply(SetField("root", Transform, "rotation", 1.0))
        assert outcome.diff.fields[0].after == 1.0

    def test_it_appears_in_the_pending_list(self, asking: StudioSession) -> None:
        asking.apply(SetField("root", Transform, "rotation", 1.0))
        assert len(asking.pending) == 1
        assert asking.pending[0].label.startswith("Set Transform.rotation")

    def test_approving_applies_it(
        self, asking: StudioSession, populated: EntityManager
    ) -> None:
        outcome = asking.apply(SetField("root", Transform, "rotation", 1.0))
        assert outcome.pending_id is not None

        approved = asking.approve(outcome.pending_id)

        assert approved.status == "applied"
        assert _rotation(populated) == 1.0

    def test_an_approved_edit_is_undoable(self, asking: StudioSession) -> None:
        outcome = asking.apply(SetField("root", Transform, "rotation", 1.0))
        assert outcome.pending_id is not None
        asking.approve(outcome.pending_id)
        assert asking.stack.can_undo is True

    def test_approving_clears_it_from_the_queue(self, asking: StudioSession) -> None:
        outcome = asking.apply(SetField("root", Transform, "rotation", 1.0))
        assert outcome.pending_id is not None
        asking.approve(outcome.pending_id)
        assert asking.pending == ()

    def test_rejecting_discards_it(
        self, asking: StudioSession, populated: EntityManager
    ) -> None:
        outcome = asking.apply(SetField("root", Transform, "rotation", 1.0))
        assert outcome.pending_id is not None

        rejected = asking.reject(outcome.pending_id, "wrong entity")

        assert rejected.status == "rejected"
        assert _rotation(populated) == 0.0
        assert asking.pending == ()

    def test_the_rejection_reason_is_journaled(self, asking: StudioSession) -> None:
        """So an agent reading the journal back learns what not to
        propose again."""
        outcome = asking.apply(SetField("root", Transform, "rotation", 1.0))
        assert outcome.pending_id is not None
        asking.reject(outcome.pending_id, "wrong entity")

        assert asking.journal.entries[-1].detail["reason"] == "wrong entity"

    def test_approving_an_unknown_id_is_refused(self, asking: StudioSession) -> None:
        with pytest.raises(EditError, match="No pending edit"):
            asking.approve("nope")

    def test_approving_twice_is_refused(self, asking: StudioSession) -> None:
        outcome = asking.apply(SetField("root", Transform, "rotation", 1.0))
        assert outcome.pending_id is not None
        asking.approve(outcome.pending_id)
        with pytest.raises(EditError, match="No pending edit"):
            asking.approve(outcome.pending_id)

    def test_an_edit_reviewed_against_a_stale_world_fails(
        self, asking: StudioSession, populated: EntityManager
    ) -> None:
        """The world can move between queueing and approval, and an edit
        approved against a different state must fail rather than land on
        a surprise."""
        outcome = asking.apply(AddComponent("child_a", Tag("Named")))
        assert outcome.pending_id is not None

        # Someone else attaches a Tag in the meantime.
        entity = populated.get_entity("child_a")
        assert entity is not None
        entity.add_component(Tag("Other"))

        with pytest.raises(EditError, match="already has a Tag"):
            asking.approve(outcome.pending_id)

    def test_an_impossible_edit_is_never_queued(self, asking: StudioSession) -> None:
        """Not worth a person's attention."""
        with pytest.raises(EditError):
            asking.apply(CreateEntity("root"))
        assert asking.pending == ()


class TestModeChanges:
    """Switching mid-session."""

    def test_switching_is_journaled(self, session: StudioSession) -> None:
        session.set_approval_mode(ApprovalMode.ASK)
        entry = session.journal.entries[-1]
        assert entry.action == "approval_mode"
        assert entry.detail["to"] == "ask"

    def test_switching_to_the_same_mode_is_silent(self, session: StudioSession) -> None:
        before = len(session.journal)
        session.set_approval_mode(ApprovalMode.AUTO)
        assert len(session.journal) == before

    def test_switching_to_auto_does_not_approve_the_queue(
        self, populated: EntityManager, core_registry
    ) -> None:
        """A statement about future edits, not a blanket approval of the
        ones nobody has looked at."""
        asking = StudioSession(
            populated,
            component_registry=core_registry,
            approval_mode=ApprovalMode.ASK,
        )
        asking.apply(SetField("root", Transform, "rotation", 1.0))

        asking.set_approval_mode(ApprovalMode.AUTO)

        assert len(asking.pending) == 1
        assert _rotation(populated) == 0.0


class TestHistory:
    """Undo and redo through the session."""

    def test_undo_reverts_and_reports(
        self, session: StudioSession, populated: EntityManager
    ) -> None:
        session.apply(SetField("root", Transform, "rotation", 1.0))
        outcome = session.undo()

        assert outcome is not None
        assert outcome.label.startswith("Undo ")
        assert _rotation(populated) == 0.0

    def test_undo_on_an_empty_history_returns_none(
        self, session: StudioSession
    ) -> None:
        assert session.undo() is None

    def test_redo_reapplies(
        self, session: StudioSession, populated: EntityManager
    ) -> None:
        session.apply(SetField("root", Transform, "rotation", 1.0))
        session.undo()
        outcome = session.redo()

        assert outcome is not None
        assert _rotation(populated) == 1.0

    def test_redo_with_nothing_undone_returns_none(
        self, session: StudioSession
    ) -> None:
        session.apply(SetEnabled("root", False))
        assert session.redo() is None

    def test_undo_is_journaled(self, session: StudioSession) -> None:
        """An undo is an action in the record, not a rewinding of it.

        Which is the whole reason the journal is not the undo stack."""
        session.apply(SetField("root", Transform, "rotation", 1.0))
        session.undo()
        assert session.journal.entries[-1].action == "undo"

    def test_an_undo_carries_its_own_diff(self, session: StudioSession) -> None:
        session.apply(SetField("root", Transform, "rotation", 1.0))
        outcome = session.undo()
        assert outcome is not None
        assert outcome.diff.fields[0].after == 0.0


class TestMeasure:
    """Diffing a change that is not a command."""

    def test_reports_what_a_raw_change_did(
        self, session: StudioSession, populated: EntityManager
    ) -> None:
        """For edits outside the command layer -- a scene load, a frame of
        simulation -- where the question is still "what moved?"."""

        def mutate() -> None:
            populated.create_entity("sneaky").add_component(Transform())

        diff = session.measure(mutate)
        assert diff.added == ("sneaky",)

    def test_a_no_op_measures_empty(self, session: StudioSession) -> None:
        assert session.measure(lambda: None).is_empty


class TestSessionOpening:
    """What a new session records about itself."""

    def test_opening_is_journaled(self, session: StudioSession) -> None:
        first = session.journal.entries[0]
        assert first.action == "session_open"
        assert first.actor is Actor.SYSTEM

    def test_the_scene_name_is_recorded(self, session: StudioSession) -> None:
        assert session.journal.entries[0].detail["scene"] == "test_scene"

    def test_the_approval_mode_is_recorded(self, session: StudioSession) -> None:
        assert session.journal.entries[0].detail["approval_mode"] == "auto"

    def test_snapshots_carry_the_scene_name(self, session: StudioSession) -> None:
        assert session.snapshot().scene_name == "test_scene"


class TestActorAttribution:
    """Who an edit is recorded against.

    The field exists so a human's edits can be told from an agent's
    afterwards, which makes a *wrong* actor worse than no actor at all.
    Handlers used to hardcode `Actor.AGENT`, so a script driving the
    surface was recorded as an agent -- the session carries the current
    actor now, and a transport sets it for the duration of one call.
    """

    def test_the_default_actor_is_a_human(self, session: StudioSession) -> None:
        """A bare session is someone at the keyboard."""
        session.apply(SetEnabled("root", False))
        assert session.journal.entries[-1].actor is Actor.HUMAN

    def test_acting_as_changes_the_attribution(self, session: StudioSession) -> None:
        with session.acting_as(Actor.SCRIPT):
            session.apply(SetEnabled("root", False))
        assert session.journal.entries[-1].actor is Actor.SCRIPT

    def test_an_explicit_actor_still_wins(self, session: StudioSession) -> None:
        with session.acting_as(Actor.SCRIPT):
            session.apply(SetEnabled("root", False), actor=Actor.AGENT)
        assert session.journal.entries[-1].actor is Actor.AGENT

    def test_the_previous_actor_is_restored(self, session: StudioSession) -> None:
        with session.acting_as(Actor.AGENT):
            pass
        assert session.actor is Actor.HUMAN

    def test_it_is_restored_even_on_an_exception(self, session: StudioSession) -> None:
        """A failed agent call must not leave the session attributing a
        person's next edit to the agent."""
        with pytest.raises(EditError), session.acting_as(Actor.AGENT):
            session.apply(CreateEntity("root"))

        assert session.actor is Actor.HUMAN

    def test_nesting_restores_the_outer_actor(self, session: StudioSession) -> None:
        with session.acting_as(Actor.AGENT):
            with session.acting_as(Actor.SCRIPT):
                assert session.actor is Actor.SCRIPT
            assert session.actor is Actor.AGENT

    def test_undo_is_attributed_to_the_current_actor(
        self, session: StudioSession
    ) -> None:
        session.apply(SetEnabled("root", False))
        with session.acting_as(Actor.AGENT):
            session.undo()
        assert session.journal.entries[-1].actor is Actor.AGENT
