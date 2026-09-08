"""Resource management subsystem.

Handles loading, caching, and lifecycle of game resources including
textures, audio clips, atlases, and other assets.
"""

from pyguara.resources.data import DataResource
from pyguara.resources.exceptions import (
    InvalidMetadataError,
    ResourceError,
    ResourceLoadError,
)
from pyguara.resources.loader import IMetaAwareLoader, IResourceLoader
from pyguara.resources.loaders.data_loader import JsonLoader
from pyguara.resources.manager import ResourceManager
from pyguara.resources.meta import (
    AssetMeta,
    AudioMeta,
    MetaLoader,
    SpritesheetMeta,
    TextureMeta,
    get_meta_loader,
)
from pyguara.resources.types import AudioClip, Resource, Texture

__all__ = [
    "AssetMeta",
    "AudioClip",
    "AudioMeta",
    "DataResource",
    "IMetaAwareLoader",
    "IResourceLoader",
    "InvalidMetadataError",
    "JsonLoader",
    "MetaLoader",
    "Resource",
    "ResourceError",
    "ResourceLoadError",
    "ResourceManager",
    "SpritesheetMeta",
    "Texture",
    "TextureMeta",
    "get_meta_loader",
]
