"""A serializable random-number stream.

`RandomStream` wraps `random.Random` so gameplay code can hold an explicit,
inspectable source of randomness instead of reaching into Python's global
`random` module (which is shared, unseeded, and impossible to snapshot).

State caveat:
    `random.Random.getstate()` returns a nested tuple of ints. Round-tripped
    through JSON (as `pyguara/persistence` and `pyguara/replay` do),
    `json.loads` decodes tuples back as lists, and `random.Random.setstate()`
    raises `TypeError` on a list. `restore_state()` re-tuples defensively so
    a JSON round trip is safe.
"""

from __future__ import annotations

import random
from collections.abc import MutableSequence, Sequence
from typing import Any, TypeVar

T = TypeVar("T")


def _retuple(value: Any) -> Any:
    """Recursively convert lists back to tuples (undoes a JSON round trip)."""
    if isinstance(value, list):
        return tuple(_retuple(item) for item in value)
    return value


class RandomStream:
    """A single, independently seedable source of randomness."""

    __slots__ = ("_rng",)

    def __init__(self, seed: int | None = None) -> None:
        """Create a stream, optionally seeded for a reproducible sequence."""
        self._rng = random.Random(seed)

    def random(self) -> float:
        """Return a float in [0.0, 1.0)."""
        return self._rng.random()

    def uniform(self, a: float, b: float) -> float:
        """Return a float N such that a <= N <= b."""
        return self._rng.uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        """Return an integer N such that a <= N <= b."""
        return self._rng.randint(a, b)

    def choice(self, seq: Sequence[T]) -> T:
        """Return a random element from a non-empty sequence."""
        return self._rng.choice(seq)

    def shuffle(self, seq: MutableSequence[Any]) -> None:
        """Shuffle a mutable sequence in place."""
        self._rng.shuffle(seq)

    def get_state(self) -> tuple[Any, ...]:
        """Return the stream's full internal state, for `restore_state()`."""
        return self._rng.getstate()

    def restore_state(self, state: Sequence[Any]) -> None:
        """Restore state previously returned by `get_state()`.

        Accepts state that has been through a JSON round trip (lists in
        place of tuples) as well as the raw tuple `get_state()` returns.
        """
        self._rng.setstate(_retuple(state))
