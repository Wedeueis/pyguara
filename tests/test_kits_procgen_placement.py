"""The constraint-placement engine: rules, ordering, and honest failure."""

import pytest

from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.kits.procgen import (
    DependencyCycleError,
    Excludes,
    ForbidsTag,
    MaxCount,
    MaxPerGroup,
    MinSpacing,
    PlacementRequest,
    PlacementRule,
    Requires,
    RequiresTag,
    Slot,
    place_items,
)


def _row(count: int, spacing: float = 100.0, group_size: int = 0) -> list[Slot]:
    """A row of evenly spaced slots, optionally grouped in runs."""
    return [
        Slot(
            position=Vector2(index * spacing, 0.0),
            group=(index // group_size) if group_size else None,
        )
        for index in range(count)
    ]


def _place(slots, requests, rules, seed: int = 1, **kwargs):
    return place_items(slots, requests, rules, RandomStream(seed), **kwargs)


# -- The basics --


def test_everything_asked_for_is_placed_when_there_is_room():
    slots = _row(10)

    result = _place(slots, [PlacementRequest("chest", 3)], [])

    assert result.complete
    assert len(result.slots_for("chest")) == 3


def test_two_kinds_never_share_a_slot():
    slots = _row(4)

    result = _place(
        slots, [PlacementRequest("shop", 2), PlacementRequest("chest", 2)], []
    )

    assert sorted(result.assignments) == [0, 1, 2, 3]
    assert len(set(result.assignments.values())) == 2


def test_free_slots_reports_what_a_second_pass_can_fill():
    slots = _row(5)

    result = _place(slots, [PlacementRequest("boss", 1)], [])

    assert len(result.free_slots(5)) == 4
    assert result.slots_for("boss")[0] not in result.free_slots(5)


def test_more_wanted_than_slots_is_reported_not_raised():
    """A generator that gets four of its five chests down should carry on;
    one that silently got three is the bug `unplaced` prevents."""
    slots = _row(3)

    result = _place(slots, [PlacementRequest("chest", 5)], [])

    assert not result.complete
    assert result.unplaced == {"chest": 2}
    assert len(result.slots_for("chest")) == 3


def test_no_slots_at_all_places_nothing():
    result = _place([], [PlacementRequest("chest", 2)], [])

    assert result.assignments == {}
    assert result.unplaced == {"chest": 2}


def test_no_requests_places_nothing():
    result = _place(_row(5), [], [MaxCount("chest", 1)])

    assert result.complete
    assert result.assignments == {}


# -- Determinism --


def test_the_same_seed_gives_the_same_placement():
    slots = _row(12)
    requests = [PlacementRequest("shop", 2), PlacementRequest("chest", 3)]

    first = _place(slots, requests, [], seed=5)
    second = _place(slots, requests, [], seed=5)

    assert first.assignments == second.assignments


def test_a_different_seed_generally_gives_a_different_placement():
    slots = _row(20)
    requests = [PlacementRequest("chest", 3)]

    results = {
        tuple(_place(slots, requests, [], seed=seed).slots_for("chest"))
        for seed in range(10)
    }

    assert len(results) > 1


def test_attempts_below_one_is_refused():
    with pytest.raises(ValueError, match="at least 1"):
        _place(_row(3), [PlacementRequest("chest", 1)], [], attempts=0)


# -- MaxCount --


def test_max_count_caps_a_kind():
    slots = _row(10)

    result = _place(slots, [PlacementRequest("shop", 5)], [MaxCount("shop", 2)])

    assert len(result.slots_for("shop")) == 2
    assert result.unplaced == {"shop": 3}


def test_a_rule_for_another_kind_does_not_apply():
    slots = _row(10)

    result = _place(slots, [PlacementRequest("chest", 4)], [MaxCount("shop", 1)])

    assert result.complete


# -- MaxPerGroup --


def test_max_per_group_allows_one_per_group():
    """ "One shop per floor" when the group is the floor."""
    slots = _row(12, group_size=4)

    result = _place(slots, [PlacementRequest("shop", 3)], [MaxPerGroup("shop", 1)])

    assert result.complete
    groups = {slots[index].group for index in result.slots_for("shop")}
    assert groups == {0, 1, 2}


def test_max_per_group_refuses_a_fourth_when_there_are_three_groups():
    slots = _row(12, group_size=4)

    result = _place(slots, [PlacementRequest("shop", 4)], [MaxPerGroup("shop", 1)])

    assert result.unplaced == {"shop": 1}


def test_an_ungrouped_slot_is_exempt_rather_than_lumped_together():
    """Two slots being equally unlabelled is not a statement that they are
    in the same place."""
    slots = _row(5)  # every group is None

    result = _place(slots, [PlacementRequest("shop", 3)], [MaxPerGroup("shop", 1)])

    assert result.complete


# -- MinSpacing --


def test_min_spacing_keeps_a_kind_apart():
    slots = _row(10, spacing=100.0)

    result = _place(
        slots, [PlacementRequest("shrine", 3)], [MinSpacing("shrine", 300.0)]
    )

    assert result.complete
    positions = [slots[index].position for index in result.slots_for("shrine")]
    for i, first in enumerate(positions):
        for second in positions[i + 1 :]:
            assert first.distance_to(second) >= 300.0


def test_min_spacing_can_measure_against_another_kind():
    slots = _row(10, spacing=100.0)

    result = _place(
        slots,
        [PlacementRequest("shop", 1, priority=5), PlacementRequest("chest", 3)],
        [MinSpacing("chest", 250.0, other="shop")],
    )

    shop = slots[result.slots_for("shop")[0]].position
    for index in result.slots_for("chest"):
        assert slots[index].position.distance_to(shop) >= 250.0


def test_spacing_too_tight_to_satisfy_is_reported():
    slots = _row(4, spacing=100.0)

    result = _place(
        slots, [PlacementRequest("shrine", 3)], [MinSpacing("shrine", 1000.0)]
    )

    assert result.unplaced == {"shrine": 2}


# -- Tags --


def test_requires_tag_restricts_a_kind_to_matching_slots():
    slots = [
        Slot(
            Vector2(index * 100, 0),
            tags=frozenset({"dead_end"} if index % 4 == 0 else {"corridor"}),
        )
        for index in range(12)
    ]

    result = _place(
        slots, [PlacementRequest("boss", 2)], [RequiresTag("boss", {"dead_end"})]
    )

    assert result.complete
    for index in result.slots_for("boss"):
        assert "dead_end" in slots[index].tags


def test_requires_all_demands_every_tag():
    slots = [
        Slot(Vector2(0, 0), tags=frozenset({"dead_end"})),
        Slot(Vector2(100, 0), tags=frozenset({"dead_end", "large"})),
    ]

    result = _place(
        slots,
        [PlacementRequest("boss", 1)],
        [RequiresTag("boss", {"dead_end", "large"}, require_all=True)],
    )

    assert result.slots_for("boss") == [1]


def test_requires_tag_accepts_any_iterable_of_tags():
    rule = RequiresTag("boss", ["a", "b", "a"])

    assert rule.tags == frozenset({"a", "b"})


def test_forbids_tag_rules_a_slot_out():
    slots = [
        Slot(
            Vector2(index * 100, 0), tags=frozenset({"flooded"} if index < 8 else set())
        )
        for index in range(10)
    ]

    result = _place(
        slots, [PlacementRequest("chest", 2)], [ForbidsTag("chest", {"flooded"})]
    )

    assert sorted(result.slots_for("chest")) == [8, 9]


# -- Requires --


def test_a_dependent_kind_is_placed_after_its_prerequisite():
    """The vault needs its key somewhere first. A single-pass placer can
    only honour that by ordering the requests."""
    slots = _row(6)

    result = _place(
        slots,
        [PlacementRequest("vault", 1), PlacementRequest("key", 1)],
        [Requires("vault", "key")],
    )

    assert result.complete
    assert result.slots_for("key")
    assert result.slots_for("vault")


def test_a_dependent_kind_is_unplaced_when_its_prerequisite_is_not_requested():
    slots = _row(6)

    result = _place(slots, [PlacementRequest("vault", 1)], [Requires("vault", "key")])

    assert result.unplaced == {"vault": 1}


def test_requires_can_demand_several_of_the_prerequisite():
    slots = _row(6)

    result = _place(
        slots,
        [PlacementRequest("vault", 1), PlacementRequest("key", 1)],
        [Requires("vault", "key", count=2)],
    )

    assert result.unplaced == {"vault": 1}


def test_a_dependency_chain_is_ordered_throughout():
    slots = _row(6)

    result = _place(
        slots,
        [
            PlacementRequest("c", 1),
            PlacementRequest("a", 1),
            PlacementRequest("b", 1),
        ],
        [Requires("c", "b"), Requires("b", "a")],
    )

    assert result.complete


def test_a_dependency_cycle_raises_rather_than_reporting_unplaced():
    """A fact about the rule set, not about this slot list."""
    slots = _row(6)

    with pytest.raises(DependencyCycleError, match="cycle"):
        _place(
            slots,
            [PlacementRequest("a", 1), PlacementRequest("b", 1)],
            [Requires("a", "b"), Requires("b", "a")],
        )


# -- Excludes --


def test_excludes_globally_when_no_distance_is_given():
    slots = _row(6)

    result = _place(
        slots,
        [PlacementRequest("altar", 1, priority=5), PlacementRequest("shrine", 1)],
        [Excludes("shrine", "altar")],
    )

    assert result.slots_for("altar")
    assert result.unplaced == {"shrine": 1}


def test_excludes_within_a_distance_leaves_room_further_away():
    slots = _row(10, spacing=100.0)

    result = _place(
        slots,
        [PlacementRequest("altar", 1, priority=5), PlacementRequest("shrine", 1)],
        [Excludes("shrine", "altar", within=300.0)],
    )

    assert result.complete
    altar = slots[result.slots_for("altar")[0]].position
    shrine = slots[result.slots_for("shrine")[0]].position
    assert altar.distance_to(shrine) >= 300.0


# -- Priority and retries --


def test_priority_decides_who_gets_the_scarce_slots_first():
    slots = [
        Slot(Vector2(0, 0), tags=frozenset({"special"})),
        Slot(Vector2(100, 0)),
        Slot(Vector2(200, 0)),
    ]
    rules = [RequiresTag("boss", {"special"}), RequiresTag("shop", {"special"})]

    result = _place(
        slots,
        [
            PlacementRequest("shop", 1, priority=1),
            PlacementRequest("boss", 1, priority=9),
        ],
        rules,
    )

    assert result.slots_for("boss") == [0]
    assert result.unplaced == {"shop": 1}


def test_retries_find_a_placement_a_single_pass_misses():
    """Five slots 100 apart with 200 spacing has exactly one answer --
    slots 0, 2 and 4 -- so a greedy pass that takes slot 1 first can never
    complete. A reshuffled retry is cheaper and far more predictable than
    a backtracking solver, which is the trade this engine makes."""
    slots = _row(5, spacing=100.0)
    requests = [PlacementRequest("shrine", 3)]
    rules = [MinSpacing("shrine", 200.0)]

    once = _place(slots, requests, rules, seed=4, attempts=1)
    retried = _place(slots, requests, rules, seed=4, attempts=32)

    assert not once.complete
    assert retried.complete
    assert retried.slots_for("shrine") == [0, 2, 4]


def test_the_best_attempt_is_kept_when_none_is_complete():
    """Not the last one tried: a generator should get the fullest layout
    the retries found, not whichever order came up last."""
    slots = _row(5, spacing=100.0)

    result = _place(
        slots,
        [PlacementRequest("shrine", 4)],
        [MinSpacing("shrine", 200.0)],
        seed=4,
        attempts=32,
    )

    assert len(result.slots_for("shrine")) == 3
    assert result.unplaced == {"shrine": 1}


def test_a_single_attempt_is_still_a_valid_placement():
    slots = _row(10)

    result = _place(
        slots,
        [PlacementRequest("shrine", 2)],
        [MinSpacing("shrine", 300.0)],
        attempts=1,
    )

    positions = [slots[index].position for index in result.slots_for("shrine")]
    if len(positions) == 2:
        assert positions[0].distance_to(positions[1]) >= 300.0


# -- Rules are vetoes, in any order --


def test_a_custom_rule_only_needs_an_allows_method():
    class OnlyEvenSlots:
        def allows(self, kind, slot_index, state):
            return slot_index % 2 == 0

    slots = _row(6)

    result = _place(slots, [PlacementRequest("chest", 3)], [OnlyEvenSlots()])

    assert sorted(result.slots_for("chest")) == [0, 2, 4]
    assert isinstance(OnlyEvenSlots(), PlacementRule)


def test_rule_order_does_not_change_the_outcome():
    """Vetoes commute, which is why a rule can only ever say no."""
    slots = _row(12, group_size=4)
    requests = [PlacementRequest("shop", 3)]
    rules = [MaxPerGroup("shop", 1), MinSpacing("shop", 200.0), MaxCount("shop", 3)]

    forward = _place(slots, requests, list(rules), seed=2)
    backward = _place(slots, requests, list(reversed(rules)), seed=2)

    assert forward.assignments == backward.assignments


def test_every_rule_is_consulted_so_one_no_is_enough():
    slots = _row(6, group_size=6)

    result = _place(
        slots,
        [PlacementRequest("shop", 2)],
        [MaxPerGroup("shop", 2), MaxCount("shop", 1)],
    )

    assert len(result.slots_for("shop")) == 1


# -- Composition with the rest of the kit --


def test_it_composes_with_poisson_disc_slots():
    """The spacing half decides where the candidates are; this decides what
    goes in them."""
    from pyguara.common.types import Rect
    from pyguara.kits.procgen import poisson_disc_sample

    points = poisson_disc_sample(Rect(0, 0, 600, 600), 80.0, RandomStream(3))
    slots = [Slot(position=point) for point in points]

    result = _place(
        slots,
        [PlacementRequest("shrine", 3), PlacementRequest("chest", 5)],
        [MinSpacing("shrine", 200.0)],
    )

    assert result.complete
    assert len(result.free_slots(len(slots))) == len(slots) - 8


def test_it_composes_with_a_generated_graph():
    from pyguara.common.types import Rect
    from pyguara.kits.procgen import build_graph, scatter_points

    points = scatter_points(Rect(0, 0, 800, 800), 14, RandomStream(6))
    edges = build_graph(points, RandomStream(6), extra_edge_chance=0.0)
    degree = {index: 0 for index in range(len(points))}
    for i, j in edges:
        degree[i] += 1
        degree[j] += 1

    slots = [
        Slot(
            position=point,
            tags=frozenset({"dead_end"} if degree[index] == 1 else {"junction"}),
        )
        for index, point in enumerate(points)
    ]

    result = _place(
        slots, [PlacementRequest("boss", 1)], [RequiresTag("boss", {"dead_end"})]
    )

    assert result.complete
    assert degree[result.slots_for("boss")[0]] == 1
