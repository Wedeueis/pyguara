"""
Central Asset Management System.

This module provides the `ResourceManager`, which acts as the single source
of truth for all game assets. It handles:
1. Caching (Flyweight pattern) to prevent duplicate loading.
2. Loader delegation based on file extensions (Strategy pattern).
3. Type safety validation using Generics.
4. Asset metadata via `.meta` sidecar files for import settings.
"""

import logging
import os
import json
from pathlib import Path
from typing import Dict, Type, TypeVar

from .exceptions import InvalidMetadataError, ResourceLoadError
from .loader import IResourceLoader, IMetaAwareLoader
from .meta import MetaLoader, get_meta_loader
from .types import Resource, Texture
from pyguara.common.types import Rect
from pyguara.graphics.atlas import Atlas, AtlasRegion

logger = logging.getLogger(__name__)

# T must be a subclass of Resource (e.g., Texture)
T = TypeVar("T", bound=Resource)


class ResourceManager:
    """Orchestrate the loading, caching, and lifecycle of game resources.

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
        self._cache: Dict[str, Resource] = {}
        self._extension_map: Dict[str, IResourceLoader] = {}
        self._path_index: Dict[str, str] = {}
        self._reference_counts: Dict[str, int] = {}
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
            # Normaliza para lowercase para evitar erros (PNG vs png)
            clean_ext = ext.lower()

            # Opcional: Aviso se já existir um loader para essa extensão
            if clean_ext in self._extension_map:
                logger.warning("Overwriting loader for extension: %s", clean_ext)

            self._extension_map[clean_ext] = loader

    def index_directory(self, root_path: str, recursive: bool = True) -> None:
        """
        Scan a directory and maps filenames to their full paths without loading them.

        This allows requesting assets by name (e.g., 'hero') instead of full path
        (e.g., 'assets/chars/hero.png'), mimicking Godot's resource system.

        Args:
            root_path (str): The directory to scan.
            recursive (bool): If True, scans subdirectories as well.
        """
        path_obj = Path(root_path)
        if not path_obj.exists():
            logger.warning("Directory does not exist: %s", root_path)
            return

        iterator = path_obj.rglob("*") if recursive else path_obj.glob("*")

        for file_path in iterator:
            if file_path.is_file():
                extension = file_path.suffix.lower()
                # Only index files we know how to load
                if extension in self._extension_map:
                    filename = file_path.stem  # e.g., 'hero' from 'hero.png'
                    self._path_index[filename] = str(file_path)
                    # Also index the full filename just in case
                    self._path_index[file_path.name] = str(file_path)

    def load(self, path_or_name: str, resource_type: Type[T]) -> T:
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
            # Increment ref count for cached resource too
            if actual_path not in self._reference_counts:
                self._reference_counts[actual_path] = 0
            self._reference_counts[actual_path] += 1
            return res

        # 3. Find Loader (O(1) Lookup)
        extension = os.path.splitext(actual_path)[1].lower()
        loader = self._extension_map.get(extension)

        if not loader:
            raise ValueError(f"No loader registered for extension: {extension}")

        # 4. Load with metadata if supported
        logger.debug("Loading resource: %s", actual_path)

        # Check for meta-aware loader and load metadata
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

        self._cache[actual_path] = resource

        # Initialize reference count for new resource
        if actual_path not in self._reference_counts:
            self._reference_counts[actual_path] = 0

        # Auto-increment ref count on load
        self._reference_counts[actual_path] += 1

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

    def get_cache_stats(self) -> dict:
        """
        Get statistics about the current resource cache state.

        Returns:
            dict: Statistics including resource count, total refs, and resource details.
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
            with open(metadata_file, "r") as f:
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
        regions: Dict[str, AtlasRegion] = {}
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

        # Create and return the atlas
        atlas = Atlas(texture=texture, regions=regions)

        logger.debug("Loaded atlas '%s' with %d regions", atlas_path, len(regions))

        return atlas
