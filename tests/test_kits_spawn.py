"""Tests for `pyguara/kits/spawn/` (SpawnDirector, Wave, SpawnEntry).

The director used to gate releases on a release-rate budget. Every
consumer in this repository switched that gate off (`budget=0.0,
cost=0.0`) and `tamandua_murundus` hand-rolled a time-keyed schedule
instead, so the budget went and the schedule and alive cap took its
place. These tests cover the gates that replaced it, alongside the
pacing and ordering rules that were always there.
"""

from __future__ import annotations

import pytest

from pyguara.kits.spawn import SpawnDirector, SpawnEntry, Wave


def _entry(log: list[str], name: str) -> SpawnEntry:
    return SpawnEntry(factory=lambda: log.append(name))


def test_director_starts_idle() -> None:
    director = SpawnDirector()

    assert director.is_idle is True


def test_queued_wave_is_not_idle() -> None:
    director = SpawnDirector()
    director.queue_wave(Wave(entries=[_entry([], "a")], interval=0.0))

    assert director.is_idle is False


def test_entries_release_in_order_when_nothing_gates_them() -> None:
    log: list[str] = []
    director = SpawnDirector()
    director.queue_wave(
        Wave(
            entries=[_entry(log, "a"), _entry(log, "b"), _entry(log, "c")], interval=0.0
        )
    )

    director.update(0.0)

    assert log == ["a", "b", "c"]
    assert director.is_idle is True


class TestTheSchedule:
    """What replaced the budget: "at this point in the run, this much"."""

    def test_a_scheduled_wave_waits_for_its_time(self) -> None:
        log: list[str] = []
        director = SpawnDirector()
        director.schedule_at(2.0, Wave(entries=[_entry(log, "a")], interval=0.0))

        director.update(1.0)

        assert log == []
        assert director.is_idle is False

    def test_it_releases_once_the_clock_reaches_it(self) -> None:
        log: list[str] = []
        director = SpawnDirector()
        director.schedule_at(2.0, Wave(entries=[_entry(log, "a")], interval=0.0))

        director.update(1.0)
        director.update(1.0)

        assert log == ["a"]
        assert director.is_idle is True

    def test_scheduled_waves_queue_in_time_order_not_call_order(self) -> None:
        log: list[str] = []
        director = SpawnDirector()
        director.schedule_at(2.0, Wave(entries=[_entry(log, "late")], interval=0.0))
        director.schedule_at(1.0, Wave(entries=[_entry(log, "early")], interval=0.0))

        director.update(5.0)

        assert log == ["early", "late"]

    def test_two_waves_at_the_same_time_keep_their_scheduling_order(self) -> None:
        """A `Wave` is not orderable, so the tie-break has to be explicit."""
        log: list[str] = []
        director = SpawnDirector()
        director.schedule_at(1.0, Wave(entries=[_entry(log, "first")], interval=0.0))
        director.schedule_at(1.0, Wave(entries=[_entry(log, "second")], interval=0.0))

        director.update(1.0)

        assert log == ["first", "second"]

    def test_a_time_already_past_queues_on_the_next_update(self) -> None:
        log: list[str] = []
        director = SpawnDirector()
        director.update(5.0)

        director.schedule_at(1.0, Wave(entries=[_entry(log, "a")], interval=0.0))
        director.update(0.0)

        assert log == ["a"]

    def test_the_clock_is_the_directors_own_accumulated_dt(self) -> None:
        director = SpawnDirector()

        director.update(0.25)
        director.update(0.25)

        assert director.elapsed == 0.5

    def test_a_scheduled_wave_queues_behind_one_already_waiting(self) -> None:
        log: list[str] = []
        director = SpawnDirector()
        director.queue_wave(Wave(entries=[_entry(log, "queued")], interval=1.0))
        director.schedule_at(
            0.0, Wave(entries=[_entry(log, "scheduled")], interval=0.0)
        )

        director.update(0.0)

        assert log == ["queued"]


class TestTheAliveCap:
    """The other half of what replaced the budget."""

    def test_nothing_releases_while_the_cap_is_reached(self) -> None:
        log: list[str] = []
        alive = 2
        director = SpawnDirector(alive_cap=2, alive_count=lambda: alive)
        director.queue_wave(Wave(entries=[_entry(log, "a")], interval=0.0))

        director.update(0.0)

        assert log == []
        assert director.is_idle is False

    def test_releases_resume_once_something_dies(self) -> None:
        log: list[str] = []
        alive = [2]
        director = SpawnDirector(alive_cap=2, alive_count=lambda: alive[0])
        director.queue_wave(Wave(entries=[_entry(log, "a")], interval=0.0))

        director.update(0.0)
        assert log == []

        alive[0] = 1
        director.update(0.0)

        assert log == ["a"]

    def test_the_count_is_read_between_entries_not_once_per_tick(self) -> None:
        """A wave releasing into a filling arena has to stop mid-wave."""
        log: list[str] = []
        director = SpawnDirector(alive_cap=2, alive_count=lambda: len(log))
        director.queue_wave(
            Wave(
                entries=[_entry(log, "a"), _entry(log, "b"), _entry(log, "c")],
                interval=0.0,
            )
        )

        director.update(0.0)

        assert log == ["a", "b"]

    def test_no_cap_means_no_gate(self) -> None:
        log: list[str] = []
        director = SpawnDirector()
        director.queue_wave(
            Wave(entries=[_entry(log, "a"), _entry(log, "b")], interval=0.0)
        )

        director.update(0.0)

        assert log == ["a", "b"]

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"alive_cap": 3},
            {"alive_count": lambda: 0},
        ],
        ids=["cap-without-count", "count-without-cap"],
    )
    def test_half_a_cap_is_rejected(self, kwargs: dict[str, object]) -> None:
        """Either half alone is silently inert, which is the failure mode
        this kit is being fixed for in the first place."""
        with pytest.raises(ValueError, match="go together"):
            SpawnDirector(**kwargs)  # type: ignore[arg-type]


class TestPacingAndOrdering:
    def test_pacing_limits_one_spawn_per_interval(self) -> None:
        log: list[str] = []
        director = SpawnDirector()
        director.queue_wave(
            Wave(entries=[_entry(log, "a"), _entry(log, "b")], interval=1.0)
        )

        director.update(0.0)
        assert log == ["a"]

        director.update(0.5)  # still within the 1.0s pacing interval
        assert log == ["a"]

        director.update(0.6)  # total 1.1s since "a" -- pacing has elapsed
        assert log == ["a", "b"]

    def test_zero_interval_releases_the_whole_wave_in_one_update(self) -> None:
        log: list[str] = []
        director = SpawnDirector()
        director.queue_wave(
            Wave(
                entries=[_entry(log, "a"), _entry(log, "b"), _entry(log, "c")],
                interval=0.0,
            )
        )

        director.update(0.0)

        assert log == ["a", "b", "c"]

    def test_delay_before_postpones_the_first_release(self) -> None:
        log: list[str] = []
        director = SpawnDirector()
        director.queue_wave(
            Wave(entries=[_entry(log, "a")], interval=0.0, delay_before=2.0)
        )

        director.update(1.0)
        assert log == []

        director.update(1.1)  # total 2.1s -- delay has elapsed
        assert log == ["a"]

    def test_second_wave_does_not_start_until_the_first_fully_releases(self) -> None:
        log: list[str] = []
        alive = 1
        director = SpawnDirector(alive_cap=1, alive_count=lambda: alive)
        director.queue_wave(Wave(entries=[_entry(log, "a")], interval=0.0))
        director.queue_wave(Wave(entries=[_entry(log, "b")], interval=0.0))

        director.update(0.0)

        assert log == []  # "a" held by the cap; "b" never even attempted

    def test_is_idle_after_every_wave_fully_releases(self) -> None:
        log: list[str] = []
        director = SpawnDirector()
        director.queue_wave(Wave(entries=[_entry(log, "a")], interval=0.0))
        director.queue_wave(Wave(entries=[_entry(log, "b")], interval=0.0))

        director.update(0.0)

        assert log == ["a", "b"]
        assert director.is_idle is True
