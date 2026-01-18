"""
Interface definition for Resource Loaders.

This module uses Python Protocols to define the Strategy Pattern for
loading files. Any class that implements this protocol can be registered
into the ResourceManager.
"""

from typing import Protocol, List, Optional, runtime_checkable
from .types import Resource
from .meta import AssetMeta


@runtime_checkable
class IResourceLoader(Protocol):
    """A Protocol that defines how to load a specific file format from disk."""

    @property
    def supported_extensions(self) -> List[str]:
        """
        A list of file extensions that this loader can handle.

        Example:
            return ['.png', '.jpg', '.jpeg']

        Returns:
            List[str]: Lowercase extensions including the dot.
        """
        ...

    def load(self, path: str) -> Resource:
        """
        Read the file at the given path and returns a concrete Resource instance.

        Args:
            path (str): The full path to the file.

        Returns:
            Resource: The loaded and wrapped resource (e.g., PygameTexture).

        Raises:
            FileNotFoundError: If the path does not exist.
            IOError: If the file is corrupted or unreadable.
        """
        ...


@runtime_checkable
class IMetaAwareLoader(IResourceLoader, Protocol):
    """Extended loader protocol that supports asset metadata.

    Loaders implementing this protocol can apply import settings from
    `.meta` files during loading.
    """

    def load_with_meta(self, path: str, meta: Optional[AssetMeta]) -> Resource:
        """
        Load a resource with optional metadata settings.

        If meta is None, uses default settings. Otherwise applies the
        settings from the meta object.

        Args:
            path: The full path to the file.
            meta: Optional metadata with import settings.

        Returns:
            Resource: The loaded resource with meta settings applied.
        """
        ...
