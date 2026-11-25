"""Prefab loader for the resource system.

Provides loading of prefab files in JSON and YAML formats.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pyguara import assets
from pyguara.log import get_logger
from pyguara.persistence.migration import MigrationError, MigrationManager
from pyguara.prefabs.types import PrefabChild, PrefabData
from pyguara.resources.types import Resource

logger = get_logger(__name__)


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


class PrefabLoader:
    """Loader for prefab files.

    Supports JSON (.prefab.json, .json) and YAML (.prefab.yaml, .yaml, .prefab.yml)
    file formats.

    With `migrations`, a file whose `version` is older than the manager's
    `current_version` is upgraded on load, one registered step at a time,
    before it is parsed; the loaded prefab reports the current version.

    Attributes:
        migrations: Upgrades old prefab files, or None to load every version
            as written.
    """

    def __init__(self, migrations: MigrationManager | None = None) -> None:
        """Create a loader.

        Args:
            migrations: Upgrades old prefab files as they load.
        """
        self.migrations = migrations

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

        if not assets.is_file(file_path):
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

    def _load_json(self, path: Path) -> dict[str, Any]:
        """Load JSON file."""
        result: dict[str, Any] = json.loads(assets.read_text(path))
        return result

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """Load YAML file."""
        result: dict[str, Any] = yaml.safe_load(assets.read_text(path))
        return result

    def _load_auto(self, path: Path) -> dict[str, Any]:
        """Auto-detect format and load."""
        content = assets.read_text(path).strip()

        # Try JSON first (starts with { or [)
        if content.startswith(("{", "[")):
            result: dict[str, Any] = json.loads(content)
            return result

        # Try YAML
        if HAS_YAML:
            result = yaml.safe_load(content)
            return result

        # Fallback to JSON
        result = json.loads(content)
        return result

    def _parse_prefab_data(self, raw: Any, source_path: str) -> PrefabData:
        """Parse raw dictionary into PrefabData.

        Args:
            raw: Raw data from file.
            source_path: Source file path for error messages.

        Returns:
            Parsed PrefabData.

        Raises:
            ValueError: If the top-level document is not a mapping, or a
                required field is missing.
        """
        if not isinstance(raw, dict):
            raise ValueError(
                f"Prefab '{source_path}' must contain a mapping at the top "
                f"level, got {type(raw).__name__}"
            )
        raw = self._migrate(raw, source_path)

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

    def _migrate(self, raw: dict[str, Any], source_path: str) -> dict[str, Any]:
        """Upgrade a file's data to the current version, when there are migrations.

        Raises:
            ValueError: If the version is not a whole number from 1, is newer
                than the migrations know, has no path to the current version,
                or a step fails. The message names the file.
        """
        if self.migrations is None:
            return raw
        version = raw.get("version", 1)
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise ValueError(
                f"Prefab '{source_path}' has version {version!r}; a version is a "
                f"whole number from 1"
            )
        try:
            migrated = self.migrations.migrate(raw, version)
        except (ValueError, MigrationError) as error:
            raise ValueError(f"Prefab '{source_path}': {error}") from error
        if not isinstance(migrated, dict):
            raise ValueError(
                f"Prefab '{source_path}': a migration returned "
                f"{type(migrated).__name__}, not a mapping"
            )
        migrated["version"] = self.migrations.current_version
        return migrated

    def _parse_children(self, children_raw: list[dict[str, Any]]) -> list[PrefabChild]:
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

    def __init__(self, loader: PrefabLoader | None = None) -> None:
        """Initialize the cache.

        Args:
            loader: Optional custom loader. Creates one if not provided.
        """
        self._loader = loader or PrefabLoader()
        self._cache: dict[str, PrefabData] = {}

    def load(self, path: str) -> PrefabData | None:
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

    def get(self, path: str) -> PrefabData | None:
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
