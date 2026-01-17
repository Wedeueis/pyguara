"""Resource management subsystem.

Handles loading, caching, and lifecycle of game resources including
textures, audio clips, atlases, and other assets.
"""

from pyguara.resources.exceptions import (
    InvalidMetadataError,
    ResourceError,
    ResourceLoadError,
)
from pyguara.resources.manager import ResourceManager
from pyguara.resources.types import Resource, Texture

__all__ = [
    "InvalidMetadataError",
    "Resource",
    "ResourceError",
    "ResourceLoadError",
    "ResourceManager",
    "Texture",
]
