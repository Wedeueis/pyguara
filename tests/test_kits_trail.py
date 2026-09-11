"""Tests for `pyguara/kits/trail/` (Trail, advance/grow/overlaps_self/reset)."""

from __future__ import annotations

from pyguara.kits.trail import Trail, advance, contains, grow, overlaps_self, reset

# ========== reset / basic properties ==========


def test_reset_seeds_positions_head_first() -> None:
    trail = Trail()

    reset(trail, [(5, 5), (4, 5), (3, 5)])

    assert list(trail.positions) == [(5, 5), (4, 5), (3, 5)]
    assert trail.head == (5, 5)
    assert trail.tail == (3, 5)
    assert len(trail) == 3


def test_reset_clears_pending_growth() -> None:
    trail = Trail()
    reset(trail, [(0, 0)])
    grow(trail, 2)

    reset(trail, [(1, 1)])

    assert trail.pending_growth == 0


# ========== advance ==========


def test_advance_moves_head_and_keeps_length_constant() -> None:
    trail = Trail()
    reset(trail, [(5, 5), (4, 5), (3, 5)])

    advance(trail, (6, 5))

    assert list(trail.positions) == [(6, 5), (5, 5), (4, 5)]
    assert len(trail) == 3


def test_advance_with_pending_growth_keeps_the_tail_and_spends_one_debt() -> None:
    trail = Trail()
    reset(trail, [(5, 5), (4, 5)])
    grow(trail, 1)

    advance(trail, (6, 5))

    assert list(trail.positions) == [(6, 5), (5, 5), (4, 5)]
    assert len(trail) == 3
    assert trail.pending_growth == 0


def test_grow_by_more_than_one_spans_multiple_advances() -> None:
    trail = Trail()
    reset(trail, [(0, 0)])
    grow(trail, 2)

    advance(trail, (1, 0))
    assert len(trail) == 2
    assert trail.pending_growth == 1

    advance(trail, (2, 0))
    assert len(trail) == 3
    assert trail.pending_growth == 0

    advance(trail, (3, 0))  # growth debt spent, back to popping the tail
    assert len(trail) == 3
    assert list(trail.positions) == [(3, 0), (2, 0), (1, 0)]


# ========== overlaps_self ==========


def test_no_overlap_for_a_short_trail() -> None:
    trail = Trail()
    reset(trail, [(0, 0)])

    assert overlaps_self(trail) is False


def test_moving_into_the_just_vacated_tail_cell_is_not_a_collision() -> None:
    """A non-growing advance pops the tail before the check -- moving into
    where the tail just was is exactly the safe case a manually simulated
    snake needs."""
    trail = Trail()
    reset(trail, [(2, 0), (1, 0), (0, 0)])  # facing +x, tail at (0,0)

    # A tight loop bringing the head back onto (0,0) the same tick the
    # tail vacates it.
    advance(trail, (0, 0))

    assert overlaps_self(trail) is False


def test_moving_onto_a_body_segment_that_does_not_vacate_is_a_collision() -> None:
    trail = Trail()
    # Head (0,0), tail (0,2); (0,1) is a middle segment, not the tail.
    reset(trail, [(0, 0), (1, 0), (1, 1), (0, 1), (0, 2)])

    advance(trail, (0, 1))  # head moves onto a middle segment, not the tail

    assert overlaps_self(trail) is True


def test_growing_into_the_tails_old_cell_is_a_collision() -> None:
    """While growth is owed, the tail does not vacate -- moving onto it
    must read as a collision, unlike the non-growing case."""
    trail = Trail()
    reset(trail, [(2, 0), (1, 0), (0, 0)])
    grow(trail, 1)

    advance(trail, (0, 0))

    assert overlaps_self(trail) is True


# ========== contains ==========


def test_contains_true_for_any_segment() -> None:
    trail = Trail()
    reset(trail, [(0, 0), (1, 0), (2, 0)])

    assert contains(trail, (0, 0)) is True
    assert contains(trail, (1, 0)) is True
    assert contains(trail, (2, 0)) is True


def test_contains_false_for_an_unoccupied_cell() -> None:
    trail = Trail()
    reset(trail, [(0, 0), (1, 0)])

    assert contains(trail, (5, 5)) is False
