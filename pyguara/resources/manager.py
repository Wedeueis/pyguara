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
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TypeVar

from pyguara.common.types import Rect
from pyguara.graphics.atlas import Atlas, AtlasRegion
from pyguara.log import get_logger

from .exceptions import InvalidMetadataError, ResourceLoadError
from .loader import IMetaAwareLoader, IResourceLoader
from .meta import MetaLoader, get_meta_loader
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
        self._cache: dict[str, Resource] = {}
        self._extension_map: dict[str, IResourceLoader] = {}
        self._path_index: dict[str, str] = {}
        self._reference_counts: dict[str, int] = {}
        self._meta_loader = meta_loader or get_meta_loader()

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
            return res

        # 3. Load from disk
        resource = self._load_from_disk(actual_path, resource_type)

        self._cache[actual_path] = resource

        # A load is a cache-get, not an acquire: the resource enters the cache
        # unpinned (ref count 0). Callers that need it to survive
        # unload_unused() must acquire() it explicitly.
        self._reference_counts[actual_path] = 0

        return resource

    def _load_from_disk(self, actual_path: str, resource_type: type[T]) -> T:
        """Run the registered loader for a path and type-check the result.

        Shared by load() (cache miss) and reload(). Does not touch the cache
        or the reference counts.

        Args:
            actual_path: The resolved filesystem path.
            resource_type: The expected class.

        Returns:
            The freshly loaded resource.

        Raises:
            ValueError: If no loader is registered for the file extension.
            TypeError: If the loader returns the wrong type.
        """
        extension = os.path.splitext(actual_path)[1].lower()
        loader = self._extension_map.get(extension)

        if not loader:
            raise ValueError(f"No loader registered for extension: {extension}")

        logger.debug("Loading resource: %s", actual_path)

        # Check for meta-aware loader and load metadata
        meta = None
        if isinstance(loader, IMetaAwareLoader):
            meta = self._meta_loader.load_meta(actual_path)
            if meta:
                logger.debug("Applying meta settings for '%s'", actual_path)
            resource = loader.load_with_meta(actual_path, meta)
        else:
            resource = loader.load(actual_path)

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

    def get_cache_stats(self) -> dict[str, Any]:
        """
        Get statistics about the current resource cache state.

        Returns:
            A dict with ``resource_count`` (int), ``total_references`` (int)
            and ``resources`` (a ``{path: {"type": str, "ref_count": int}}``
            mapping).
        """
        total_refs = sum(self._reference_counts.values())
        resources_info = {
            path: {
                "type": type(res).__name__,
                "ref_count": self._reference_counts.get(path, 0),
            }
            for path, res in self._cache.items()
        }

        return {
            "resource_count": len(self._cache),
            "total_references": total_refs,
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
