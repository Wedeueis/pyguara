"""Tests for `pyguara/kits/spawn/` (SpawnDirector, Wave, SpawnEntry)."""

from __future__ import annotations

from pyguara.kits.spawn import SpawnDirector, SpawnEntry, Wave


def _entry(log: list[str], name: str, cost: float = 1.0) -> SpawnEntry:
    return SpawnEntry(factory=lambda: log.append(name), cost=cost)


def test_director_starts_idle() -> None:
    director = SpawnDirector()

    assert director.is_idle is True


def test_queued_wave_is_not_idle() -> None:
    director = SpawnDirector()
    director.queue_wave(Wave(entries=[_entry([], "a")], interval=0.0))

    assert director.is_idle is False


def test_entries_release_in_order_with_no_pacing_and_plenty_of_budget() -> None:
    log: list[str] = []
    director = SpawnDirector(budget=10.0)
    director.queue_wave(
        Wave(
            entries=[_entry(log, "a"), _entry(log, "b"), _entry(log, "c")], interval=0.0
        )
    )

    director.update(0.0)

    assert log == ["a", "b", "c"]
    assert director.is_idle is True


def test_insufficient_budget_withholds_an_entry() -> None:
    log: list[str] = []
    director = SpawnDirector(budget=0.5, regen_rate=0.0)
    director.queue_wave(Wave(entries=[_entry(log, "a", cost=1.0)], interval=0.0))

    director.update(0.0)

    assert log == []
    assert director.is_idle is False


def test_budget_regenerates_and_eventually_allows_the_spawn() -> None:
    log: list[str] = []
    director = SpawnDirector(budget=0.0, regen_rate=1.0, max_budget=10.0)
    director.queue_wave(Wave(entries=[_entry(log, "a", cost=1.0)], interval=0.0))

    director.update(0.5)
    assert log == []

    director.update(0.6)  # total 1.1s of regen -> budget now >= 1.0
    assert log == ["a"]


def test_budget_is_capped_at_max_budget() -> None:
    director = SpawnDirector(budget=5.0, regen_rate=100.0, max_budget=5.0)

    director.update(10.0)

    assert director.budget == 5.0


def test_max_budget_defaults_to_the_starting_budget() -> None:
    director = SpawnDirector(budget=7.0, regen_rate=100.0)

    director.update(10.0)

    assert director.budget == 7.0


def test_pacing_limits_one_spawn_per_interval() -> None:
    log: list[str] = []
    director = SpawnDirector(budget=10.0)
    director.queue_wave(
        Wave(entries=[_entry(log, "a"), _entry(log, "b")], interval=1.0)
    )

    director.update(0.0)
    assert log == ["a"]

    director.update(0.5)  # still within the 1.0s pacing interval
    assert log == ["a"]

    director.update(0.6)  # total 1.1s since "a" -- pacing has elapsed
    assert log == ["a", "b"]


def test_zero_interval_releases_the_whole_wave_in_one_update() -> None:
    log: list[str] = []
    director = SpawnDirector(budget=10.0)
    director.queue_wave(
        Wave(
            entries=[_entry(log, "a"), _entry(log, "b"), _entry(log, "c")], interval=0.0
        )
    )

    director.update(0.0)

    assert log == ["a", "b", "c"]


def test_delay_before_postpones_the_first_release() -> None:
    log: list[str] = []
    director = SpawnDirector(budget=10.0)
    director.queue_wave(
        Wave(entries=[_entry(log, "a")], interval=0.0, delay_before=2.0)
    )

    director.update(1.0)
    assert log == []

    director.update(1.1)  # total 2.1s -- delay has elapsed
    assert log == ["a"]


def test_second_wave_does_not_start_until_the_first_fully_releases() -> None:
    log: list[str] = []
    director = SpawnDirector(budget=0.0, regen_rate=0.0)  # first entry withheld forever
    director.queue_wave(Wave(entries=[_entry(log, "a", cost=1.0)], interval=0.0))
    director.queue_wave(Wave(entries=[_entry(log, "b", cost=0.0)], interval=0.0))

    director.update(0.0)

    assert log == []  # "a" withheld by budget; "b" never even attempted


def test_is_idle_after_every_wave_fully_releases() -> None:
    log: list[str] = []
    director = SpawnDirector(budget=10.0)
    director.queue_wave(Wave(entries=[_entry(log, "a")], interval=0.0))
    director.queue_wave(Wave(entries=[_entry(log, "b")], interval=0.0))

    director.update(0.0)

    assert log == ["a", "b"]
    assert director.is_idle is True


def test_costs_are_deducted_individually() -> None:
    log: list[str] = []
    director = SpawnDirector(budget=3.0, regen_rate=0.0)
    director.queue_wave(
        Wave(
            entries=[_entry(log, "a", cost=2.0), _entry(log, "b", cost=2.0)],
            interval=0.0,
        )
    )

    director.update(0.0)

    assert log == ["a"]  # "a" spends the only affordable 2.0; "b" needs 2.0 more
    assert director.budget == 1.0


def test_a_wave_trickles_out_across_multiple_ticks_as_budget_regenerates() -> None:
    log: list[str] = []
    director = SpawnDirector(budget=1.0, regen_rate=1.0, max_budget=10.0)
    director.queue_wave(
        Wave(
            entries=[_entry(log, "a", cost=1.0), _entry(log, "b", cost=1.0)],
            interval=0.0,
        )
    )

    director.update(0.0)
    assert log == ["a"]

    director.update(1.0)  # budget regenerates to 1.0, "b" now affordable
    assert log == ["a", "b"]
    assert director.is_idle is True
