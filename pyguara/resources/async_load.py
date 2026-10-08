"""Asynchronous resource loading: a thread pool where it pays, a budget elsewhere.

Shaped by measurement rather than by instinct, and the measurements are in
"Resource loading, and the GIL" in `docs/guides/performance.md`. In short:

- One 2356x1824 jpg decode costs **30.9 ms** -- nearly two 60 Hz frames. A
  scene loading a dozen textures on entry stalls for a third of a second.
  That is the cost this module exists to move.
- `pygame-ce` decodes with the GIL **released** (2.9-3.4x on four threads),
  so a worker pays. `json` parses with it **held** (0.71x -- *slower*
  threaded than inline), so a worker costs. Threading is therefore opt-in
  per loader, never the default.
- `asyncio` is the wrong tool: it overlaps I/O *waits*, and reading 2.5 MB
  costs 0.17 ms against 30.9 ms to decode it. There is no wait to overlap,
  the expense is CPU, and an event loop cannot parallelise CPU on a GIL
  build -- quite apart from needing an event loop inside a frame loop.

Two tiers follow, and the first matters more than the second:

1. **A time-budgeted main-thread pump.** `ResourceManager.pump(budget_ms)`
   completes work until the budget is spent, then returns. This alone turns
   a stall into a spread, works for every loader including GIL-bound ones,
   is deterministic, and is where device uploads must happen anyway.
2. **An opt-in decode pool.** Loaders that declare `threaded_decode` have
   their decode phase run on workers, so by the time the pump reaches them
   the expensive half is already done.

**Thread affinity, and why there is no cache lock.** #40 asks for a lock
around `_cache`/`_reference_counts` "once there is a concurrent caller".
There is none: a worker thread only turns a path into bytes. Every cache
read and write stays on the thread that calls `load()` and `pump()`, so the
invariant is thread *affinity* rather than mutual exclusion -- cheaper, and
with no lock ordering to get wrong. Call `load`, `load_async` and `pump`
from one thread, as a frame loop naturally does.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from pyguara.log import get_logger

if TYPE_CHECKING:
    from pyguara.resources.meta import AssetMeta
    from pyguara.resources.types import Resource

logger = get_logger(__name__)

DEFAULT_PUMP_BUDGET_MS = 4.0
"""Default per-frame budget for `pump()`.

A quarter of a 60 Hz frame. Small enough to leave the rest of the frame
alone, large enough to finish several uploads per call.
"""


class LoadState(Enum):
    """Where a queued load has got to."""

    PENDING = auto()
    """Queued; decode has not finished."""

    DECODED = auto()
    """Decode done, waiting for the main thread to upload."""

    READY = auto()
    """Finished and in the cache."""

    FAILED = auto()
    """Decode or upload raised; see `error`."""


@dataclass
class LoadRequest:
    """One queued load, and the handle the caller watches.

    Attributes:
        key: The resolved cache key (a path).
        requested_as: The name the caller asked for, for error messages.
        resource_type: The type the caller expects.
        state: Where this request has got to.
        resource: The finished resource, once `state` is READY.
        error: What went wrong, once `state` is FAILED.
    """

    key: str
    requested_as: str
    resource_type: type[Resource]
    state: LoadState = LoadState.PENDING
    resource: Resource | None = None
    error: BaseException | None = None

    # Set when the decode is running on, or has returned from, a worker.
    _future: Future[object] | None = field(default=None, repr=False)
    # A main-thread decode that has not run yet.
    _inline_decode: Callable[[], object] | None = field(default=None, repr=False)
    _decoded: object = field(default=None, repr=False)
    _meta: AssetMeta | None = field(default=None, repr=False)

    @property
    def done(self) -> bool:
        """Whether this request has finished, successfully or not."""
        return self.state in (LoadState.READY, LoadState.FAILED)


class LoadBatch:
    """Progress over a group of queued loads, for a loading screen.

    Counts requests rather than bytes: a loading bar wants a number that
    only goes up, and byte totals are not known until every file has been
    stat-ed, which is itself work.
    """

    def __init__(self, requests: list[LoadRequest]) -> None:
        """Initialize the batch.

        Args:
            requests: The requests this batch tracks.
        """
        self._requests = requests

    @property
    def total(self) -> int:
        """How many loads this batch covers."""
        return len(self._requests)

    @property
    def completed(self) -> int:
        """How many have finished, successfully or not."""
        return sum(1 for request in self._requests if request.done)

    @property
    def failed(self) -> list[LoadRequest]:
        """The requests that failed, for reporting rather than guessing."""
        return [r for r in self._requests if r.state is LoadState.FAILED]

    @property
    def progress(self) -> float:
        """Completion as 0.0..1.0. An empty batch is complete."""
        if not self._requests:
            return 1.0
        return self.completed / self.total

    @property
    def done(self) -> bool:
        """Whether every load in this batch has finished."""
        return self.completed == self.total

    def __len__(self) -> int:
        """How many loads this batch covers."""
        return self.total


class DecodePool:
    """A lazily-created thread pool for loaders that release the GIL.

    Lazy because a game that never calls `load_async()` should not pay for
    threads it will not use, and because the pool's size depends on nothing
    knowable at manager construction.
    """

    def __init__(self, max_workers: int = 4) -> None:
        """Initialize the pool without starting it.

        Args:
            max_workers: Worker count. Four, not `cpu_count()`: the
                measured scaling of image decode flattens well before that
                (2.9-3.4x on four), and every extra worker is another
                thread competing with the frame for the GIL during the
                parts of decode that hold it.
        """
        self._max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None

    def submit(self, fn: Callable[[], object]) -> Future[object]:
        """Run `fn` on a worker, starting the pool if needed.

        Args:
            fn: The decode callable.

        Returns:
            Its future.
        """
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers, thread_name_prefix="pyguara-decode"
            )
            logger.debug("Started decode pool with %d workers", self._max_workers)
        return self._executor.submit(fn)

    def shutdown(self, wait: bool = True) -> None:
        """Stop the pool, if one was ever started.

        Args:
            wait: Block until in-flight decodes finish. True by default:
                a decode holds no device state, so letting it finish is
                cheap and avoids tearing down a thread mid-read.
        """
        if self._executor is not None:
            self._executor.shutdown(wait=wait)
            self._executor = None

    @property
    def started(self) -> bool:
        """Whether any worker thread has been created."""
        return self._executor is not None


class Budget:
    """A spend-down timer for one `pump()` call.

    Checked *between* units of work, never inside one: a decode or an upload
    cannot be interrupted part-way, so the honest contract is "stop starting
    new work once the budget is gone", and a single over-long item can still
    overrun it. A budget that promised otherwise would be lying.
    """

    def __init__(self, budget_ms: float) -> None:
        """Start the clock.

        Args:
            budget_ms: Milliseconds this pump may spend. Non-positive means
                unlimited, which is what a loading screen wants between
                frames it is not trying to keep smooth.
        """
        self._limit = budget_ms / 1000.0 if budget_ms > 0 else None
        self._start = time.perf_counter()

    @property
    def spent(self) -> bool:
        """Whether the budget has run out."""
        if self._limit is None:
            return False
        return (time.perf_counter() - self._start) >= self._limit

    @property
    def elapsed_ms(self) -> float:
        """How long this pump has been running, in milliseconds."""
        return (time.perf_counter() - self._start) * 1000.0


__all__ = [
    "DEFAULT_PUMP_BUDGET_MS",
    "Budget",
    "DecodePool",
    "LoadBatch",
    "LoadRequest",
    "LoadState",
]
