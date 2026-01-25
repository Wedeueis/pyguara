"""Replay serialization for save/load functionality.

Handles saving and loading replay data to/from files.
"""

from __future__ import annotations

import gzip
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from pyguara.replay.types import ReplayData

logger = logging.getLogger(__name__)


class ReplaySerializer:
    """Serializes and deserializes replay data.

    Supports JSON format with optional gzip compression for smaller file sizes.
    """

    # File extension for replay files
    EXTENSION = ".replay"
    COMPRESSED_EXTENSION = ".replay.gz"

    def save(
        self,
        replay_data: ReplayData,
        path: str,
        compress: bool = True,
    ) -> bool:
        """Save replay data to a file.

        Args:
            replay_data: The replay data to save.
            path: File path to save to.
            compress: Whether to use gzip compression.

        Returns:
            True if save successful.
        """
        try:
            file_path = Path(path)

            # Add extension if not present
            if not str(path).endswith((self.EXTENSION, self.COMPRESSED_EXTENSION)):
                if compress:
                    file_path = Path(str(path) + self.COMPRESSED_EXTENSION)
                else:
                    file_path = Path(str(path) + self.EXTENSION)

            # Convert to dict
            data = replay_data.to_dict()

            # Serialize to JSON
            json_str = json.dumps(data, separators=(",", ":"))

            if compress or str(file_path).endswith(".gz"):
                # Write compressed
                with gzip.open(file_path, "wt", encoding="utf-8") as f:
                    f.write(json_str)
            else:
                # Write uncompressed
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(json_str)

            logger.info(f"Saved replay to {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save replay: {e}")
            return False

    def load(self, path: str) -> Optional[ReplayData]:
        """Load replay data from a file.

        Args:
            path: File path to load from.

        Returns:
            Loaded replay data, or None if load failed.
        """
        try:
            file_path = Path(path)

            if not file_path.exists():
                logger.error(f"Replay file not found: {path}")
                return None

            # Determine if compressed based on extension
            if str(file_path).endswith(".gz"):
                with gzip.open(file_path, "rt", encoding="utf-8") as f:
                    json_str = f.read()
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    json_str = f.read()

            # Parse JSON
            data = json.loads(json_str)

            # Convert to ReplayData
            replay_data = ReplayData.from_dict(data)

            logger.info(
                f"Loaded replay: {replay_data.metadata.frame_count} frames "
                f"from {file_path}"
            )
            return replay_data

        except json.JSONDecodeError as e:
            logger.error(f"Invalid replay file format: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load replay: {e}")
            return None

    def get_metadata(self, path: str) -> Optional[dict]:
        """Load only the metadata from a replay file.

        Useful for displaying replay info without loading all frames.

        Args:
            path: File path to load from.

        Returns:
            Metadata dictionary, or None if load failed.
        """
        try:
            file_path = Path(path)

            if not file_path.exists():
                return None

            # Read file
            if str(file_path).endswith(".gz"):
                with gzip.open(file_path, "rt", encoding="utf-8") as f:
                    # Read just enough for metadata
                    content = f.read(10000)  # First 10KB should have metadata
            else:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read(10000)

            # Try to parse just the metadata
            # This is a simple heuristic - full parsing would be more robust
            data = json.loads(
                content[: content.rfind("}") + 1] if "frames" in content else content
            )

            metadata: Dict[str, Any] = data.get("metadata", {})
            return metadata

        except Exception as e:
            logger.error(f"Failed to read replay metadata: {e}")
            return None


def save_replay(replay_data: ReplayData, path: str, compress: bool = True) -> bool:
    """Save replay data to a file.

    Args:
        replay_data: The replay data to save.
        path: File path to save to.
        compress: Whether to use compression.

    Returns:
        True if save successful.
    """
    serializer = ReplaySerializer()
    return serializer.save(replay_data, path, compress)


def load_replay(path: str) -> Optional[ReplayData]:
    """Load replay data from a file.

    Args:
        path: File path to load from.

    Returns:
        Loaded replay data, or None if load failed.
    """
    serializer = ReplaySerializer()
    return serializer.load(path)
