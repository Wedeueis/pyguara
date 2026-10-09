"""
Core abstract definitions for the Resource domain.

This module defines the foundational data structures and contracts for the
resource system. It relies on the 'Dependency Inversion Principle':
the core engine depends on these abstract classes, while specific backends
(like Pygame or OpenGL) inherit from them to provide implementation details.
"""

from abc import ABC, abstractmethod
from typing import Any

from pyguara.resources.meta import AssetMeta


class Resource(ABC):
    """
    The base abstract class for all assets loaded from the filesystem.

    Attributes:
        path (str): The original file path or unique identifier of the resource.
        import_meta (AssetMeta | None): The `.meta` sidecar settings a
            meta-aware loader resolved for this resource, or None. Systems that
            need import settings after load (e.g. the audio system reading
            ``volume_db``) read them here instead of round-tripping through the
            ResourceManager.
    """

    def __init__(self, path: str):
        """Initialize the resource with a file path."""
        self._path = path
        self._import_meta: AssetMeta | None = None

    @property
    def path(self) -> str:
        """Get the file path associated with this resource."""
        return self._path

    @property
    def import_meta(self) -> AssetMeta | None:
        """Get the `.meta` import settings resolved for this resource."""
        return self._import_meta

    @import_meta.setter
    def import_meta(self, meta: AssetMeta | None) -> None:
        self._import_meta = meta

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

    @property
    def size_bytes(self) -> int:
        """Roughly how much memory this resource occupies.

        What `ResourceManager`'s cache budget counts. An estimate, not a
        measurement: the real figure lives in a backend's allocator and
        often on the GPU, where Python cannot see it at all.

        **Zero means "unknown", not "free".** The base class returns zero
        rather than guessing, and a resource the budget cannot measure is
        neither counted towards it nor evicted to satisfy it -- evicting
        something of unknown size frees an unknown amount, which is not a
        step towards a target. Subclasses that can estimate should, and
        `Texture` does, which is where the memory actually is.

        Returns:
            Bytes, or 0 when unknown.
        """
        return 0


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

    @property
    def size_bytes(self) -> int:
        """Estimated memory, as four bytes of RGBA per pixel.

        Four bytes because every backend here uploads RGBA: the pygame
        surfaces are converted with alpha and the GL textures are four
        components. A compressed or paletted format would use less, and
        mipmaps more; neither is in the engine, and a figure that is right
        for what the engine does beats a configurable one that is right
        for nothing.

        Returns:
            Bytes.
        """
        return self.width * self.height * 4


class AudioClip(Resource):
    """Abstract contract for sound effects or music tracks."""

    @property
    @abstractmethod
    def duration(self) -> float:
        """Return the audio clip duration in seconds."""
        ...
