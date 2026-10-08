"""Deciding *what* goes where, under rules the caller writes.

`poisson_disc_sample()` answers how far apart things may be.
`generate_dungeon()` and `build_graph()` answer where the candidate spots
are. Neither answers the question a level generator actually has to
settle: which of these spots gets the shop, and which the boss, given that
there may be only one shop per floor, that the vault needs a key
somewhere before it, and that the two mini-bosses must not share a wing.

#28 named constraint placement as one of `kits/procgen`'s four algorithm
families and #120 shipped the spacing half of it. This is the other half.

`reclaimer_legacy`'s `constraint_system.py` does all of this already, in
roguelike-floor vocabulary -- `RoomType`, floor pacing, progression
curves. Per #28's "mine it per kit, not wholesale", none of that comes
across: a rule here reads caller-defined string kinds and slot tags, and
the engine has never heard of a room.

    slots = [Slot(position=p, tags={"dead_end"}, group=floor) for p in spots]
    result = place_items(
        slots,
        [PlacementRequest("shop", count=2), PlacementRequest("boss", count=1)],
        [
            MaxPerGroup("shop", limit=1),
            MinSpacing("boss", distance=400.0),
            RequiresTag("boss", {"dead_end"}),
        ],
        rng,
    )
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2


@dataclass(frozen=True)
class Slot:
    """One place something could go.

    Attributes:
        position: Where it is, for distance rules.
        tags: Caller-defined labels -- `"dead_end"`, `"near_water"`,
            `"corridor"`. Rules match against these rather than against
            any fixed vocabulary, which is what keeps the engine
            genre-agnostic.
        group: Caller-defined bucket, for "at most one per group" rules.
            A floor number, a wing, a biome; anything hashable. None
            means the slot belongs to no group and `MaxPerGroup` ignores
            it, rather than lumping every ungrouped slot together -- two
            slots being equally unlabelled is not a statement that they
            are in the same place.
    """

    position: Vector2
    tags: frozenset[str] = frozenset()
    group: object | None = None


@dataclass(frozen=True)
class PlacementRequest:
    """A demand for `count` of one kind.

    Attributes:
        kind: Caller-defined name -- `"shop"`, `"boss"`, `"chest"`.
        count: How many to place.
        priority: Higher goes first. The tightest-constrained kind should
            win the best slots before a plentiful one takes them, and only
            the caller knows which that is. Ties break on count, most
            first, because many-of-a-kind is harder to fit late.
    """

    kind: str
    count: int = 1
    priority: int = 0


@dataclass
class PlacementState:
    """What a rule gets to look at when deciding.

    Read-only by convention: a rule that mutated this would make the
    result depend on rule order, which is the one thing a rule set must
    not do.

    Attributes:
        slots: Every slot, by index.
        assignments: Slot index to the kind placed there, so far.
        counts: How many of each kind are placed so far.
    """

    slots: Sequence[Slot]
    assignments: dict[int, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def indices_of(self, kind: str) -> list[int]:
        """Return the slot indices currently holding `kind`.

        Args:
            kind: The kind to look for.

        Returns:
            Their indices, in slot order.
        """
        return [index for index, placed in self.assignments.items() if placed == kind]

    def positions_of(self, kind: str) -> list[Vector2]:
        """Return the positions currently holding `kind`.

        Args:
            kind: The kind to look for.

        Returns:
            Their positions.
        """
        return [self.slots[index].position for index in self.indices_of(kind)]


@runtime_checkable
class PlacementRule(Protocol):
    """A veto on putting one kind in one slot.

    A rule only ever says no. That is deliberate: a rule that could say
    "yes, definitely" would have to be weighed against the others, and
    then the answer would depend on their order. Vetoes commute, so a rule
    set has no ordering to get wrong, and a game can add one rule without
    re-reading the rest.
    """

    def allows(self, kind: str, slot_index: int, state: PlacementState) -> bool:
        """Report whether `kind` may go in that slot.

        Args:
            kind: The kind being placed.
            slot_index: The candidate slot.
            state: What is placed so far.

        Returns:
            False to veto.
        """
        ...


@dataclass(frozen=True)
class MaxCount:
    """At most `limit` of one kind, anywhere.

    Attributes:
        kind: The kind to cap.
        limit: The cap.
    """

    kind: str
    limit: int

    def allows(self, kind: str, slot_index: int, state: PlacementState) -> bool:
        """Veto once the cap is reached."""
        if kind != self.kind:
            return True
        return state.counts.get(kind, 0) < self.limit


@dataclass(frozen=True)
class MaxPerGroup:
    """At most `limit` of one kind within any one slot group.

    "One shop per floor" when the group is the floor; "one shop every
    three floors" when it is `floor // 3`. The arithmetic is the caller's,
    because only the caller knows what a floor is.

    Attributes:
        kind: The kind to cap.
        limit: The cap, per group.
    """

    kind: str
    limit: int

    def allows(self, kind: str, slot_index: int, state: PlacementState) -> bool:
        """Veto once this slot's group is full."""
        if kind != self.kind:
            return True
        group = state.slots[slot_index].group
        if group is None:
            return True
        placed = sum(
            1 for index in state.indices_of(kind) if state.slots[index].group == group
        )
        return placed < self.limit


@dataclass(frozen=True)
class MinSpacing:
    """No two of a kind closer than `distance`, or none that close to `other`.

    The per-*kind* counterpart of `poisson_disc_sample`'s per-point
    spacing: that one keeps the candidate slots apart, this keeps the
    things put in them apart.

    Attributes:
        kind: The kind being placed.
        distance: The minimum separation.
        other: Measure against this kind instead of against `kind`
            itself -- "no chest within 300 of a shop". None measures
            against the same kind.
    """

    kind: str
    distance: float
    other: str | None = None

    def allows(self, kind: str, slot_index: int, state: PlacementState) -> bool:
        """Veto a slot too close to an already-placed instance."""
        if kind != self.kind:
            return True
        against = self.other if self.other is not None else self.kind
        position = state.slots[slot_index].position
        return all(
            position.distance_to(placed) >= self.distance
            for placed in state.positions_of(against)
        )


@dataclass(frozen=True)
class RequiresTag:
    """A kind may only go in a slot carrying the right tags.

    Attributes:
        kind: The kind to restrict.
        tags: The tags to look for.
        require_all: True to demand every tag, False (the default) to
            accept any one of them.
    """

    kind: str
    tags: frozenset[str]
    require_all: bool = False

    def __init__(
        self, kind: str, tags: Iterable[str], require_all: bool = False
    ) -> None:
        """Accept any iterable of tags, not only a frozenset.

        Args:
            kind: The kind to restrict.
            tags: The tags to look for.
            require_all: Demand every tag rather than any one.
        """
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "tags", frozenset(tags))
        object.__setattr__(self, "require_all", require_all)

    def allows(self, kind: str, slot_index: int, state: PlacementState) -> bool:
        """Veto a slot without the required tags."""
        if kind != self.kind:
            return True
        present = state.slots[slot_index].tags
        if self.require_all:
            return self.tags <= present
        return bool(self.tags & present)


@dataclass(frozen=True)
class ForbidsTag:
    """A kind may not go in a slot carrying any of these tags.

    Attributes:
        kind: The kind to restrict.
        tags: The tags that rule a slot out.
    """

    kind: str
    tags: frozenset[str]

    def __init__(self, kind: str, tags: Iterable[str]) -> None:
        """Accept any iterable of tags.

        Args:
            kind: The kind to restrict.
            tags: The tags that rule a slot out.
        """
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "tags", frozenset(tags))

    def allows(self, kind: str, slot_index: int, state: PlacementState) -> bool:
        """Veto a slot carrying a forbidden tag."""
        if kind != self.kind:
            return True
        return not (self.tags & state.slots[slot_index].tags)


@dataclass(frozen=True)
class Requires:
    """A kind may only be placed once another already is.

    The vault needs its key somewhere first. `place_items` orders requests
    so the prerequisite is placed before its dependent, which is the only
    way a single-pass placer can honour this at all.

    Attributes:
        kind: The dependent kind.
        other: The kind that must exist first.
        count: How many of `other` must exist.
    """

    kind: str
    other: str
    count: int = 1

    def allows(self, kind: str, slot_index: int, state: PlacementState) -> bool:
        """Veto until the prerequisite is satisfied."""
        if kind != self.kind:
            return True
        return state.counts.get(self.other, 0) >= self.count


@dataclass(frozen=True)
class Excludes:
    """Two kinds that must not coexist, or must not be near each other.

    Attributes:
        kind: The kind to restrict.
        other: The kind it cannot coexist with.
        within: Only exclude within this distance; None excludes
            globally, so placing `other` anywhere rules `kind` out
            entirely.
    """

    kind: str
    other: str
    within: float | None = None

    def allows(self, kind: str, slot_index: int, state: PlacementState) -> bool:
        """Veto a slot where the excluded kind is too close, or present."""
        if kind != self.kind:
            return True
        positions = state.positions_of(self.other)
        if self.within is None:
            return not positions
        position = state.slots[slot_index].position
        return all(position.distance_to(other) >= self.within for other in positions)


@dataclass
class PlacementResult:
    """What `place_items` managed to do.

    Attributes:
        assignments: Slot index to the kind placed there.
        unplaced: Kind to how many of it could not be placed. Reported
            rather than raised: a generator that gets four of its five
            chests down should carry on, and one that silently got three
            is the bug this field exists to prevent.
    """

    assignments: dict[int, str]
    unplaced: dict[str, int] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        """Whether every request was satisfied in full."""
        return not self.unplaced

    def slots_for(self, kind: str) -> list[int]:
        """Return the slot indices holding `kind`, in slot order.

        Args:
            kind: The kind to look for.

        Returns:
            Their indices.
        """
        return sorted(
            index for index, placed in self.assignments.items() if placed == kind
        )

    def free_slots(self, total: int) -> list[int]:
        """Return the indices nothing was placed in.

        What a second pass fills with scenery or filler.

        Args:
            total: How many slots there were.

        Returns:
            The unused indices, in order.
        """
        return [index for index in range(total) if index not in self.assignments]


class DependencyCycleError(Exception):
    """Raised when `Requires` rules form a cycle."""


def place_items(
    slots: Sequence[Slot],
    requests: Sequence[PlacementRequest],
    rules: Sequence[PlacementRule],
    rng: RandomStream,
    attempts: int = 8,
) -> PlacementResult:
    """Assign kinds to slots, honouring every rule.

    Greedy, randomised, and retried -- not a backtracking solver. A
    generator runs inside a frame budget, and a CSP solver's runtime on a
    bad instance is unbounded, which trades a slightly worse layout for an
    occasional hang. Instead the whole assignment is attempted several
    times from a shuffled slot order and the best result kept, which in
    practice finds a complete placement whenever one is not tight, and
    reports honestly when it does not.

    Requests are ordered by their `Requires` dependencies first -- a
    prerequisite must be placed before its dependent, or the dependent's
    rule can never pass -- then by priority, then by count.

    Args:
        slots: The candidate spots.
        requests: What to place, and how many.
        rules: The vetoes. Every rule is consulted for every candidate;
            one "no" is enough.
        rng: Seeded stream. The same seed, slots, requests and rules give
            the same result.
        attempts: How many shuffled orders to try before settling for the
            best found. 1 makes it a single greedy pass.

    Returns:
        The assignment, plus whatever could not be placed.

    Raises:
        DependencyCycleError: If `Requires` rules form a cycle, which no
            ordering can satisfy -- a fact about the rule set rather than
            about this particular slot list, so it raises rather than
            being reported as unplaced.
        ValueError: If `attempts` is below 1.
    """
    if attempts < 1:
        raise ValueError(f"attempts must be at least 1, got {attempts}.")

    ordered = _order_requests(requests, rules)
    total_wanted = sum(request.count for request in ordered)

    best: PlacementResult | None = None
    for _ in range(attempts):
        result = _attempt(slots, ordered, rules, rng)
        placed = len(result.assignments)
        if best is None or placed > len(best.assignments):
            best = result
        if placed == total_wanted:
            break

    return best if best is not None else PlacementResult(assignments={})


def _attempt(
    slots: Sequence[Slot],
    ordered: Sequence[PlacementRequest],
    rules: Sequence[PlacementRule],
    rng: RandomStream,
) -> PlacementResult:
    """Run one greedy pass over a shuffled slot order.

    Args:
        slots: The candidate spots.
        ordered: Requests, already dependency- and priority-ordered.
        rules: The vetoes.
        rng: Seeded stream.

    Returns:
        This pass's result.
    """
    state = PlacementState(slots=slots)
    unplaced: dict[str, int] = {}

    order = list(range(len(slots)))
    rng.shuffle(order)

    for request in ordered:
        for _ in range(request.count):
            chosen = next(
                (
                    index
                    for index in order
                    if index not in state.assignments
                    and all(rule.allows(request.kind, index, state) for rule in rules)
                ),
                None,
            )
            if chosen is None:
                unplaced[request.kind] = unplaced.get(request.kind, 0) + 1
                continue
            state.assignments[chosen] = request.kind
            state.counts[request.kind] = state.counts.get(request.kind, 0) + 1

    return PlacementResult(assignments=dict(state.assignments), unplaced=unplaced)


def _order_requests(
    requests: Sequence[PlacementRequest], rules: Sequence[PlacementRule]
) -> list[PlacementRequest]:
    """Order requests so every prerequisite is placed before its dependent.

    A topological sort over the `Requires` rules, with priority then count
    breaking ties among requests that do not depend on each other -- so
    the ordering is deterministic and the tightest-constrained kind gets
    the best slots.

    Args:
        requests: The requests to order.
        rules: The rule set, scanned for `Requires`.

    Returns:
        The ordered requests.

    Raises:
        DependencyCycleError: If the dependencies form a cycle.
    """
    by_kind = {request.kind: request for request in requests}
    prerequisites: dict[str, set[str]] = {kind: set() for kind in by_kind}
    for rule in rules:
        if isinstance(rule, Requires) and rule.kind in prerequisites:
            # A prerequisite nothing was asked for cannot be waited on; the
            # rule will simply veto, and that is reported as unplaced.
            if rule.other in by_kind:
                prerequisites[rule.kind].add(rule.other)

    def rank(kind: str) -> tuple[int, int, str]:
        """Sort key: priority first, then count, then name for determinism."""
        request = by_kind[kind]
        return (-request.priority, -request.count, kind)

    remaining = {kind: set(needs) for kind, needs in prerequisites.items()}
    ordered: list[PlacementRequest] = []

    while remaining:
        ready = sorted(
            (kind for kind, needs in remaining.items() if not needs), key=rank
        )
        if not ready:
            break
        for kind in ready:
            ordered.append(by_kind[kind])
            del remaining[kind]
        for needs in remaining.values():
            needs.difference_update(ready)

    if remaining:
        raise DependencyCycleError(
            f"Requires rules form a cycle among "
            f"{', '.join(sorted(remaining))}; no placement order can satisfy "
            f"them."
        )

    return ordered
