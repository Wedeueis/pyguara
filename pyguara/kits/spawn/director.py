"""`SpawnDirector`: a schedule- and pacing-gated queue of waves.

Genre-agnostic on purpose -- a `SpawnEntry.factory` is an opaque
zero-argument callable that actually does the spawning (creating an
enemy, dropping a pickup, whatever); this module never knows what's being
spawned, only when it's allowed to happen. TD wave-clear-to-advance and
horde/arena continuous pressure are both this same mechanism with
different `Wave` parameters and a different schedule, not different code
paths.

**On the release-rate budget this used to have.** The original model was
a budget: an entry cost something, the director accrued budget over time,
and released when it could afford to. Every consumer in this repository
bypassed it (`budget=0.0, cost=0.0`), and `games/tamandua_murundus`
hand-rolled a time-keyed schedule rather than reach for it -- a horde's
shape is "more, on a schedule", not "this much weight per second". The
budget is gone rather than sitting beside the schedule unused; see #163.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class SpawnEntry:
    """One thing a `Wave` can release.

    Attributes:
        factory: Called with no arguments to actually spawn this entry.
            The game closes over whatever context it needs (position,
            enemy type, level) when constructing this -- opaque here.
    """

    factory: Callable[[], None]


@dataclass
class Wave:
    """A batch of `SpawnEntry`s, released one at a time as pacing allows.

    Attributes:
        entries: Spawned in order, front to back.
        interval: Minimum seconds between releasing one entry and
            attempting the next. 0 imposes no pacing delay -- the whole
            wave releases in one tick unless the alive cap stops it.
        delay_before: Seconds to wait, once this wave becomes the active
            one, before its first entry can release.
    """

    entries: list[SpawnEntry]
    interval: float = 0.5
    delay_before: float = 0.0


@dataclass(order=True)
class _ScheduledWave:
    """A wave waiting for the director's clock to reach `time`.

    Attributes:
        time: Seconds from the director's first update.
        sequence: Tie-break, so two waves scheduled at the same time
            queue in the order they were scheduled rather than by
            comparing the waves themselves.
        wave: Queued when the clock passes `time`.
    """

    time: float
    sequence: int
    wave: Wave = field(compare=False)


class SpawnDirector:
    """Releases queued waves' entries as the schedule, pacing and cap allow.

    Three independent gates:

    - **Schedule.** `schedule_at()` holds a wave until the director's own
      clock reaches a point in the run; `queue_wave()` queues one
      immediately, behind whatever is already waiting.
    - **Pacing.** A wave's `interval` caps how fast its entries release,
      so a wave trickles out rather than dumping in one tick.
    - **Alive cap.** Nothing releases while `alive_count()` is at
      `alive_cap`. Every consumer used to enforce this itself, or lean on
      a pool handing back `None`.

    The clock is the director's own accumulated `dt`. A core run clock is
    named in #28 and would be the natural input once it exists; keying off
    `elapsed` in the meantime costs nothing to change later.
    """

    def __init__(
        self,
        *,
        alive_cap: int | None = None,
        alive_count: Callable[[], int] | None = None,
    ) -> None:
        """Create a director with no waves queued yet.

        Args:
            alive_cap: Stop releasing while this many are already out.
                None for no cap.
            alive_count: Called with no arguments for the current live
                count. Pull-based rather than the game reporting each
                spawn and despawn: the game already knows the number, and
                a missed despawn report would wedge the director.

        Raises:
            ValueError: If exactly one of `alive_cap` and `alive_count`
                is given. A cap with nothing to count never binds, and a
                count with no cap is never read -- either way the caller
                means something that is not happening.
        """
        if (alive_cap is None) != (alive_count is None):
            raise ValueError(
                "alive_cap and alive_count go together: a cap with nothing to "
                "count never binds, and a count with no cap is never read. "
                f"Got alive_cap={alive_cap!r}, alive_count={alive_count!r}."
            )

        self.alive_cap = alive_cap
        self.alive_count = alive_count

        self._elapsed = 0.0
        self._scheduled: list[_ScheduledWave] = []
        self._schedule_sequence = 0
        self._waves: deque[Wave] = deque()
        self._active_wave: Wave | None = None
        self._active_entries: deque[SpawnEntry] = deque()
        self._wave_delay_remaining = 0.0
        self._pacing_remaining = 0.0

    @property
    def elapsed(self) -> float:
        """Seconds of `update()` this director has seen."""
        return self._elapsed

    @property
    def is_idle(self) -> bool:
        """Whether nothing is releasing, queued, or still scheduled."""
        return self._active_wave is None and not self._waves and not self._scheduled

    def queue_wave(self, wave: Wave) -> None:
        """Add `wave` to the back of the queue.

        Args:
            wave: Released only once every wave ahead of it has fully
                released its own entries.
        """
        self._waves.append(wave)

    def schedule_at(self, time: float, wave: Wave) -> None:
        """Queue `wave` when the director's clock passes `time`.

        This is the "at this point in the run, this much" shape: a horde
        that thickens, a boss at four minutes. A wave whose time has
        already passed queues on the next `update()`.

        Args:
            time: Seconds from the director's first update.
            wave: Queued -- behind anything already waiting -- when the
                clock reaches `time`.
        """
        self._scheduled.append(_ScheduledWave(time, self._schedule_sequence, wave))
        self._schedule_sequence += 1
        self._scheduled.sort()

    def update(self, dt: float) -> None:
        """Advance the clock and release as many entries as the gates allow.

        Args:
            dt: Seconds since the last call.
        """
        self._elapsed += dt
        self._queue_due_waves()

        # Looping rather than handling one wave per call: a wave that
        # finishes draining mid-tick (interval=0) must let the next queued
        # wave start releasing the same tick too, not wait for a whole
        # extra update() -- each gate below is its own independent
        # countdown, so re-entering the loop for a fresh wave and reusing
        # the same dt against its own delay_before is exactly consistent
        # with how a single wave's gates already work.
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
                if self._at_capacity():
                    return  # Wait for something already out to die.

                entry = self._active_entries.popleft()
                entry.factory()

                self._pacing_remaining = self._active_wave.interval
                if self._pacing_remaining > 0:
                    return  # Respect pacing before attempting the next entry.

            self._active_wave = None

    def _queue_due_waves(self) -> None:
        """Move every scheduled wave whose time has come onto the queue."""
        while self._scheduled and self._scheduled[0].time <= self._elapsed:
            self._waves.append(self._scheduled.pop(0).wave)

    def _at_capacity(self) -> bool:
        """Whether the alive cap is holding releases back right now."""
        if self.alive_cap is None or self.alive_count is None:
            return False
        return self.alive_count() >= self.alive_cap
