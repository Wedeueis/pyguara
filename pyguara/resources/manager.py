"""Central Asset Management System.

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
from collections.abc import Callable, Iterator, Sequence
from functools import partial
from pathlib import Path
from typing import Any, TypeVar

from pyguara import assets
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

    - ``load()`` is a cache-get, leaving the resource unpinned (count 0).
    - ``acquire()`` and ``release()`` pin and unpin, and must be balanced.
    - ``unload_unused()`` evicts every resource whose count is 0, and
      ``unload(path, force=True)`` evicts regardless of the count.
    - What loads during a load is a dependency: kept while a dependent is
      cached, except by ``force``, and ``reload()`` rebuilds its dependents.

    Example:
        A `.meta` sidecar (`hero.png.meta` for `hero.png`) supplies import
        settings to a loader that supports metadata:
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

        # The dependency graph, both directions, by resolved key. Edges are
        # recorded while a resource loads: whatever it loads in the
        # meantime, it depends on. `_loading` is the stack of keys whose
        # loader or builder is running.
        self._dependencies: dict[str, set[str]] = {}
        self._dependents: dict[str, set[str]] = {}
        self._loading: list[str] = []
        self._builders: dict[str, Callable[[], Resource]] = {}

        # None means unbounded, which is the behaviour every existing
        # caller already has. A budget is opted into.
        self._cache_budget_bytes: int | None = None
        self._warned_over_budget = False

        # Asynchronous loading. The pool is lazy: a game that never calls
        # load_async() starts no threads.
        self._decode_pool = DecodePool()
        self._queue: list[LoadRequest] = []

    def register_loader(self, loader: IResourceLoader) -> None:
        """Register a new loader strategy into the manager.

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
        """Scan a directory and maps filenames to their full paths without loading them.

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
        if not assets.is_dir(root_path):
            logger.warning("Directory does not exist: %s", root_path)
            return

        ambiguous_stems: set[str] = set()

        # Through the asset layer: a mounted pack's files are indexed under
        # the same paths they would have on disk.
        for listed in assets.files_under(root_path, recursive=recursive):
            file_path = Path(listed)
            # Only index files we know how to load
            if self._match_loader(file_path.name) is None:
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
        """Retrieve a resource from the cache or loads it from disk if necessary.

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
            self._record_dependency(actual_path)
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
        self._record_dependency(actual_path)

        return resource

    def build(
        self, key: str, resource_type: type[T], builder: Callable[[], Resource]
    ) -> T:
        """Cache a resource assembled from others, rebuilt when one reloads.

        On a miss `builder` runs, and every resource it loads becomes a
        dependency of `key`. On a hit it does not run. The result is
        cached unpinned, like a `load()`.

        Args:
            key: The cache key to keep it under.
            resource_type: The class it must be.
            builder: Makes it, loading what it needs through this manager.

        Returns:
            The cached or newly built resource.

        Raises:
            TypeError: If the cached or built resource is not `resource_type`.
        """
        if key in self._cache:
            cached = self._cache[key]
            if not isinstance(cached, resource_type):
                raise TypeError(
                    f"Resource '{key}' is cached as {type(cached).__name__}, "
                    f"but {resource_type.__name__} was requested."
                )
            self._cache.move_to_end(key)
            self._record_dependency(key)
            return cached

        resource = self._run_builder(key, builder, resource_type)
        self._builders[key] = builder
        self._cache[key] = resource
        self._reference_counts[key] = 0
        self.evict_to_budget(protect=key)
        self._record_dependency(key)
        return resource

    def dependencies_of(self, path_or_name: str) -> list[str]:
        """Return the keys a resource loaded while it loaded, sorted."""
        key = self._path_index.get(path_or_name, path_or_name)
        return sorted(self._dependencies.get(key, ()))

    def dependents_of(self, path_or_name: str) -> list[str]:
        """Return every cached resource built on this one, in reload order.

        Direct and indirect dependents, each after everything it depends on
        in the list, which is the order `reload()` rebuilds them in.
        """
        key = self._path_index.get(path_or_name, path_or_name)
        order: list[str] = []
        seen = {key}

        def visit(node: str) -> None:
            for dependent in sorted(self._dependents.get(node, ())):
                if dependent not in seen and dependent in self._cache:
                    seen.add(dependent)
                    visit(dependent)
                    order.append(dependent)

        visit(key)
        order.reverse()
        return order

    def _record_dependency(self, key: str) -> None:
        """Note that the resource now loading depends on `key`."""
        if self._loading and self._loading[-1] != key:
            dependent = self._loading[-1]
            self._dependencies.setdefault(dependent, set()).add(key)
            self._dependents.setdefault(key, set()).add(dependent)

    def _forget_dependencies(self, key: str) -> set[str]:
        """Drop the edges from `key` to what it depends on, returning them."""
        dependencies = self._dependencies.pop(key, set())
        for dependency in dependencies:
            dependents = self._dependents.get(dependency)
            if dependents is not None:
                dependents.discard(key)
                if not dependents:
                    del self._dependents[dependency]
        return dependencies

    def _restore_dependencies(self, key: str, dependencies: set[str]) -> None:
        """Put back edges `_forget_dependencies` removed."""
        self._forget_dependencies(key)
        if dependencies:
            self._dependencies[key] = set(dependencies)
            for dependency in dependencies:
                self._dependents.setdefault(dependency, set()).add(key)

    def _has_cached_dependent(self, key: str) -> bool:
        """Whether a cached resource depends on `key`."""
        return any(d in self._cache for d in self._dependents.get(key, ()))

    def _enter_loading(self, key: str, requested_as: str | None) -> None:
        """Push `key` onto the loading stack, refusing a cycle.

        Raises:
            ResourceLoadError: If `key` is already loading further down.
        """
        if key in self._loading:
            cycle = self._loading[self._loading.index(key) :] + [key]
            raise ResourceLoadError(
                key, "depends on itself: " + " -> ".join(cycle), name=requested_as
            )
        self._loading.append(key)

    def _run_builder(
        self, key: str, builder: Callable[[], Resource], resource_type: type[T]
    ) -> T:
        """Run a builder with `key` loading, and type-check its result.

        Raises:
            TypeError: If the builder returns the wrong type.
        """
        self._enter_loading(key, None)
        try:
            resource = builder()
        except BaseException:
            self._forget_dependencies(key)
            raise
        finally:
            self._loading.pop()
        if not isinstance(resource, resource_type):
            self._forget_dependencies(key)
            raise TypeError(
                f"The builder for '{key}' returned {type(resource).__name__}, "
                f"expected {resource_type.__name__}."
            )
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
                # Same as the hit in `load()`: a hit is a use, and the
                # budget's eviction order is only meaningful if uses
                # refresh it. Without this, anything reached only through
                # `load_async()` kept its original rank forever and was
                # evicted as though it had never been touched.
                self._cache.move_to_end(actual_path)
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

        # And the same budget enforcement, protecting what just arrived --
        # a resource should never be evicted to make room for itself. This
        # was missing, so a game that loaded everything through
        # `preload()` / `load_async()` had a cache budget that was never
        # applied at all.
        self.evict_to_budget(protect=request.key)

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
        loader = self._match_loader(actual_path)
        if loader is None:
            extension = os.path.splitext(actual_path)[1].lower()
            raise ValueError(f"No loader registered for extension: {extension}")
        return loader

    def _match_loader(self, path: str) -> IResourceLoader | None:
        """Return the loader for the longest registered suffix of a file name.

        `goblin.prefab.json` goes to a `.prefab.json` loader before a
        `.json` one, whichever was registered first.
        """
        name = os.path.basename(path).lower()
        start = name.find(".", 1)
        while start != -1:
            loader = self._extension_map.get(name[start:])
            if loader is not None:
                return loader
            start = name.find(".", start + 1)
        return None

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
            ResourceError: If the loader fails; a loader's own error is wrapped
                in `ResourceLoadError`.
        """
        loader = self._loader_for(actual_path)
        extension = os.path.splitext(actual_path)[1].lower()

        logger.debug("Loading resource: %s", actual_path)

        # Check for meta-aware loader and load metadata
        meta = None
        self._enter_loading(actual_path, requested_as)
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
            self._forget_unless_cached(actual_path)
            raise
        except Exception as e:
            self._forget_unless_cached(actual_path)
            # A loader's own `FileNotFoundError` or `pygame.error` names
            # neither the asset the caller asked for nor, clearly, the path
            # the index resolved it to. `load_atlas()` already wrapped its
            # failures this way; this is the same for every other loader.
            raise ResourceLoadError(
                actual_path, f"{type(e).__name__}: {e}", name=requested_as
            ) from e
        finally:
            self._loading.pop()

        if not isinstance(resource, resource_type):
            self._forget_unless_cached(actual_path)
            raise TypeError(
                f"Loader for {extension} returned {type(resource).__name__}, "
                f"expected {resource_type.__name__}."
            )

        # Record the resolved import settings on the resource so systems that
        # need them post-load can read resource.import_meta.
        resource.import_meta = meta

        return resource

    def _forget_unless_cached(self, key: str) -> None:
        """Drop a failed first load's edges; a failed reload's are restored."""
        if key not in self._cache:
            self._forget_dependencies(key)

    def reload(self, path_or_name: str) -> Resource:
        """Re-read a cached resource, then rebuild everything that depends on it.

        Runs the loader again (re-reading a meta-aware loader's `.meta`
        sidecar) and swaps the cached instance, keeping its reference count.
        Then each cached dependent is reloaded, in `dependents_of` order. An
        old instance is not mutated: its holder must `load()` again.

        Args:
            path_or_name: The full path or indexed filename of the asset.

        Returns:
            The freshly loaded resource now in the cache.

        Raises:
            KeyError: If the resource is not currently cached.
            ValueError: If no loader is registered for the file extension.
            TypeError: If the file now loads as a different type than the
                cached instance.
            ResourceLoadError: If it or a dependent fails to load. Whatever
                reloaded before the failure stays reloaded.
        """
        actual_path = self._path_index.get(path_or_name, path_or_name)

        if actual_path not in self._cache:
            raise KeyError(
                f"Cannot reload a resource that is not loaded: {path_or_name}"
            )

        dependents = self.dependents_of(actual_path)
        resource = self._reload_one(actual_path)
        for dependent in dependents:
            if dependent in self._cache:
                self._reload_one(dependent)
        return resource

    def _reload_one(self, key: str) -> Resource:
        """Reload one cached resource, re-recording what it depends on."""
        old_type = type(self._cache[key])
        # Drop any cached .meta so import settings changed on disk take effect.
        self._meta_loader.invalidate(key)
        previous = self._forget_dependencies(key)
        try:
            builder = self._builders.get(key)
            if builder is not None:
                resource: Resource = self._run_builder(key, builder, old_type)
            else:
                resource = self._load_from_disk(key, old_type)
        except BaseException:
            self._restore_dependencies(key, previous)
            raise

        # Released, not merely overwritten: the old instance may hold a
        # driver allocation. The reference count survives, because callers
        # that acquired the old instance still hold a claim on the key.
        self._evict_entry(key, drop_refcount=False)

        self._cache[key] = resource
        logger.debug("Reloaded resource: %s", key)
        return resource

    def acquire(self, path_or_name: str) -> None:
        """Increment the reference count for a resource.

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

    def _evict_entry(self, key: str, *, drop_refcount: bool = True) -> None:
        """Drop one cache entry, releasing whatever it holds first.

        Every eviction path goes through here. `del self._cache[key]` on its
        own frees only the Python object: a `GLTexture` owns a
        `moderngl.Texture` in VRAM that the garbage collector cannot see, so
        dropping the reference without releasing it orphaned the allocation
        for the life of the process. `size_bytes` counts that memory towards
        the cache budget, so `evict_to_budget` was evicting to reclaim
        memory it never actually reclaimed.

        Args:
            key: The resolved cache key to evict. Absent keys are ignored,
                so a caller need not check first.
            drop_refcount: Also forget the reference count. False where the
                caller is replacing the entry rather than retiring it, as
                `reload()` does.
        """
        resource = self._cache.pop(key, None)
        if resource is not None:
            try:
                resource.release()
            except Exception as exc:
                # An eviction that cannot free its driver handle is worth
                # knowing about, but it must not leave the entry in the
                # cache or abort the caller's unload.
                logger.error(
                    "Releasing resource failed, evicting anyway: %s (%s)", key, exc
                )

        if drop_refcount:
            self._reference_counts.pop(key, None)
            self._forget_dependencies(key)
            self._builders.pop(key, None)

    def release(self, path_or_name: str) -> None:
        """Decrement the reference count for a resource.

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

        # Auto-unload when ref count reaches zero, unless a cached resource
        # is built on it.
        if self._reference_counts[actual_path] == 0 and not self._has_cached_dependent(
            actual_path
        ):
            self._evict_entry(actual_path)
            logger.debug("Auto-unloaded resource (ref count 0): %s", actual_path)

    def unload(self, path_or_name: str, force: bool = False) -> None:
        """Drop a reference to a resource, evicting it when none are left.

        Without `force`, one reference is dropped, and the resource is
        evicted once it has none and no cached resource depends on it. With
        `force`, it is evicted regardless.

        Args:
            path_or_name (str): The identifier used to load the resource.
            force (bool): If True, unload regardless of reference count. Use with caution.
        """
        actual_path = self._path_index.get(path_or_name, path_or_name)

        if actual_path not in self._cache:
            return  # Already unloaded

        if force:
            self._evict_entry(actual_path)
            logger.debug("Force unloaded resource: %s", actual_path)
            return

        if self._reference_counts.get(actual_path, 0) > 0:
            self._reference_counts[actual_path] -= 1
        if self._reference_counts.get(actual_path, 0) > 0:
            logger.debug(
                "Decremented ref count for %s (now %d)",
                actual_path,
                self._reference_counts[actual_path],
            )
        elif self._has_cached_dependent(actual_path):
            logger.debug("Kept %s: a cached resource depends on it", actual_path)
        else:
            self._evict_entry(actual_path)
            logger.debug("Unloaded resource: %s", actual_path)

    def unload_unused(self) -> int:
        """Evict every resource with no references and no cached dependent.

        A dependency whose last dependent this evicts goes too. Useful for
        cleanup between scenes or game states.

        Returns:
            int: The number of resources unloaded.
        """
        unloaded = 0
        while True:
            to_unload = [
                path
                for path in self._cache
                if self._reference_counts.get(path, 0) == 0
                and not self._has_cached_dependent(path)
            ]
            if not to_unload:
                return unloaded
            for path in to_unload:
                self._evict_entry(path)
                logger.debug("Batch unloaded resource: %s", path)
            unloaded += len(to_unload)

    # ------------------------------------------------------------------
    # Cache budget
    # ------------------------------------------------------------------

    @property
    def cache_budget_bytes(self) -> int | None:
        """The cache's size ceiling, or None for unbounded."""
        return self._cache_budget_bytes

    def set_cache_budget(self, budget_bytes: int | None) -> int:
        """Cap the cache's estimated size, evicting least-recently-used first.

        Enforced after each load and whenever this is set, so a game sets it
        once at startup.

        A pinned resource is never evicted, whatever the budget. A budget
        smaller than what is pinned is exceeded, and that is logged once.

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
            if self._has_cached_dependent(path):
                continue
            size = self._cache[path].size_bytes
            if size <= 0:
                # Evicting something of unknown size frees an unknown
                # amount, which is not a step towards a target. Left alone
                # rather than thrown away for no measurable gain.
                continue
            self._evict_entry(path)
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
        """Get statistics about the current resource cache state.

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
        """Load a sprite atlas with its metadata.

        The atlas is cached under `metadata_path`, as a dependent of its page
        textures: they stay loaded while it is cached, and reloading one
        rebuilds it. Each call pins it; drop each with `unload(metadata_path)`. An atlas of several pages names the other pages' images
        in its metadata, and they are loaded from beside `atlas_path`.

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
        key = self._path_index.get(metadata_path, metadata_path)
        atlas = self.build(key, Atlas, partial(self._read_atlas, atlas_path, key))
        self.acquire(key)
        return atlas

    def _read_atlas(self, atlas_path: str, metadata_path: str) -> Atlas:
        """Read an atlas's region map and load its pages.

        Raises:
            InvalidMetadataError: If the region map is missing or malformed.
            ResourceLoadError: If a page fails to load.
        """
        # Check metadata file exists first (fail fast)
        if not assets.is_file(metadata_path):
            raise InvalidMetadataError(metadata_path, "File not found")

        # Load and parse the metadata JSON with detailed error reporting
        try:
            metadata = json.loads(assets.read_text(metadata_path))
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

        page_paths = _atlas_page_paths(atlas_path, metadata_path, metadata)

        # Parse regions from metadata with detailed error reporting
        regions: dict[str, AtlasRegion] = {}
        for name, region_data in metadata["regions"].items():
            try:
                region = AtlasRegion(
                    name=name,
                    rect=Rect(
                        region_data["x"],
                        region_data["y"],
                        region_data["width"],
                        region_data["height"],
                    ),
                    original_size=_int_pair(region_data["original_size"]),
                    offset=_int_pair(region_data.get("offset", (0, 0))),
                    page=int(region_data.get("page", 0)),
                )
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
            if not 0 <= region.page < len(page_paths):
                raise InvalidMetadataError(
                    metadata_path,
                    f"Region '{name}' is on page {region.page}, but the atlas "
                    f"has {len(page_paths)}",
                )
            regions[name] = region

        # Load the page textures using existing infrastructure
        pages: list[Texture] = []
        for page_path in page_paths:
            try:
                pages.append(self.load(page_path, Texture))  # type: ignore[type-abstract]
            except Exception as e:
                raise ResourceLoadError(page_path, str(e)) from e

        atlas = Atlas(
            texture=pages[0], regions=regions, pages=pages, path=metadata_path
        )

        logger.debug("Loaded atlas '%s' with %d regions", atlas_path, len(regions))

        return atlas


def _int_pair(value: Any) -> tuple[int, int]:
    """Read a two-number list from atlas metadata, as integers."""
    first, second = value
    return int(first), int(second)


def _atlas_page_paths(
    atlas_path: str, metadata_path: str, metadata: dict[str, Any]
) -> list[str]:
    """Return every page's image path, `atlas_path` first.

    A later page's file is named in the metadata and lives beside
    `atlas_path`. A name that could reach anywhere else is refused.

    Raises:
        InvalidMetadataError: If `pages` is malformed or names a path.
    """
    pages = metadata.get("pages")
    if pages is None:
        return [atlas_path]
    if not isinstance(pages, list) or not pages:
        raise InvalidMetadataError(metadata_path, "'pages' must be a non-empty list")
    folder = os.path.dirname(atlas_path)
    paths = [atlas_path]
    for index, page in enumerate(pages[1:], start=1):
        image = page.get("image") if isinstance(page, dict) else None
        if (
            not isinstance(image, str)
            or not image
            or image != os.path.basename(image)
            or "/" in image
            or "\\" in image
            or image in (".", "..")
        ):
            raise InvalidMetadataError(
                metadata_path,
                f"Page {index} must name an image file beside the atlas, not {image!r}",
            )
        paths.append(os.path.join(folder, image))
    return paths
