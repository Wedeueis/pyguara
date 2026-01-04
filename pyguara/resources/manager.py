"""
Central Asset Management System.

This module provides the `ResourceManager`, which acts as the single source
of truth for all game assets. It handles:
1. Caching (Flyweight pattern) to prevent duplicate loading.
2. Loader delegation based on file extensions (Strategy pattern).
3. Type safety validation using Generics.
"""

import os
from pathlib import Path
from typing import Dict, Type, TypeVar
from .types import Resource
from .loader import IResourceLoader

# T must be a subclass of Resource (e.g., Texture)
T = TypeVar("T", bound=Resource)


class ResourceManager:
    """Orchestrate the loading, caching, and lifecycle of game resources."""

    def __init__(self) -> None:
        """Initialize the manager with empty cache and index."""
        self._cache: Dict[str, Resource] = {}
        self._extension_map: Dict[str, IResourceLoader] = {}
        self._path_index: Dict[str, str] = {}

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
                print(f"[Warning] Overwriting loader for {clean_ext}")

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
            print(f"[ResourceManager] Warning: Directory {root_path} does not exist.")
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
            return res

        # 3. Find Loader (O(1) Lookup)
        extension = os.path.splitext(actual_path)[1].lower()
        loader = self._extension_map.get(extension)

        if not loader:
            raise ValueError(f"No loader registered for extension: {extension}")

        # 4. Load & Verify
        print(f"[ResourceManager] Loading {actual_path}...")
        resource = loader.load(actual_path)

        if not isinstance(resource, resource_type):
            raise TypeError(
                f"Loader for {extension} returned {type(resource).__name__}, "
                f"expected {resource_type.__name__}."
            )

        self._cache[actual_path] = resource
        return resource

    def unload(self, path_or_name: str) -> None:
        """
        Remove a resource from the cache, allowing the garbage collector to free memory.

        Args:
            path_or_name (str): The identifier used to load the resource.
        """
        actual_path = self._path_index.get(path_or_name, path_or_name)
        if actual_path in self._cache:
            del self._cache[actual_path]
            print(f"[ResourceManager] Unloaded {actual_path}")
