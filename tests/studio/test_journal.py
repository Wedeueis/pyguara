"""`Journal`: the append-only record of who did what.

Distinct from the undo stack, and the tests say why: an undo *moves* the
stack and removes what it undid from the undoable history, while the
journal records the undo as another entry. "What did the agent do, in
order" is a question only the journal can answer.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyguara.studio.agent.journal import Actor, Journal, JournalEntry


class TestRecording:
    """Appending entries."""

    def test_records_an_entry(self) -> None:
        journal = Journal()
        entry = journal.record(Actor.HUMAN, "set_field")

        assert entry.actor is Actor.HUMAN
        assert entry.action == "set_field"
        assert entry.ok is True
        assert len(journal) == 1

    def test_sequence_numbers_start_at_one_and_increment(self) -> None:
        """So an entry read back can be referred to unambiguously, even
        when two share a timestamp."""
        journal = Journal()
        first = journal.record(Actor.AGENT, "a")
        second = journal.record(Actor.AGENT, "b")

        assert (first.sequence, second.sequence) == (1, 2)

    def test_records_a_failure_with_its_reason(self) -> None:
        journal = Journal()
        entry = journal.record(
            Actor.AGENT, "add_component", ok=False, error="already has a Tag"
        )

        assert entry.ok is False
        assert entry.error == "already has a Tag"

    def test_detail_carries_a_command_description(self) -> None:
        """Which is what makes an entry reviewable without the world."""
        journal = Journal()
        entry = journal.record(
            Actor.AGENT,
            "set_field",
            detail={"entity_id": "hero", "from": "0.0", "to": "1.0"},
        )
        assert entry.detail["from"] == "0.0"

    def test_entries_are_in_order(self) -> None:
        journal = Journal()
        for name in ("a", "b", "c"):
            journal.record(Actor.SCRIPT, name)
        assert [entry.action for entry in journal.entries] == ["a", "b", "c"]

    def test_actors_are_distinguishable(self) -> None:
        """The whole point of the field: telling an agent's edits apart
        from a human's afterwards."""
        journal = Journal()
        journal.record(Actor.HUMAN, "drag")
        journal.record(Actor.AGENT, "set_field")

        actors = [entry.actor for entry in journal.entries]
        assert actors == [Actor.HUMAN, Actor.AGENT]


class TestMemoryLimit:
    """Bounded in memory, unbounded on disk."""

    def test_the_oldest_in_memory_entry_is_dropped(self) -> None:
        journal = Journal(limit=2)
        for name in ("a", "b", "c"):
            journal.record(Actor.SCRIPT, name)

        assert [entry.action for entry in journal.entries] == ["b", "c"]

    def test_the_file_keeps_everything(self, tmp_path: Path) -> None:
        """The cap stops a long session growing without bound; it is not
        there to discard history."""
        path = tmp_path / "journal.jsonl"
        journal = Journal(path, limit=1)
        for name in ("a", "b", "c"):
            journal.record(Actor.SCRIPT, name)

        assert len(journal) == 1
        assert [entry.action for entry in Journal.read(path)] == ["a", "b", "c"]

    def test_a_non_positive_limit_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            Journal(limit=0)


class TestQueries:
    """Reading a journal back."""

    def test_tail_returns_the_most_recent(self) -> None:
        journal = Journal()
        for index in range(5):
            journal.record(Actor.AGENT, f"op{index}")

        assert [entry.action for entry in journal.tail(2)] == ["op3", "op4"]

    def test_tail_is_oldest_of_them_first(self) -> None:
        """An agent reads it as a narrative of what it just did."""
        journal = Journal()
        for index in range(3):
            journal.record(Actor.AGENT, f"op{index}")

        assert [entry.action for entry in journal.tail(3)] == [
            "op0",
            "op1",
            "op2",
        ]

    def test_tail_beyond_the_length_returns_everything(self) -> None:
        journal = Journal()
        journal.record(Actor.AGENT, "only")
        assert len(journal.tail(100)) == 1

    def test_tail_of_zero_is_empty(self) -> None:
        journal = Journal()
        journal.record(Actor.AGENT, "only")
        assert journal.tail(0) == ()

    def test_a_negative_tail_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must not be negative"):
            Journal().tail(-1)

    def test_failures_returns_only_the_failed(self) -> None:
        """The first thing worth looking at when a run went wrong."""
        journal = Journal()
        journal.record(Actor.AGENT, "ok_one")
        journal.record(Actor.AGENT, "bad", ok=False, error="nope")
        journal.record(Actor.AGENT, "ok_two")

        assert [entry.action for entry in journal.failures()] == ["bad"]


class TestPersistence:
    """JSON Lines on disk."""

    def test_writes_one_json_object_per_line(self, tmp_path: Path) -> None:
        path = tmp_path / "journal.jsonl"
        journal = Journal(path)
        journal.record(Actor.AGENT, "a")
        journal.record(Actor.AGENT, "b")

        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["action"] == "a"

    def test_creates_the_parent_directory(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "deeper" / "journal.jsonl"
        Journal(path).record(Actor.SYSTEM, "open")
        assert path.exists()

    def test_appends_across_journal_instances(self, tmp_path: Path) -> None:
        """A second session adds to the file rather than truncating it."""
        path = tmp_path / "journal.jsonl"
        Journal(path).record(Actor.HUMAN, "first_session")
        Journal(path).record(Actor.HUMAN, "second_session")

        assert [entry.action for entry in Journal.read(path)] == [
            "first_session",
            "second_session",
        ]

    def test_round_trips_every_field(self, tmp_path: Path) -> None:
        path = tmp_path / "journal.jsonl"
        journal = Journal(path)
        journal.record(
            Actor.AGENT,
            "set_field",
            detail={"entity_id": "hero"},
            ok=False,
            error="boom",
        )

        entry = Journal.read(path)[0]
        assert entry.actor is Actor.AGENT
        assert entry.action == "set_field"
        assert entry.detail == {"entity_id": "hero"}
        assert entry.ok is False
        assert entry.error == "boom"
        assert entry.sequence == 1
        assert entry.timestamp > 0

    def test_reading_a_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert Journal.read(tmp_path / "nothing.jsonl") == []

    def test_a_truncated_last_line_does_not_lose_the_rest(self, tmp_path: Path) -> None:
        """A session killed mid-write leaves a partial line.

        Everything before it is still worth having, which is the reason
        for JSON Lines over one JSON document.
        """
        path = tmp_path / "journal.jsonl"
        journal = Journal(path)
        journal.record(Actor.AGENT, "complete")
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"action": "truncated"')

        entries = Journal.read(path)
        assert [entry.action for entry in entries] == ["complete"]

    def test_blank_lines_are_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "journal.jsonl"
        path.write_text(
            json.dumps(JournalEntry(Actor.AGENT, "a", sequence=1).to_dict()) + "\n\n\n",
            encoding="utf-8",
        )
        assert len(Journal.read(path)) == 1

    def test_an_unwritable_path_does_not_lose_the_edit(self, tmp_path: Path) -> None:
        """The edit already happened. Losing the record of it is strictly
        better than failing the edit that was already applied."""
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")

        journal = Journal(blocker / "journal.jsonl")
        entry = journal.record(Actor.HUMAN, "edit")

        assert entry.action == "edit"
        assert len(journal) == 1

    def test_in_memory_only_writes_nothing(self, tmp_path: Path) -> None:
        journal = Journal()
        journal.record(Actor.AGENT, "a")
        assert journal.path is None
        assert list(tmp_path.iterdir()) == []


class TestActorSerialization:
    """`Actor` is a `str` enum so it needs no encoder hook."""

    def test_the_value_is_the_name(self) -> None:
        assert Actor.AGENT.value == "agent"

    def test_it_json_encodes_directly(self) -> None:
        assert json.dumps({"actor": Actor.AGENT}) == '{"actor": "agent"}'

    def test_an_unknown_actor_in_a_file_raises(self) -> None:
        """Rather than silently reading as a human edit."""
        with pytest.raises(ValueError):
            JournalEntry.from_dict({"actor": "nobody", "action": "a"})
