"""`SpawnDirector`: a budget- and pacing-gated queue of waves.

Genre-agnostic on purpose -- a `SpawnEntry.factory` is an opaque
zero-argument callable that actually does the spawning (creating an
enemy, dropping a pickup, whatever); this module never knows what's being
spawned, only when it's allowed to happen. TD wave-clear-to-advance and
horde/arena continuous pressure are both this same mechanism with
different `Wave`/budget parameters, not different code paths.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class SpawnEntry:
    """One thing a `Wave` can release.

    Attributes:
        factory: Called with no arguments to actually spawn this entry.
            The game closes over whatever context it needs (position,
            enemy type, level) when constructing this -- opaque here.
        cost: Deducted from the director's budget when this entry
            releases. An entry never releases while `cost` exceeds the
            currently available budget.
    """

    factory: Callable[[], None]
    cost: float = 1.0


@dataclass
class Wave:
    """A batch of `SpawnEntry`s, released one at a time as pacing allows.

    Attributes:
        entries: Spawned in order, front to back.
        interval: Minimum seconds between releasing one entry and
            attempting the next, regardless of budget. 0 imposes no
            pacing delay -- the whole wave releases as fast as budget
            allows.
        delay_before: Seconds to wait, once this wave becomes the active
            one, before its first entry can release.
    """

    entries: list[SpawnEntry]
    interval: float = 0.5
    delay_before: float = 0.0


class SpawnDirector:
    """Releases queued waves' entries as both budget and pacing allow.

    Budget and pacing are independent gates: budget caps how much total
    spawn "weight" can be alive/released over time and regenerates on its
    own schedule; pacing caps how *fast* individual spawns can happen
    even when budget would allow several at once, so a wave with more
    affordable entries than the pacing interval permits still trickles
    out one at a time rather than dumping them all in one tick.
    """

    def __init__(
        self,
        budget: float = 10.0,
        regen_rate: float = 1.0,
        max_budget: float | None = None,
    ) -> None:
        """Create a director with no waves queued yet.

        Args:
            budget: Starting budget.
            regen_rate: Budget regenerated per second, uncapped below
                `max_budget`.
            max_budget: Ceiling `budget` regenerates toward. Defaults to
                the starting `budget` if not given.
        """
        self.budget = budget
        self.max_budget = max_budget if max_budget is not None else budget
        self.regen_rate = regen_rate
        self._waves: deque[Wave] = deque()
        self._active_wave: Wave | None = None
        self._active_entries: deque[SpawnEntry] = deque()
        self._wave_delay_remaining = 0.0
        self._pacing_remaining = 0.0

    @property
    def is_idle(self) -> bool:
        """Whether every queued wave has fully released its entries."""
        return self._active_wave is None and not self._waves

    def queue_wave(self, wave: Wave) -> None:
        """Add `wave` to the back of the queue.

        Args:
            wave: Released only once every wave ahead of it has fully
                released its own entries.
        """
        self._waves.append(wave)

    def update(self, dt: float) -> None:
        """Regenerate budget and release as many entries as gates allow.

        Args:
            dt: Seconds since the last call.
        """
        self.budget = min(self.max_budget, self.budget + self.regen_rate * dt)

        # Looping rather than handling one wave per call: a wave that
        # finishes draining mid-tick (interval=0, budget to spare) must
        # let the next queued wave start releasing the same tick too, not
        # wait for a whole extra update() -- each gate below is its own
        # independent countdown, so re-entering the loop for a fresh wave
        # and reusing the same dt against its own delay_before is exactly
        # consistent with how a single wave's gates already work.
        while True:
            if self._active_wave is None:
                if not self._waves:
                    return
                self._active_wave = self._waves.popleft()
                self._active_entries = deque(self._active_wave.entries)
                self._wave_delay_remaining = self._active_wave.delay_before
                self._pacing_remaining = 0.0

            if self._wave_delay_remaining > 0:
                self._wave_delay_remaining -= dt
                if self._wave_delay_remaining > 0:
                    return

            if self._pacing_remaining > 0:
                self._pacing_remaining -= dt
                if self._pacing_remaining > 0:
                    return

            while self._active_entries:
                entry = self._active_entries[0]
                if entry.cost > self.budget:
                    return  # Not enough budget yet; wait for it to regenerate.

                self.budget -= entry.cost
                entry.factory()
                self._active_entries.popleft()

                self._pacing_remaining = self._active_wave.interval
                if self._pacing_remaining > 0:
                    return  # Respect pacing before attempting the next entry.

            self._active_wave = None
