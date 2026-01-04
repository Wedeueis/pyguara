"""
Core abstract definitions for the Resource domain.

This module defines the foundational data structures and contracts for the
resource system. It relies on the 'Dependency Inversion Principle':
the core engine depends on these abstract classes, while specific backends
(like Pygame or OpenGL) inherit from them to provide implementation details.
"""

from abc import ABC, abstractmethod
from typing import Any


class Resource(ABC):
    """
    The base abstract class for all assets loaded from the filesystem.

    Attributes:
        path (str): The original file path or unique identifier of the resource.
    """

    def __init__(self, path: str):
        """Initialize the resource with a file path."""
        self._path = path
        self._ref_count = 0

    @property
    def path(self) -> str:
        """Get the file path associated with this resource."""
        return self._path

    @property
    @abstractmethod
    def native_handle(self) -> Any:
        """
        Returns the underlying engine-specific object.

        This is an 'escape hatch' allowing low-level systems (like a Renderer)
        to access the raw data (e.g., pygame.Surface) needed for drawing.

        Returns:
            Any: The backend-specific object.
        """
        ...


class Texture(Resource):
    """Abstract contract for a 2D image or texture."""

    @property
    @abstractmethod
    def width(self) -> int:
        """Get the width of the texture in pixels."""
        ...

    @property
    @abstractmethod
    def height(self) -> int:
        """Get the height of the texture in pixels."""
        ...

    @property
    def size(self) -> tuple[int, int]:
        """Get a tuple containing (width, height)."""
        return (self.width, self.height)


class AudioClip(Resource):
    """Abstract contract for sound effects or music tracks."""

    @property
    @abstractmethod
    def duration(self) -> float:
        """Return the audio clip duration in seconds."""
        ...
