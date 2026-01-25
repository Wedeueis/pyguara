"""Prefab loader for the resource system.

Provides loading of prefab files in JSON and YAML formats.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from pyguara.prefabs.types import PrefabChild, PrefabData
from pyguara.resources.loader import IResourceLoader
from pyguara.resources.types import Resource

logger = logging.getLogger(__name__)


# Try to import YAML support
try:
    import yaml  # type: ignore[import-untyped]

    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    yaml = None


class Prefab(Resource):
    """Resource wrapper for prefab data.

    Attributes:
        data: The parsed prefab data.
        path: Source file path.
    """

    def __init__(self, data: PrefabData, path: str) -> None:
        """Initialize the prefab resource.

        Args:
            data: Parsed prefab data.
            path: Source file path.
        """
        super().__init__(path)
        self.data = data

    @property
    def native_handle(self) -> PrefabData:
        """Return the prefab data as the native handle."""
        return self.data


class PrefabLoader(IResourceLoader):
    """Loader for prefab files.

    Supports JSON (.prefab.json, .json) and YAML (.prefab.yaml, .yaml, .prefab.yml)
    file formats.
    """

    @property
    def supported_extensions(self) -> list[str]:
        """Get supported file extensions."""
        extensions = [".prefab.json", ".prefab"]
        if HAS_YAML:
            extensions.extend([".prefab.yaml", ".prefab.yml"])
        return extensions

    def load(self, path: str) -> Prefab:
        """Load a prefab from file.

        Args:
            path: Path to the prefab file.

        Returns:
            Prefab resource containing the parsed data.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file format is invalid.
        """
        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"Prefab file not found: {path}")

        # Determine format by extension
        suffix = file_path.suffix.lower()
        suffixes = "".join(file_path.suffixes).lower()

        if suffix in (".json",) or suffixes.endswith(".prefab.json"):
            raw_data = self._load_json(file_path)
        elif suffix in (".yaml", ".yml") or suffixes.endswith(
            (".prefab.yaml", ".prefab.yml")
        ):
            if not HAS_YAML:
                raise ValueError(
                    "YAML support not available. Install PyYAML: pip install pyyaml"
                )
            raw_data = self._load_yaml(file_path)
        elif suffix == ".prefab":
            # Try JSON first, then YAML
            raw_data = self._load_auto(file_path)
        else:
            raise ValueError(f"Unsupported prefab format: {suffix}")

        # Parse into PrefabData
        prefab_data = self._parse_prefab_data(raw_data, path)
        return Prefab(prefab_data, path)

    def _load_json(self, path: Path) -> Dict[str, Any]:
        """Load JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            result: Dict[str, Any] = json.load(f)
            return result

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            result: Dict[str, Any] = yaml.safe_load(f)
            return result

    def _load_auto(self, path: Path) -> Dict[str, Any]:
        """Auto-detect format and load."""
        content = path.read_text(encoding="utf-8").strip()

        # Try JSON first (starts with { or [)
        if content.startswith(("{", "[")):
            result: Dict[str, Any] = json.loads(content)
            return result

        # Try YAML
        if HAS_YAML:
            result = yaml.safe_load(content)
            return result

        # Fallback to JSON
        result = json.loads(content)
        return result

    def _parse_prefab_data(self, raw: Dict[str, Any], source_path: str) -> PrefabData:
        """Parse raw dictionary into PrefabData.

        Args:
            raw: Raw data from file.
            source_path: Source file path for error messages.

        Returns:
            Parsed PrefabData.

        Raises:
            ValueError: If required fields are missing.
        """
        # Required field
        name = raw.get("name")
        if not name:
            # Use filename as name if not specified
            name = Path(source_path).stem

        # Optional fields with defaults
        version = raw.get("version", 1)
        components = raw.get("components", {})
        extends = raw.get("extends")
        tags = raw.get("tags", [])

        # Parse children
        children_raw = raw.get("children", [])
        children = self._parse_children(children_raw)

        return PrefabData(
            name=name,
            version=version,
            components=components,
            children=children,
            extends=extends,
            tags=tags,
        )

    def _parse_children(self, children_raw: List[Dict[str, Any]]) -> List[PrefabChild]:
        """Parse child prefab references.

        Args:
            children_raw: List of raw child data.

        Returns:
            List of PrefabChild objects.
        """
        children = []

        for child_data in children_raw:
            prefab_path = child_data.get("prefab")
            if not prefab_path:
                logger.warning("Child prefab missing 'prefab' field, skipping")
                continue

            child = PrefabChild(
                prefab=prefab_path,
                offset=child_data.get("offset"),
                name=child_data.get("name"),
                overrides=child_data.get("overrides", {}),
            )
            children.append(child)

        return children


class PrefabCache:
    """Cache for loaded prefabs with inheritance resolution.

    Provides a unified interface for loading and caching prefabs,
    with support for inheritance resolution.
    """

    def __init__(self, loader: Optional[PrefabLoader] = None) -> None:
        """Initialize the cache.

        Args:
            loader: Optional custom loader. Creates one if not provided.
        """
        self._loader = loader or PrefabLoader()
        self._cache: Dict[str, PrefabData] = {}

    def load(self, path: str) -> Optional[PrefabData]:
        """Load a prefab, using cache if available.

        Args:
            path: Path to the prefab file.

        Returns:
            PrefabData, or None if loading failed.
        """
        # Check cache
        if path in self._cache:
            return self._cache[path]

        try:
            prefab_resource = self._loader.load(path)
            self._cache[path] = prefab_resource.data
            return prefab_resource.data
        except Exception as e:
            logger.error(f"Failed to load prefab '{path}': {e}")
            return None

    def get(self, path: str) -> Optional[PrefabData]:
        """Get a cached prefab without loading.

        Args:
            path: Path to the prefab.

        Returns:
            Cached PrefabData, or None if not cached.
        """
        return self._cache.get(path)

    def invalidate(self, path: str) -> None:
        """Remove a prefab from cache.

        Args:
            path: Path to invalidate.
        """
        self._cache.pop(path, None)

    def invalidate_all(self) -> None:
        """Clear entire cache."""
        self._cache.clear()

    def is_cached(self, path: str) -> bool:
        """Check if a prefab is cached.

        Args:
            path: Path to check.

        Returns:
            True if cached.
        """
        return path in self._cache
