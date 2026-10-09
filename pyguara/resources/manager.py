"""
Central Asset Management System.

This module provides the `ResourceManager`, which acts as the single source
of truth for all game assets. It handles:
1. Caching (Flyweight pattern) to prevent duplicate loading.
2. Loader delegation based on file extensions (Strategy pattern).
3. Type safety validation using Generics.
4. Asset metadata via `.meta` sidecar files for import settings.
"""

import json
import os
import time
from collections import OrderedDict
from collections.abc import Iterator, Sequence
from functools import partial
from pathlib import Path
from typing import Any, TypeVar

from pyguara.common.types import Rect
from pyguara.graphics.atlas import Atlas, AtlasRegion
from pyguara.log import get_logger

from .async_load import (
    DEFAULT_PUMP_BUDGET_MS,
    Budget,
    DecodePool,
    LoadBatch,
    LoadRequest,
    LoadState,
)
from .exceptions import InvalidMetadataError, ResourceError, ResourceLoadError
from .loader import IMetaAwareLoader, IResourceLoader, ITwoPhaseLoader
from .meta import AssetMeta, MetaLoader, get_meta_loader
from .types import Resource, Texture

logger = get_logger(__name__)

# T must be a subclass of Resource (e.g., Texture)
T = TypeVar("T", bound=Resource)


class ResourceManager:
    """Orchestrate the loading, caching, and lifecycle of game resources.

    Lifecycle model:
        - ``load()`` is a cache-get. On a miss it reads from disk and caches
          the result; on a hit it returns the cached instance. Either way the
          resource sits in the cache **unpinned** (reference count 0).
        - ``acquire()`` / ``release()`` are the explicit pin API. They must be
          balanced. A ``release()`` that drops the count to 0 evicts the
          resource immediately.
        - ``unload_unused()`` evicts every resource whose count is 0. Call it
          between scenes to drop everything nothing has acquired.
        - ``unload(path, force=True)`` evicts regardless of the count.
        - ``reload()`` re-reads a cached resource from disk and swaps the
          cached instance in place, keeping the reference count.

    The ResourceManager supports asset metadata via `.meta` sidecar files.
    When loading a resource, it checks for a corresponding `.meta` file
    (e.g., `hero.png.meta` for `hero.png`) and applies import settings
    if the loader supports metadata.

    Example:
        Create `hero.png.meta`:
        ```json
        {
            "type": "texture",
            "filter": "nearest",
            "premultiply_alpha": true
        }
        ```
    """

    def __init__(self, meta_loader: MetaLoader | None = None) -> None:
        """Initialize the manager with empty cache and index.

        Args:
            meta_loader: Optional custom meta loader. If None, uses the global instance.
        """
        # An ordered dict, least-recently-used first. Insertion order is
        # already use order for a cache nothing has touched twice; `load()`
        # moves a hit to the end, which is what makes the budget's eviction
        # order mean anything.
        self._cache: OrderedDict[str, Resource] = OrderedDict()
        self._extension_map: dict[str, IResourceLoader] = {}
        self._path_index: dict[str, str] = {}
        self._reference_counts: dict[str, int] = {}
        self._meta_loader = meta_loader or get_meta_loader()

        # None means unbounded, which is the behaviour every existing
        # caller already has. A budget is opted into.
        self._cache_budget_bytes: int | None = None
        self._warned_over_budget = False

        # Asynchronous loading. The pool is lazy: a game that never calls
        # load_async() starts no threads.
        self._decode_pool = DecodePool()
        self._queue: list[LoadRequest] = []

    def register_loader(self, loader: IResourceLoader) -> None:
        """
        Register a new loader strategy into the manager.

        This method updates the internal lookup table, mapping the loader's
        supported extensions to the loader instance for O(1) access.

        Args:
            loader (IResourceLoader): The loader instance to register.
        """
        for ext in loader.supported_extensions:
            # Normalise to lowercase so "PNG" and "png" resolve alike.
            clean_ext = ext.lower()

            if clean_ext in self._extension_map:
                logger.warning("Overwriting loader for extension: %s", clean_ext)

            self._extension_map[clean_ext] = loader

    def index_directory(self, root_path: str, recursive: bool = True) -> None:
        """
        Scan a directory and maps filenames to their full paths without loading them.

        This allows requesting assets by name (e.g., 'hero') instead of full path
        (e.g., 'assets/chars/hero.png'), mimicking Godot's resource system.

        Two files that share a stem (``chars/hero.png`` and ``fx/hero.png``)
        would both claim the bare name ``hero``. That is ambiguous, so the
        bare-stem entry is dropped and a warning is logged naming both paths;
        the unambiguous full-name keys (``hero.png``) are always kept. Resolve
        the clash by loading the colliding asset via its full name or path.

        Args:
            root_path (str): The directory to scan.
            recursive (bool): If True, scans subdirectories as well.
        """
        path_obj = Path(root_path)
        if not path_obj.exists():
            logger.warning("Directory does not exist: %s", root_path)
            return

        iterator = path_obj.rglob("*") if recursive else path_obj.glob("*")

        ambiguous_stems: set[str] = set()

        for file_path in iterator:
            if file_path.is_file():
                extension = file_path.suffix.lower()
                # Only index files we know how to load
                if extension not in self._extension_map:
                    continue

                str_path = str(file_path)
                stem = file_path.stem  # e.g., 'hero' from 'hero.png'
                existing = self._path_index.get(stem)
                if existing is not None and existing != str_path:
                    logger.warning(
                        "Ambiguous asset name '%s': both '%s' and '%s' claim it; "
                        "load one by its full name or path.",
                        stem,
                        existing,
                        str_path,
                    )
                    ambiguous_stems.add(stem)
                elif stem not in ambiguous_stems:
                    self._path_index[stem] = str_path

                # The full filename is unambiguous; always index it.
                self._path_index[file_path.name] = str_path

        for stem in ambiguous_stems:
            self._path_index.pop(stem, None)

    def load(self, path_or_name: str, resource_type: type[T]) -> T:
        """
        Retrieve a resource from the cache or loads it from disk if necessary.

        This method guarantees type safety: if you request a Texture but the
        file is a Sound, it raises a TypeError immediately.

        Args:
            path_or_name (str): The full path or the indexed filename of the asset.
            resource_type (Type[T]): The expected class (e.g., Texture, AudioClip).

        Returns:
            T: The resource instance cast to the correct type.

        Raises:
            ValueError: If no loader is registered for the file extension.
            TypeError: If the loaded resource does not match `resource_type`.
            FileNotFoundError: If the file is not found on disk.
        """
        # 1. Resolve Path
        actual_path = self._path_index.get(path_or_name, path_or_name)

        # 2. Check Cache
        if actual_path in self._cache:
            res = self._cache[actual_path]
            if not isinstance(res, resource_type):
                raise TypeError(
                    f"Resource '{path_or_name}' is cached as {type(res).__name__}, "
                    f"but {resource_type.__name__} was requested."
                )
            self._cache.move_to_end(actual_path)
            return res

        # 3. Load from disk
        resource = self._load_from_disk(
            actual_path, resource_type, requested_as=path_or_name
        )

        self._cache[actual_path] = resource

        # A load is a cache-get, not an acquire: the resource enters the cache
        # unpinned (ref count 0). Callers that need it to survive
        # unload_unused() must acquire() it explicitly.
        self._reference_counts[actual_path] = 0

        # After inserting, and protecting what was just inserted: the thing
        # the caller asked for should never be the thing evicted to make
        # room for itself, however small the budget.
        self.evict_to_budget(protect=actual_path)

        return resource

    # ------------------------------------------------------------------
    # Asynchronous loading
    #
    # See `async_load.py` for why this is a thread pool plus a budgeted
    # main-thread pump rather than asyncio, and why threading is opt-in per
    # loader. The short version: image decode releases the GIL and scales
    # ~3x, JSON parsing holds it and runs 0.71x threaded.
    # ------------------------------------------------------------------

    def load_async(
        self, path_or_name: str, resource_type: type[Resource]
    ) -> LoadRequest:
        """Queue a load and return immediately.

        Nothing is read here. The caller drives progress with `pump()`,
        normally once per frame, and watches the returned request's `state`.

        A resource already in the cache yields a request that is already
        `READY`, so a caller need not special-case the hit.

        Args:
            path_or_name: The full path or the indexed filename.
            resource_type: The expected class.

        Returns:
            A `LoadRequest` to watch. Also tracked internally until it
            finishes, so dropping the reference does not cancel the load.

        Raises:
            ValueError: If no loader is registered for the extension. Raised
                here rather than deferred, since it is a programming error
                and not a runtime failure.
        """
        actual_path = self._path_index.get(path_or_name, path_or_name)
        request = LoadRequest(
            key=actual_path,
            requested_as=path_or_name,
            resource_type=resource_type,
        )

        cached = self._cache.get(actual_path)
        if cached is not None:
            if isinstance(cached, resource_type):
                request.resource = cached
                request.state = LoadState.READY
            else:
                request.error = TypeError(
                    f"Resource '{path_or_name}' is cached as "
                    f"{type(cached).__name__}, but {resource_type.__name__} "
                    f"was requested."
                )
                request.state = LoadState.FAILED
            return request

        loader = self._loader_for(actual_path)
        request._meta = self._meta_for(actual_path, loader)
        self._schedule_decode(request, loader)
        self._queue.append(request)
        return request

    def preload(self, items: Sequence[tuple[str, type[Resource]]]) -> LoadBatch:
        """Queue several loads and return a progress handle.

        What a loading screen wants: queue the scene's assets, then pump and
        read `batch.progress` until `batch.done`.

        Args:
            items: `(path_or_name, resource_type)` pairs.

        Returns:
            A `LoadBatch` over the queued requests.
        """
        return LoadBatch([self.load_async(name, rtype) for name, rtype in items])

    def pump(self, budget_ms: float = DEFAULT_PUMP_BUDGET_MS) -> int:
        """Advance queued loads, spending at most `budget_ms`.

        Call once per frame on the thread that owns the device context --
        uploads happen here. Work is started only while the budget holds,
        but a single item is never interrupted part-way, so one slow upload
        can overrun it; see `Budget`.

        Requests whose decode is still running on a worker are skipped
        without consuming budget, so a pump never blocks on a thread.

        Args:
            budget_ms: Milliseconds this call may spend. Non-positive means
                unlimited, which is what a loading screen between frames
                wants.

        Returns:
            How many requests reached a terminal state this call.
        """
        if not self._queue:
            return 0

        budget = Budget(budget_ms)
        finished = 0
        still_pending: list[LoadRequest] = []

        for request in self._queue:
            if request.done:
                continue
            if budget.spent:
                still_pending.append(request)
                continue
            if not self._advance(request):
                # Decode still in flight; costs no budget to skip.
                still_pending.append(request)
                continue
            finished += 1

        self._queue = still_pending
        return finished

    @property
    def pending_loads(self) -> int:
        """How many queued loads have not finished."""
        return sum(1 for request in self._queue if not request.done)

    def wait_for(self, batch: LoadBatch, budget_ms: float = 0.0) -> None:
        """Pump until `batch` is finished.

        For a loading screen that is not trying to keep a frame budget, and
        for tests. Blocks, so it is the one place an unlimited budget is the
        right default.

        Args:
            batch: The batch to finish.
            budget_ms: Per-pump budget; 0 (the default) means unlimited.
        """
        while not batch.done:
            if self.pump(budget_ms) == 0 and self.pending_loads:
                # Every remaining request is mid-decode on a worker. Yield
                # rather than spin: the GIL is better spent on the decode.
                time.sleep(0.001)

    def shutdown_decode_pool(self, wait: bool = True) -> None:
        """Stop the decode pool, if one was started.

        Args:
            wait: Let in-flight decodes finish. A decode holds no device
                state, so this is cheap.
        """
        self._decode_pool.shutdown(wait=wait)

    def _schedule_decode(self, request: LoadRequest, loader: IResourceLoader) -> None:
        """Put a request's decode on a worker, or defer it to the pump.

        Args:
            request: The request to schedule.
            loader: Its loader.
        """
        if isinstance(loader, ITwoPhaseLoader):
            decode = partial(loader.decode, request.key, request._meta)
            if loader.threaded_decode:
                request._future = self._decode_pool.submit(decode)
            else:
                # Two-phase but GIL-bound: still worth splitting, because
                # the pump can then do the decode and the upload in
                # different frames rather than both in one.
                request._inline_decode = decode
            return

        # A single-phase loader cannot be split, so the whole thing runs on
        # the main thread during a pump. The gain is the spread across
        # frames, not parallelism -- which for a GIL-holding loader is the
        # only gain available anyway.
        request._inline_decode = partial(
            self._load_from_disk,
            request.key,
            request.resource_type,
            request.requested_as,
        )

    def _advance(self, request: LoadRequest) -> bool:
        """Move one request forward as far as it can go now.

        Args:
            request: The request to advance.

        Returns:
            True if it reached a terminal state, False if it is waiting on
            a worker.
        """
        try:
            if request._future is not None:
                if not request._future.done():
                    return False
                request._decoded = request._future.result()
                request._future = None
                request.state = LoadState.DECODED
            elif request._inline_decode is not None:
                request._decoded = request._inline_decode()
                request._inline_decode = None
                request.state = LoadState.DECODED

            self._finish(request)
        except Exception as e:
            request.error = e
            request.state = LoadState.FAILED
            logger.error("Async load failed for '%s': %s", request.requested_as, e)
        return True

    def _finish(self, request: LoadRequest) -> None:
        """Upload a decoded payload, type-check it, and cache it.

        Runs on the pumping thread, which is the one that owns the device
        context.

        Args:
            request: A request whose decode has completed.

        Raises:
            TypeError: If the result is not the requested type.
        """
        decoded = request._decoded
        loader = self._loader_for(request.key)

        if isinstance(loader, ITwoPhaseLoader):
            resource = loader.upload(request.key, decoded, request._meta)
            resource.import_meta = request._meta
        else:
            # A single-phase loader's "decode" already produced the
            # finished, type-checked resource.
            resource = decoded  # type: ignore[assignment]

        if not isinstance(resource, request.resource_type):
            raise TypeError(
                f"Loader for '{request.requested_as}' returned "
                f"{type(resource).__name__}, expected "
                f"{request.resource_type.__name__}."
            )

        self._cache[request.key] = resource
        # Same lifecycle as load(): enters unpinned, as a cache-get.
        self._reference_counts.setdefault(request.key, 0)
        request.resource = resource
        request.state = LoadState.READY

    def _loader_for(self, actual_path: str) -> IResourceLoader:
        """Return the loader registered for a path's extension.

        Args:
            actual_path: The resolved filesystem path.

        Returns:
            The loader.

        Raises:
            ValueError: If no loader handles the extension.
        """
        extension = os.path.splitext(actual_path)[1].lower()
        loader = self._extension_map.get(extension)
        if not loader:
            raise ValueError(f"No loader registered for extension: {extension}")
        return loader

    def _meta_for(self, actual_path: str, loader: IResourceLoader) -> AssetMeta | None:
        """Load a path's sidecar metadata, if its loader uses metadata.

        Args:
            actual_path: The resolved filesystem path.
            loader: The loader for it.

        Returns:
            The metadata, or None.
        """
        if isinstance(loader, IMetaAwareLoader | ITwoPhaseLoader):
            return self._meta_loader.load_meta(actual_path)
        return None

    def _load_from_disk(
        self,
        actual_path: str,
        resource_type: type[T],
        requested_as: str | None = None,
    ) -> T:
        """Run the registered loader for a path and type-check the result.

        Shared by load() (cache miss) and reload(). Does not touch the cache
        or the reference counts.

        Args:
            actual_path: The resolved filesystem path.
            resource_type: The expected class.
            requested_as: The name the caller asked for, for error context.

        Returns:
            The freshly loaded resource.

        Raises:
            ValueError: If no loader is registered for the file extension.
            TypeError: If the loader returns the wrong type.
            ResourceLoadError: If the loader itself fails. The original
                exception is chained, so nothing is hidden.
        """
        extension = os.path.splitext(actual_path)[1].lower()
        loader = self._extension_map.get(extension)

        if not loader:
            raise ValueError(f"No loader registered for extension: {extension}")

        logger.debug("Loading resource: %s", actual_path)

        # Check for meta-aware loader and load metadata
        meta = None
        try:
            if isinstance(loader, IMetaAwareLoader):
                meta = self._meta_loader.load_meta(actual_path)
                if meta:
                    logger.debug("Applying meta settings for '%s'", actual_path)
                resource = loader.load_with_meta(actual_path, meta)
            else:
                resource = loader.load(actual_path)
        except ResourceError:
            # Already carries its own context -- re-wrapping would bury it.
            raise
        except Exception as e:
            # A loader's own `FileNotFoundError` or `pygame.error` names
            # neither the asset the caller asked for nor, clearly, the path
            # the index resolved it to. `load_atlas()` already wrapped its
            # failures this way; this is the same for every other loader.
            raise ResourceLoadError(
                actual_path, f"{type(e).__name__}: {e}", name=requested_as
            ) from e

        if not isinstance(resource, resource_type):
            raise TypeError(
                f"Loader for {extension} returned {type(resource).__name__}, "
                f"expected {resource_type.__name__}."
            )

        # Record the resolved import settings on the resource so systems that
        # need them post-load can read resource.import_meta.
        resource.import_meta = meta

        return resource

    def reload(self, path_or_name: str) -> Resource:
        """Re-read a cached resource from disk and swap it in place.

        Runs the registered loader again (re-reading the `.meta` sidecar too,
        if the loader is meta-aware) and replaces the cached instance. The
        reference count is preserved, so anything that acquired the resource
        keeps its hold.

        Note:
            Callers that already hold a reference to the *previous* instance
            keep that stale object -- ``reload()`` swaps the cache entry, it
            does not mutate the old instance. Re-``load()`` after a reload to
            pick up the new one. This is what a hot-reload watcher does.

        Args:
            path_or_name: The full path or indexed filename of the asset.

        Returns:
            The freshly loaded resource now in the cache.

        Raises:
            KeyError: If the resource is not currently cached.
            ValueError: If no loader is registered for the file extension.
            TypeError: If the file now loads as a different type than the
                cached instance.
        """
        actual_path = self._path_index.get(path_or_name, path_or_name)

        if actual_path not in self._cache:
            raise KeyError(
                f"Cannot reload a resource that is not loaded: {path_or_name}"
            )

        old_type = type(self._cache[actual_path])
        # Drop any cached .meta so import settings changed on disk take effect.
        self._meta_loader.invalidate(actual_path)
        resource = self._load_from_disk(actual_path, old_type)

        self._cache[actual_path] = resource
        logger.debug("Reloaded resource: %s", actual_path)
        return resource

    def acquire(self, path_or_name: str) -> None:
        """
        Increment the reference count for a resource.

        Use this when you want to explicitly hold a reference to prevent
        automatic unloading. Must be balanced with release() calls.

        Args:
            path_or_name (str): The identifier used to load the resource.

        Raises:
            KeyError: If the resource is not loaded in cache.
        """
        actual_path = self._path_index.get(path_or_name, path_or_name)

        if actual_path not in self._cache:
            raise KeyError(
                f"Cannot acquire reference to unloaded resource: {path_or_name}"
            )

        if actual_path not in self._reference_counts:
            self._reference_counts[actual_path] = 0

        self._reference_counts[actual_path] += 1

    def release(self, path_or_name: str) -> None:
        """
        Decrement the reference count for a resource.

        When the reference count reaches zero, the resource is automatically
        unloaded from the cache to free memory.

        Args:
            path_or_name (str): The identifier used to load the resource.

        Raises:
            KeyError: If the resource is not loaded in cache.
            ValueError: If reference count is already zero.
        """
        actual_path = self._path_index.get(path_or_name, path_or_name)

        if actual_path not in self._cache:
            raise KeyError(
                f"Cannot release reference to unloaded resource: {path_or_name}"
            )

        if (
            actual_path not in self._reference_counts
            or self._reference_counts[actual_path] <= 0
        ):
            raise ValueError(
                f"Reference count for {path_or_name} is already zero. "
                "Cannot release more references than acquired."
            )

        self._reference_counts[actual_path] -= 1

        # Auto-unload when ref count reaches zero
        if self._reference_counts[actual_path] == 0:
            del self._cache[actual_path]
            del self._reference_counts[actual_path]
            logger.debug("Auto-unloaded resource (ref count 0): %s", actual_path)

    def unload(self, path_or_name: str, force: bool = False) -> None:
        """
        Remove a resource from the cache, allowing the garbage collector to free memory.

        By default, this decrements the reference count and only removes the resource
        when the count reaches zero. Use force=True to bypass reference counting.

        Args:
            path_or_name (str): The identifier used to load the resource.
            force (bool): If True, unload regardless of reference count. Use with caution.
        """
        actual_path = self._path_index.get(path_or_name, path_or_name)

        if actual_path not in self._cache:
            return  # Already unloaded

        if force:
            # Force unload regardless of ref count
            if actual_path in self._cache:
                del self._cache[actual_path]
            if actual_path in self._reference_counts:
                del self._reference_counts[actual_path]
            logger.debug("Force unloaded resource: %s", actual_path)
        else:
            # Respect reference counting (same as release())
            if (
                actual_path not in self._reference_counts
                or self._reference_counts[actual_path] <= 0
            ):
                # No references, safe to unload
                del self._cache[actual_path]
                if actual_path in self._reference_counts:
                    del self._reference_counts[actual_path]
                logger.debug("Unloaded resource: %s", actual_path)
            else:
                # Has references, just decrement
                self._reference_counts[actual_path] -= 1
                if self._reference_counts[actual_path] == 0:
                    del self._cache[actual_path]
                    del self._reference_counts[actual_path]
                    logger.debug("Unloaded resource (ref count 0): %s", actual_path)
                else:
                    logger.debug(
                        "Decremented ref count for %s (now %d)",
                        actual_path,
                        self._reference_counts[actual_path],
                    )

    def unload_unused(self) -> int:
        """
        Batch-unload all resources with zero reference count.

        This is useful for cleanup between scenes or game states.

        Returns:
            int: The number of resources unloaded.
        """
        to_unload = [
            path for path, count in self._reference_counts.items() if count == 0
        ]

        for path in to_unload:
            if path in self._cache:
                del self._cache[path]
            del self._reference_counts[path]
            logger.debug("Batch unloaded resource: %s", path)

        return len(to_unload)

    # ------------------------------------------------------------------
    # Cache budget
    # ------------------------------------------------------------------

    @property
    def cache_budget_bytes(self) -> int | None:
        """The cache's size ceiling, or None for unbounded."""
        return self._cache_budget_bytes

    def set_cache_budget(self, budget_bytes: int | None) -> int:
        """Cap the cache's estimated size, evicting least-recently-used first.

        `unload_unused()` is all-or-nothing and manual, so a long run that
        visits many floors accumulates every texture it ever touched until
        something thinks to call it. A budget makes the ceiling a property
        of the manager instead of a thing every scene must remember.

        Enforced after each load and whenever this is set, so a game sets
        it once at startup and never calls it again.

        **A pinned resource is never evicted**, whatever the budget says.
        `acquire()` means "I am using this"; a cache that evicted it anyway
        would hand the next `load()` a second instance while the first is
        still being drawn. A budget smaller than what is pinned is
        therefore exceeded, and said so once rather than every frame.

        Args:
            budget_bytes: The ceiling in bytes, or None for unbounded.
                Compared against `Resource.size_bytes`, which is an
                estimate -- see that property.

        Returns:
            How many resources this call evicted.

        Raises:
            ValueError: If the budget is negative. Zero is legal and means
                "keep nothing unpinned", which is a real thing to want
                between levels.
        """
        if budget_bytes is not None and budget_bytes < 0:
            raise ValueError(
                f"Cache budget must not be negative, got {budget_bytes}. Pass "
                f"None for unbounded."
            )
        self._cache_budget_bytes = budget_bytes
        return self.evict_to_budget()

    def cache_size_bytes(self) -> int:
        """Estimated total size of everything currently cached.

        Resources reporting 0 from `size_bytes` -- the ones that cannot
        estimate -- contribute nothing, so this undercounts rather than
        guessing. In practice it is a texture figure, which is where the
        memory is.

        Returns:
            Bytes.
        """
        return sum(resource.size_bytes for resource in self._cache.values())

    def evict_to_budget(self, protect: str | None = None) -> int:
        """Evict unpinned resources, oldest first, until under budget.

        Args:
            protect: A resolved path to leave alone whatever the budget
                says. `load()` passes the resource it has just produced:
                returning it and evicting it in the same call would hand
                the caller an object the cache no longer has, and the next
                `load()` of the same path a *second* instance of it.

        Returns:
            How many resources were evicted. Zero when no budget is set.
        """
        if self._cache_budget_bytes is None:
            return 0

        total = self.cache_size_bytes()
        if total <= self._cache_budget_bytes:
            return 0

        evicted = 0
        for path in list(self._cache):
            if total <= self._cache_budget_bytes:
                break
            if path == protect:
                continue
            if self._reference_counts.get(path, 0) > 0:
                continue
            size = self._cache[path].size_bytes
            if size <= 0:
                # Evicting something of unknown size frees an unknown
                # amount, which is not a step towards a target. Left alone
                # rather than thrown away for no measurable gain.
                continue
            del self._cache[path]
            self._reference_counts.pop(path, None)
            total -= size
            evicted += 1
            logger.debug("Evicted to stay under cache budget: %s", path)

        if total > self._cache_budget_bytes and not self._warned_over_budget:
            self._warned_over_budget = True
            logger.warning(
                "Resource cache is %d bytes against a %d byte budget and "
                "cannot shrink further: everything over it is either pinned "
                "by acquire() or of unknown size. Reported once.",
                total,
                self._cache_budget_bytes,
            )

        return evicted

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get statistics about the current resource cache state.

        Returns:
            A dict with ``resource_count`` (int), ``total_references`` (int),
            ``total_bytes`` (int, the estimate the budget counts),
            ``budget_bytes`` (int or None) and ``resources`` (a
            ``{path: {"type": str, "ref_count": int, "size_bytes": int}}``
            mapping).
        """
        total_refs = sum(self._reference_counts.values())
        resources_info = {
            path: {
                "type": type(res).__name__,
                "ref_count": self._reference_counts.get(path, 0),
                "size_bytes": res.size_bytes,
            }
            for path, res in self._cache.items()
        }

        return {
            "resource_count": len(self._cache),
            "total_references": total_refs,
            "total_bytes": self.cache_size_bytes(),
            "budget_bytes": self._cache_budget_bytes,
            "resources": resources_info,
        }

    def iter_indexed(self) -> Iterator[tuple[str, str]]:
        """Yield `(name, path)` for every asset `index_directory()` has mapped.

        A read-only view for tooling such as an asset browser. `name` is the
        lookup key -- a bare stem (`hero`) or a full filename (`hero.png`) --
        and `path` its resolved location on disk. Iterates a snapshot.
        """
        yield from list(self._path_index.items())

    def iter_cached(self) -> Iterator[tuple[str, Resource]]:
        """Yield `(path, resource)` for every currently loaded resource.

        A read-only view for tooling; unlike `get_cache_stats()` this hands
        back the live resource objects. Iterates a snapshot, so a caller may
        load or unload while iterating.
        """
        yield from list(self._cache.items())

    def load_atlas(self, atlas_path: str, metadata_path: str) -> Atlas:
        """
        Load a sprite atlas with its metadata.

        This method loads both the atlas texture and its JSON metadata file,
        parsing the sprite regions and creating an Atlas object for convenient
        access to packed sprites.

        Args:
            atlas_path (str): Path to the atlas texture image.
            metadata_path (str): Path to the JSON metadata file.

        Returns:
            Atlas: The loaded atlas with all sprite regions.

        Raises:
            ResourceLoadError: If the atlas texture fails to load.
            InvalidMetadataError: If the metadata file is missing, malformed,
                or has an invalid structure. Includes line/column info for
                JSON parsing errors.

        Example:
            atlas = resource_manager.load_atlas(
                "assets/atlas/characters.png",
                "assets/atlas/characters.json"
            )
            region = atlas.get_region("player_idle")
        """
        # Check metadata file exists first (fail fast)
        metadata_file = Path(metadata_path)
        if not metadata_file.exists():
            raise InvalidMetadataError(metadata_path, "File not found")

        # Load and parse the metadata JSON with detailed error reporting
        try:
            with open(metadata_file) as f:
                metadata = json.load(f)
        except json.JSONDecodeError as e:
            raise InvalidMetadataError(
                metadata_path,
                f"JSON parsing failed: {e.msg}",
                line=e.lineno,
                column=e.colno,
            ) from e

        # Validate metadata structure
        if "regions" not in metadata:
            raise InvalidMetadataError(
                metadata_path,
                "Missing required 'regions' key",
            )

        # Load the atlas texture using existing infrastructure
        try:
            texture = self.load(atlas_path, Texture)  # type: ignore[type-abstract]
        except Exception as e:
            raise ResourceLoadError(atlas_path, str(e)) from e

        # Parse regions from metadata with detailed error reporting
        regions: dict[str, AtlasRegion] = {}
        for name, region_data in metadata["regions"].items():
            try:
                # Extract region properties
                x = region_data["x"]
                y = region_data["y"]
                width = region_data["width"]
                height = region_data["height"]
                original_size = tuple(region_data["original_size"])

                # Create region object
                rect = Rect(x, y, width, height)
                region = AtlasRegion(name=name, rect=rect, original_size=original_size)
                regions[name] = region
            except KeyError as e:
                raise InvalidMetadataError(
                    metadata_path,
                    f"Region '{name}' is missing required field: {e}",
                ) from e
            except (TypeError, ValueError) as e:
                raise InvalidMetadataError(
                    metadata_path,
                    f"Region '{name}' has invalid data: {e}",
                ) from e

        # The Atlas holds the texture for its whole lifetime; pin it so
        # unload_unused() cannot pull it out from under the atlas. Drop it
        # with unload(atlas_path, force=True) when the atlas is finished.
        self.acquire(atlas_path)

        # Create and return the atlas
        atlas = Atlas(texture=texture, regions=regions)

        logger.debug("Loaded atlas '%s' with %d regions", atlas_path, len(regions))

        return atlas
