"""Asynchronous resource loading: the queue, the budget, and thread affinity.

The design is measured rather than assumed -- see "Resource loading, and the
GIL" in `docs/guides/performance.md`. Image decode releases the GIL and
scales ~3x on four threads; `json` holds it and runs 0.71x threaded, i.e.
*slower* than inline. So threading is opt-in per loader, and these tests
pin both halves of that: a loader that opts in decodes on a worker, and one
that does not is never handed to a thread at all.

The invariant that matters most is thread affinity. `upload()` touches the
device context, so it must only ever run on the pumping thread -- a test
asserts that directly rather than trusting the code to be read correctly.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from pyguara.resources.async_load import (
    Budget,
    DecodePool,
    LoadBatch,
    LoadState,
)
from pyguara.resources.data import DataResource
from pyguara.resources.loaders.data_loader import JsonLoader
from pyguara.resources.manager import ResourceManager
from pyguara.resources.meta import AssetMeta
from pyguara.resources.types import Resource

MAIN_THREAD = "MainThread"


class Img(Resource):
    """A stand-in for a texture."""

    @property
    def native_handle(self) -> str:
        return "img"


class Other(Resource):
    """A different type, for the type-mismatch tests."""

    @property
    def native_handle(self) -> str:
        return "other"


class TwoPhaseLoader:
    """Shaped like the GL texture loader: decode off-thread, upload on it."""

    def __init__(self, *, threaded: bool = True, delay: float = 0.0) -> None:
        self.threaded_decode = threaded
        self._delay = delay
        self.decode_threads: set[str] = set()
        self.upload_threads: set[str] = set()
        self.decode_calls = 0

    @property
    def supported_extensions(self) -> list[str]:
        return [".img"]

    def load(self, path: str) -> Resource:  # pragma: no cover - must not run
        raise AssertionError("the async path must not call load()")

    def decode(self, path: str, meta: AssetMeta | None) -> object:
        self.decode_threads.add(threading.current_thread().name)
        self.decode_calls += 1
        if self._delay:
            time.sleep(self._delay)
        return b"pixels"

    def upload(self, path: str, decoded: object, meta: AssetMeta | None) -> Resource:
        self.upload_threads.add(threading.current_thread().name)
        return Img(path)


class FailingTwoPhase(TwoPhaseLoader):
    """Fails in whichever phase the test asks for."""

    def __init__(self, *, where: str) -> None:
        super().__init__(threaded=True)
        self._where = where

    def decode(self, path: str, meta: AssetMeta | None) -> object:
        if self._where == "decode":
            raise OSError("decode exploded")
        return super().decode(path, meta)

    def upload(self, path: str, decoded: object, meta: AssetMeta | None) -> Resource:
        if self._where == "upload":
            raise RuntimeError("upload exploded")
        return super().upload(path, decoded, meta)


def _manager(loader: object) -> ResourceManager:
    manager = ResourceManager()
    manager.register_loader(loader)  # type: ignore[arg-type]
    return manager


def _drain(manager: ResourceManager, batch: LoadBatch, limit: int = 2000) -> int:
    """Pump until the batch finishes. Returns the number of pumps."""
    pumps = 0
    while not batch.done and pumps < limit:
        manager.pump(budget_ms=0.0)
        pumps += 1
        if not batch.done:
            time.sleep(0.001)
    assert batch.done, "batch never finished"
    return pumps


@pytest.mark.unit
class TestThreadAffinity:
    def test_upload_only_ever_runs_on_the_pumping_thread(self) -> None:
        """The invariant the whole split exists for: `upload()` touches the
        GL context, which belongs to one thread. A decode on a worker that
        then uploaded there would corrupt or crash, not merely misbehave."""
        loader = TwoPhaseLoader(delay=0.005)
        manager = _manager(loader)

        batch = manager.preload([(f"/x/{i}.img", Img) for i in range(6)])
        _drain(manager, batch)

        assert loader.upload_threads == {MAIN_THREAD}

    def test_an_opted_in_decode_runs_off_the_main_thread(self) -> None:
        loader = TwoPhaseLoader(delay=0.005)
        manager = _manager(loader)

        batch = manager.preload([(f"/x/{i}.img", Img) for i in range(6)])
        _drain(manager, batch)

        assert loader.decode_threads
        assert MAIN_THREAD not in loader.decode_threads

    def test_a_loader_that_does_not_opt_in_is_never_threaded(self) -> None:
        """`json` parsing holds the GIL and measured 0.71x threaded, so
        handing an unmarked loader to a pool would make it slower. The
        default has to be inline, and this pins it."""
        loader = TwoPhaseLoader(threaded=False)
        manager = _manager(loader)

        batch = manager.preload([("/x/0.img", Img)])
        _drain(manager, batch)

        assert loader.decode_threads == {MAIN_THREAD}

    def test_a_single_phase_loader_also_stays_on_the_main_thread(
        self, tmp_path: Path
    ) -> None:
        """It cannot be split, so the only available gain is the spread
        across frames -- which for a GIL-holding loader is the only gain
        there is."""
        (tmp_path / "data.json").write_text(json.dumps({"hp": 1}))
        manager = ResourceManager()
        manager.register_loader(JsonLoader())
        manager.index_directory(str(tmp_path))

        batch = manager.preload([("data.json", DataResource)])
        _drain(manager, batch)

        assert batch.progress == 1.0
        assert manager.load("data.json", DataResource).native_handle == {"hp": 1}


@pytest.mark.unit
class TestQueueing:
    def test_load_async_does_no_work_itself(self) -> None:
        """Queueing must be cheap: the point is to return to the frame."""
        loader = TwoPhaseLoader(delay=0.05)
        manager = _manager(loader)

        request = manager.load_async("/x/0.img", Img)

        assert request.state is LoadState.PENDING
        assert request.resource is None
        assert manager.pending_loads == 1

    def test_a_cache_hit_comes_back_ready(self) -> None:
        """So a caller never has to special-case "already loaded"."""
        loader = TwoPhaseLoader()
        manager = _manager(loader)
        batch = manager.preload([("/x/0.img", Img)])
        _drain(manager, batch)

        again = manager.load_async("/x/0.img", Img)

        assert again.state is LoadState.READY
        assert again.resource is not None
        assert manager.pending_loads == 0

    def test_a_cached_type_mismatch_fails_without_loading(self) -> None:
        loader = TwoPhaseLoader()
        manager = _manager(loader)
        _drain(manager, manager.preload([("/x/0.img", Img)]))

        request = manager.load_async("/x/0.img", Other)

        assert request.state is LoadState.FAILED
        assert isinstance(request.error, TypeError)

    def test_an_unregistered_extension_raises_at_queue_time(self) -> None:
        """A programming error, so it surfaces where it was made rather
        than three frames later inside a pump."""
        manager = _manager(TwoPhaseLoader())
        with pytest.raises(ValueError, match="No loader registered"):
            manager.load_async("/x/0.unknown", Img)

    def test_dropping_the_request_does_not_cancel_the_load(self) -> None:
        loader = TwoPhaseLoader()
        manager = _manager(loader)
        manager.load_async("/x/0.img", Img)  # reference discarded

        while manager.pending_loads:
            manager.pump(budget_ms=0.0)
            time.sleep(0.001)

        assert loader.upload_threads == {MAIN_THREAD}
        assert len(list(manager.iter_cached())) == 1

    def test_the_resource_enters_the_cache_unpinned(self) -> None:
        """Same lifecycle as `load()`: a load is a cache-get, not an
        acquire, so `unload_unused()` must still evict it."""
        manager = _manager(TwoPhaseLoader())
        _drain(manager, manager.preload([("/x/0.img", Img)]))

        assert manager.unload_unused() == 1


@pytest.mark.unit
class TestBudget:
    def test_a_spent_budget_stops_starting_work(self) -> None:
        loader = TwoPhaseLoader(threaded=False, delay=0.01)
        manager = _manager(loader)
        manager.preload([(f"/x/{i}.img", Img) for i in range(10)])

        manager.pump(budget_ms=15.0)

        # Some finished, not all: the budget bit before the queue emptied.
        assert 0 < loader.decode_calls < 10

    def test_an_unlimited_budget_drains_what_it_can(self) -> None:
        loader = TwoPhaseLoader(threaded=False)
        manager = _manager(loader)
        batch = manager.preload([(f"/x/{i}.img", Img) for i in range(10)])

        manager.pump(budget_ms=0.0)

        assert batch.done

    def test_pump_returns_the_number_finished(self) -> None:
        manager = _manager(TwoPhaseLoader(threaded=False))
        manager.preload([(f"/x/{i}.img", Img) for i in range(3)])

        assert manager.pump(budget_ms=0.0) == 3
        assert manager.pump(budget_ms=0.0) == 0

    def test_pumping_an_empty_queue_is_free(self) -> None:
        manager = _manager(TwoPhaseLoader())
        assert manager.pump() == 0

    def test_a_pending_worker_decode_costs_no_budget(self) -> None:
        """A pump must never block on a thread, or the budget means
        nothing."""
        loader = TwoPhaseLoader(delay=0.2)
        manager = _manager(loader)
        manager.preload([(f"/x/{i}.img", Img) for i in range(4)])

        start = time.perf_counter()
        manager.pump(budget_ms=4.0)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms < 50  # nowhere near the 200ms decode
        assert manager.pending_loads == 4

    def test_the_budget_stops_between_items_not_inside_one(self) -> None:
        """The honest contract: work already started runs to completion, so
        one slow item can overrun the budget. A budget claiming otherwise
        would be a lie."""
        budget = Budget(budget_ms=5.0)
        assert not budget.spent
        time.sleep(0.01)
        assert budget.spent
        assert budget.elapsed_ms >= 5.0

    def test_a_non_positive_budget_is_unlimited(self) -> None:
        budget = Budget(budget_ms=0.0)
        time.sleep(0.005)
        assert not budget.spent


@pytest.mark.unit
class TestProgress:
    def test_progress_runs_from_zero_to_one(self) -> None:
        loader = TwoPhaseLoader(threaded=False)
        manager = _manager(loader)
        batch = manager.preload([(f"/x/{i}.img", Img) for i in range(4)])

        assert batch.progress == 0.0
        assert batch.total == 4
        assert len(batch) == 4

        _drain(manager, batch)

        assert batch.progress == 1.0
        assert batch.completed == 4

    def test_an_empty_batch_is_already_complete(self) -> None:
        """A loading screen given nothing to load must not wait forever."""
        manager = _manager(TwoPhaseLoader())
        batch = manager.preload([])
        assert batch.done
        assert batch.progress == 1.0

    def test_a_failure_counts_as_completed_and_is_reported(self) -> None:
        """Progress must reach 1.0 even when something broke, or the
        loading screen hangs -- but the failure has to be visible."""
        manager = _manager(FailingTwoPhase(where="decode"))
        batch = manager.preload([("/x/0.img", Img)])
        _drain(manager, batch)

        assert batch.progress == 1.0
        assert len(batch.failed) == 1
        assert isinstance(batch.failed[0].error, OSError)

    def test_wait_for_blocks_until_done(self) -> None:
        loader = TwoPhaseLoader(delay=0.01)
        manager = _manager(loader)
        batch = manager.preload([(f"/x/{i}.img", Img) for i in range(4)])

        manager.wait_for(batch)

        assert batch.done
        assert manager.pending_loads == 0


@pytest.mark.unit
class TestFailures:
    def test_a_decode_failure_marks_the_request_not_the_cache(self) -> None:
        manager = _manager(FailingTwoPhase(where="decode"))
        batch = manager.preload([("/x/0.img", Img)])
        _drain(manager, batch)

        request = batch.failed[0]
        assert request.state is LoadState.FAILED
        assert isinstance(request.error, OSError)
        assert list(manager.iter_cached()) == []

    def test_an_upload_failure_is_caught_too(self) -> None:
        manager = _manager(FailingTwoPhase(where="upload"))
        batch = manager.preload([("/x/0.img", Img)])
        _drain(manager, batch)

        assert isinstance(batch.failed[0].error, RuntimeError)

    def test_a_wrong_type_from_the_loader_fails_the_request(self) -> None:
        manager = _manager(TwoPhaseLoader())
        batch = manager.preload([("/x/0.img", Other)])
        _drain(manager, batch)

        assert isinstance(batch.failed[0].error, TypeError)

    def test_one_failure_does_not_stall_the_others(self) -> None:
        manager = _manager(FailingTwoPhase(where="decode"))
        batch = manager.preload([(f"/x/{i}.img", Img) for i in range(4)])
        _drain(manager, batch)

        assert batch.done
        assert len(batch.failed) == 4


@pytest.mark.unit
class TestDecodePool:
    def test_the_pool_is_not_started_until_something_needs_it(self) -> None:
        """A game that never loads asynchronously should pay for no
        threads."""
        pool = DecodePool()
        assert not pool.started

    def test_submitting_starts_it(self) -> None:
        pool = DecodePool(max_workers=1)
        try:
            assert pool.submit(lambda: 42).result() == 42
            assert pool.started
        finally:
            pool.shutdown()

    def test_shutdown_is_idempotent(self) -> None:
        pool = DecodePool()
        pool.shutdown()
        pool.shutdown()
        assert not pool.started

    def test_a_manager_that_never_loads_async_starts_no_threads(self) -> None:
        manager = _manager(TwoPhaseLoader())
        manager.load_async("/x/0.img", Img)
        # Queued but not pumped: the decode was submitted, so the pool is up.
        # The point of the assertion is the *other* direction.
        fresh = _manager(TwoPhaseLoader())
        assert not fresh._decode_pool.started

    def test_shutdown_through_the_manager(self) -> None:
        manager = _manager(TwoPhaseLoader())
        _drain(manager, manager.preload([("/x/0.img", Img)]))
        manager.shutdown_decode_pool()
        assert not manager._decode_pool.started
