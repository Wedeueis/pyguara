"""Asset import metadata system.

This module provides a `.meta` file sidecar system for defining import
settings on assets. Meta files allow customization of how assets are
loaded without modifying the original files.

Example:
    For `hero.png`, create `hero.png.meta`:
    ```json
    {
        "type": "texture",
        "filter": "nearest",
        "mipmaps": false,
        "premultiply_alpha": true
    }
    ```

    For `bgm.ogg`, create `bgm.ogg.meta`:
    ```json
    {
        "type": "audio",
        "stream": true,
        "volume_db": -3.0
    }
    ```
"""

import json
import logging
from abc import ABC
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, Type, TypeVar

logger = logging.getLogger(__name__)


class TextureFilter(Enum):
    """Texture filtering mode for scaling."""

    NEAREST = "nearest"  # Pixelated (good for pixel art)
    LINEAR = "linear"  # Smooth (good for HD textures)


class AudioLoadMode(Enum):
    """How audio should be loaded."""

    LOAD = "load"  # Load entire file into memory (SFX)
    STREAM = "stream"  # Stream from disk (Music)


@dataclass
class AssetMeta(ABC):
    """Base class for asset import metadata.

    All meta types inherit from this and add their specific settings.
    """

    # Meta file version for future compatibility
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def get_type_name(cls) -> str:
        """Get the type identifier for this meta class."""
        return cls.__name__.replace("Meta", "").lower()


@dataclass
class TextureMeta(AssetMeta):
    """Import settings for texture assets.

    Attributes:
        filter: Texture filtering mode (nearest for pixel art, linear for HD).
        mipmaps: Whether to generate mipmaps for distance rendering.
        premultiply_alpha: Pre-multiply RGB by alpha for correct blending.
        srgb: Whether the texture is in sRGB color space.
        wrap_s: Horizontal texture wrapping (repeat, clamp, mirror).
        wrap_t: Vertical texture wrapping (repeat, clamp, mirror).
    """

    filter: str = "nearest"
    mipmaps: bool = False
    premultiply_alpha: bool = False
    srgb: bool = True
    wrap_s: str = "clamp"
    wrap_t: str = "clamp"

    def get_filter_mode(self) -> TextureFilter:
        """Get the filter mode as enum."""
        return TextureFilter(self.filter)


@dataclass
class AudioMeta(AssetMeta):
    """Import settings for audio assets.

    Attributes:
        load_mode: Whether to load entirely or stream from disk.
        volume_db: Volume adjustment in decibels (0 = original).
        loop_start: Loop start point in seconds (for seamless music loops).
        loop_end: Loop end point in seconds (None = end of file).
        normalize: Whether to normalize volume to peak at 0dB.
    """

    load_mode: str = "load"
    volume_db: float = 0.0
    loop_start: Optional[float] = None
    loop_end: Optional[float] = None
    normalize: bool = False

    def get_load_mode(self) -> AudioLoadMode:
        """Get the load mode as enum."""
        return AudioLoadMode(self.load_mode)

    def get_volume_multiplier(self) -> float:
        """Convert dB to linear volume multiplier."""
        # dB to linear: 10^(dB/20)
        return 10 ** (self.volume_db / 20.0)


@dataclass
class SpritesheetMeta(AssetMeta):
    """Import settings for spritesheet assets.

    Attributes:
        frame_width: Width of each frame in pixels.
        frame_height: Height of each frame in pixels.
        margin: Margin around the spritesheet in pixels.
        spacing: Spacing between frames in pixels.
        filter: Texture filtering mode.
    """

    frame_width: int = 32
    frame_height: int = 32
    margin: int = 0
    spacing: int = 0
    filter: str = "nearest"


# Registry of meta types by name
META_TYPES: Dict[str, Type[AssetMeta]] = {
    "texture": TextureMeta,
    "audio": AudioMeta,
    "spritesheet": SpritesheetMeta,
}

# Default meta types by file extension
EXTENSION_TO_META_TYPE: Dict[str, str] = {
    ".png": "texture",
    ".jpg": "texture",
    ".jpeg": "texture",
    ".bmp": "texture",
    ".tga": "texture",
    ".gif": "texture",
    ".wav": "audio",
    ".ogg": "audio",
    ".mp3": "audio",
    ".flac": "audio",
}

M = TypeVar("M", bound=AssetMeta)


class MetaLoader:
    """Loads and manages asset metadata from `.meta` files."""

    def __init__(self) -> None:
        """Initialize the meta loader."""
        self._cache: Dict[str, AssetMeta] = {}

    def get_meta_path(self, asset_path: str) -> Path:
        """Get the `.meta` file path for an asset.

        Args:
            asset_path: Path to the asset file.

        Returns:
            Path to the corresponding `.meta` file.
        """
        return Path(f"{asset_path}.meta")

    def has_meta(self, asset_path: str) -> bool:
        """Check if an asset has a `.meta` file.

        Args:
            asset_path: Path to the asset file.

        Returns:
            True if a `.meta` file exists.
        """
        return self.get_meta_path(asset_path).exists()

    def load_meta(
        self, asset_path: str, expected_type: Optional[Type[M]] = None
    ) -> Optional[AssetMeta]:
        """Load metadata for an asset.

        If no `.meta` file exists, returns None (use defaults).
        If a `.meta` file exists but is invalid, logs a warning and returns None.

        Args:
            asset_path: Path to the asset file.
            expected_type: Optional expected meta type for validation.

        Returns:
            The loaded AssetMeta, or None if no meta file exists.
        """
        # Check cache first
        if asset_path in self._cache:
            return self._cache[asset_path]

        meta_path = self.get_meta_path(asset_path)
        if not meta_path.exists():
            return None

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON in meta file '%s': %s", meta_path, e.msg)
            return None
        except OSError as e:
            logger.warning("Failed to read meta file '%s': %s", meta_path, e)
            return None

        # Determine meta type
        type_name = data.pop("type", None)
        if type_name is None:
            # Infer from file extension
            ext = Path(asset_path).suffix.lower()
            type_name = EXTENSION_TO_META_TYPE.get(ext)

        if type_name is None:
            logger.warning(
                "Cannot determine meta type for '%s' - no 'type' field and unknown extension",
                asset_path,
            )
            return None

        meta_class = META_TYPES.get(type_name)
        if meta_class is None:
            logger.warning("Unknown meta type '%s' in '%s'", type_name, meta_path)
            return None

        # Validate expected type if specified
        if expected_type is not None and meta_class != expected_type:
            logger.warning(
                "Meta file '%s' has type '%s', expected '%s'",
                meta_path,
                type_name,
                expected_type.get_type_name(),
            )

        # Create meta object, ignoring unknown fields
        try:
            # Filter to only known fields
            valid_fields = {
                k: v for k, v in data.items() if k in meta_class.__dataclass_fields__
            }
            meta = meta_class(**valid_fields)
        except (TypeError, ValueError) as e:
            logger.warning("Invalid data in meta file '%s': %s", meta_path, e)
            return None

        # Cache and return
        self._cache[asset_path] = meta
        logger.debug("Loaded meta for '%s': %s", asset_path, type_name)
        return meta

    def get_or_default(self, asset_path: str, meta_type: Type[M]) -> M:
        """Get metadata for an asset, returning defaults if no meta file.

        Args:
            asset_path: Path to the asset file.
            meta_type: The meta type class to use.

        Returns:
            The loaded meta or a default instance.
        """
        meta = self.load_meta(asset_path, meta_type)
        if meta is not None and isinstance(meta, meta_type):
            return meta
        return meta_type()

    def save_meta(self, asset_path: str, meta: AssetMeta) -> bool:
        """Save metadata to a `.meta` file.

        Args:
            asset_path: Path to the asset file.
            meta: The metadata to save.

        Returns:
            True if saved successfully, False otherwise.
        """
        meta_path = self.get_meta_path(asset_path)

        try:
            data = meta.to_dict()
            data["type"] = meta.get_type_name()

            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            # Update cache
            self._cache[asset_path] = meta
            logger.debug("Saved meta for '%s'", asset_path)
            return True

        except OSError as e:
            logger.error("Failed to save meta file '%s': %s", meta_path, e)
            return False

    def clear_cache(self) -> None:
        """Clear the metadata cache."""
        self._cache.clear()


# Global meta loader instance
_meta_loader: Optional[MetaLoader] = None


def get_meta_loader() -> MetaLoader:
    """Get the global meta loader instance."""
    global _meta_loader
    if _meta_loader is None:
        _meta_loader = MetaLoader()
    return _meta_loader
