"""
Interface definition for Resource Loaders.

This module uses Python Protocols to define the Strategy Pattern for
loading files. Any class that implements this protocol can be registered
into the ResourceManager.
"""

from typing import Protocol, List
from .types import Resource


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
