"""Concrete storage backend implementations."""

import os
import json
from typing import Any, Dict, Optional, Tuple, List
from pyguara.persistence.types import StorageBackend


class FileStorageBackend(StorageBackend):
    """
    Storage backend that saves data to the local filesystem.

    Each 'key' maps to a file in the base directory.
    Format:
        {key}.dat -> Raw Data
        {key}.meta -> Metadata (JSON)
    """

    def __init__(self, base_path: str = "saves") -> None:
        """
        Initialize the file storage.

        Args:
            base_path: Directory where files will be stored.
        """
        self.base_path = base_path
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)

    def _get_paths(self, key: str) -> Tuple[str, str]:
        """Return (data_path, meta_path) for a given key."""
        # Sanitize key to avoid path traversal
        safe_key = "".join(c for c in key if c.isalnum() or c in ("_", "-"))
        return (
            os.path.join(self.base_path, f"{safe_key}.dat"),
            os.path.join(self.base_path, f"{safe_key}.meta"),
        )

    def save(self, key: str, data: bytes, metadata: Dict[str, Any]) -> bool:
        """Save data and metadata to disk."""
        data_path, meta_path = self._get_paths(key)

        try:
            # Write Data
            with open(data_path, "wb") as f:
                f.write(data)

            # Write Meta
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4)

            return True
        except IOError as e:
            print(f"[FileStorage] Save failed: {e}")
            return False

    def load(self, key: str) -> Optional[tuple[bytes, Dict[str, Any]]]:
        """Load data and metadata from disk."""
        data_path, meta_path = self._get_paths(key)

        if not os.path.exists(data_path) or not os.path.exists(meta_path):
            return None

        try:
            with open(data_path, "rb") as f:
                data = f.read()

            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            return data, meta
        except IOError as e:
            print(f"[FileStorage] Load failed: {e}")
            return None

    def delete(self, key: str) -> bool:
        """Delete files for key."""
        data_path, meta_path = self._get_paths(key)

        success = False
        if os.path.exists(data_path):
            os.remove(data_path)
            success = True

        if os.path.exists(meta_path):
            os.remove(meta_path)

        return success

    def list_keys(self) -> List[str]:
        """List all keys (based on .meta files)."""
        keys = []
        if not os.path.exists(self.base_path):
            return []

        for filename in os.listdir(self.base_path):
            if filename.endswith(".meta"):
                keys.append(filename[:-5])
        return keys
