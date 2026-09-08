"""Replay serialization for save/load functionality.

Handles saving and loading replay data to/from files.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from pyguara.log import get_logger
from pyguara.replay.types import ReplayData

logger = get_logger(__name__)


class ReplaySerializer:
    """Serializes and deserializes replay data.

    Supports JSON format with optional gzip compression for smaller file sizes.
    """

    # File extension for replay files
    EXTENSION = ".replay"
    COMPRESSED_EXTENSION = ".replay.gz"

    # Highest replay format version this serializer can read. Replay has no
    # migration layer (unlike persistence): a newer file is refused, not upgraded.
    SUPPORTED_VERSION = 1

    def save(
        self,
        replay_data: ReplayData,
        path: str,
        compress: bool = True,
    ) -> bool:
        """Save replay data to a file.

        The on-disk format always matches the file extension: a ``.replay.gz``
        path is gzip, a ``.replay`` path is plain JSON, and a path with neither
        gets one appended according to ``compress``. An explicit extension wins
        over ``compress`` so the file is never a gzip stream named ``.replay``
        (which :meth:`load` would then reject).

        Args:
            replay_data: The replay data to save.
            path: File path to save to.
            compress: Whether to gzip, when ``path`` carries no known extension.

        Returns:
            True if save successful.
        """
        base = str(path)
        if base.endswith(self.COMPRESSED_EXTENSION):
            file_path, compress = Path(base), True
        elif base.endswith(self.EXTENSION):
            file_path, compress = Path(base), False
        else:
            suffix = self.COMPRESSED_EXTENSION if compress else self.EXTENSION
            file_path = Path(base + suffix)

        # to_dict() / json.dumps() failures are programmer errors in the data
        # model, not runtime conditions -- let them raise. Only I/O is caught.
        data = replay_data.to_dict()
        json_str = json.dumps(data, separators=(",", ":"))

        try:
            if compress:
                with gzip.open(file_path, "wt", encoding="utf-8") as f:
                    f.write(json_str)
            else:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(json_str)
        except OSError as e:
            logger.error(f"Failed to save replay: {e}")
            return False

        logger.info(f"Saved replay to {file_path}")
        return True

    def load(self, path: str) -> ReplayData | None:
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
                with open(file_path, encoding="utf-8") as f:
                    json_str = f.read()

            # Parse JSON
            data = json.loads(json_str)

            raw_meta = data.get("metadata") if isinstance(data, dict) else None
            file_version = (
                raw_meta.get("version", 1) if isinstance(raw_meta, dict) else 1
            )
            if file_version > self.SUPPORTED_VERSION:
                logger.error(
                    f"Replay format v{file_version} in {file_path} is newer than "
                    f"the supported v{self.SUPPORTED_VERSION}; cannot load"
                )
                return None

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
        except (OSError, gzip.BadGzipFile) as e:
            logger.error(f"Failed to load replay: {e}")
            return None

    def get_metadata(self, path: str) -> dict | None:
        """Read just the metadata block from a replay file.

        Parses the file but returns only ``metadata`` -- for a save/replay menu
        that needs seed, scene, duration and frame count without building every
        :class:`~pyguara.replay.types.InputFrame`. (A leading length-framed
        metadata line would let this skip the frame bytes entirely; that is a
        possible future format change, tracked in the audit notes.)

        Args:
            path: File path to load from.

        Returns:
            Metadata dictionary, or None if the file is missing or unreadable.
        """
        try:
            file_path = Path(path)

            if not file_path.exists():
                return None

            if str(file_path).endswith(".gz"):
                with gzip.open(file_path, "rt", encoding="utf-8") as f:
                    json_str = f.read()
            else:
                with open(file_path, encoding="utf-8") as f:
                    json_str = f.read()

            data = json.loads(json_str)
            metadata: Any = data.get("metadata") if isinstance(data, dict) else None
            return metadata if isinstance(metadata, dict) else None

        except (OSError, json.JSONDecodeError, gzip.BadGzipFile) as e:
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


def load_replay(path: str) -> ReplayData | None:
    """Load replay data from a file.

    Args:
        path: File path to load from.

    Returns:
        Loaded replay data, or None if load failed.
    """
    serializer = ReplaySerializer()
    return serializer.load(path)
