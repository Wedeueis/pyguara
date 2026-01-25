"""Schema migration system for versioned save files.

Provides automatic migration pipeline for save data, enabling forward
compatibility as game schemas evolve.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class Migration:
    """Represents a single schema migration step.

    Attributes:
        from_version: Source schema version.
        to_version: Target schema version.
        migrate_fn: Function that transforms data from source to target version.
        description: Human-readable description of what this migration does.
    """

    from_version: int
    to_version: int
    migrate_fn: Callable[[Dict[str, Any]], Dict[str, Any]]
    description: str = ""

    def __post_init__(self) -> None:
        """Validate migration version ordering."""
        if self.to_version <= self.from_version:
            raise ValueError(
                f"Migration to_version ({self.to_version}) must be greater than "
                f"from_version ({self.from_version})"
            )

    def apply(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply this migration to the given data.

        Args:
            data: The data dictionary to migrate.

        Returns:
            Migrated data dictionary.
        """
        logger.debug(
            f"Applying migration v{self.from_version} -> v{self.to_version}: "
            f"{self.description}"
        )
        return self.migrate_fn(data)


class MigrationManager:
    """Manages schema migrations for save data.

    Maintains a registry of migrations and handles chained migration from
    any historical version to the current version.

    Attributes:
        current_version: The current schema version of the application.
    """

    def __init__(self, current_version: int = 1) -> None:
        """Initialize the migration manager.

        Args:
            current_version: The current schema version.
        """
        self.current_version = current_version
        self._migrations: Dict[int, Migration] = {}  # from_version -> Migration

    def register(self, migration: Migration) -> None:
        """Register a migration.

        Args:
            migration: The migration to register.

        Raises:
            ValueError: If a migration from this version already exists.
        """
        if migration.from_version in self._migrations:
            raise ValueError(
                f"Migration from version {migration.from_version} already registered"
            )

        if migration.to_version > self.current_version:
            raise ValueError(
                f"Migration to_version ({migration.to_version}) exceeds "
                f"current_version ({self.current_version})"
            )

        self._migrations[migration.from_version] = migration
        logger.info(
            f"Registered migration v{migration.from_version} -> "
            f"v{migration.to_version}: {migration.description}"
        )

    def get_migration_path(self, from_version: int) -> List[Migration]:
        """Get the sequence of migrations needed to reach current version.

        Args:
            from_version: Starting schema version.

        Returns:
            Ordered list of migrations to apply.

        Raises:
            ValueError: If no migration path exists.
        """
        if from_version >= self.current_version:
            return []

        path: List[Migration] = []
        version = from_version

        while version < self.current_version:
            if version not in self._migrations:
                raise ValueError(
                    f"No migration registered from version {version}. "
                    f"Cannot migrate from v{from_version} to v{self.current_version}"
                )

            migration = self._migrations[version]
            path.append(migration)
            version = migration.to_version

        return path

    def migrate(self, data: Dict[str, Any], from_version: int) -> Dict[str, Any]:
        """Migrate data from a historical version to current.

        Applies all necessary migrations in sequence.

        Args:
            data: The data dictionary to migrate.
            from_version: The schema version of the data.

        Returns:
            Migrated data at current_version.

        Raises:
            ValueError: If no migration path exists.
            MigrationError: If any migration fails.
        """
        if from_version == self.current_version:
            logger.debug(f"Data already at current version {self.current_version}")
            return data

        if from_version > self.current_version:
            raise ValueError(
                f"Data version ({from_version}) is newer than current version "
                f"({self.current_version}). Downgrade migrations not supported."
            )

        path = self.get_migration_path(from_version)

        logger.info(
            f"Migrating data from v{from_version} to v{self.current_version} "
            f"({len(path)} migrations)"
        )

        result = data
        for migration in path:
            try:
                result = migration.apply(result)
            except Exception as e:
                raise MigrationError(
                    f"Migration v{migration.from_version} -> v{migration.to_version} "
                    f"failed: {e}"
                ) from e

        logger.info(f"Migration complete: v{from_version} -> v{self.current_version}")
        return result

    def needs_migration(self, from_version: int) -> bool:
        """Check if data needs migration.

        Args:
            from_version: The schema version to check.

        Returns:
            True if migration is needed.
        """
        return from_version < self.current_version

    def has_migration_path(self, from_version: int) -> bool:
        """Check if a valid migration path exists.

        Args:
            from_version: Starting schema version.

        Returns:
            True if migration path exists.
        """
        try:
            self.get_migration_path(from_version)
            return True
        except ValueError:
            return False


class MigrationError(Exception):
    """Raised when a migration fails."""

    pass


def migration(
    from_version: int, to_version: int, description: str = ""
) -> Callable[[Callable[[Dict[str, Any]], Dict[str, Any]]], Migration]:
    """Create a migration from a function.

    Usage:
        @migration(from_version=1, to_version=2, description="Rename hp to health")
        def migrate_v1_to_v2(data: dict) -> dict:
            data["health"] = data.pop("hp")
            return data

    Args:
        from_version: Source schema version.
        to_version: Target schema version.
        description: Human-readable description.

    Returns:
        Decorator that creates a Migration object.
    """

    def decorator(func: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Migration:
        return Migration(
            from_version=from_version,
            to_version=to_version,
            migrate_fn=func,
            description=description or func.__doc__ or "",
        )

    return decorator


@dataclass
class MigrationRegistry:
    """Global registry for auto-discovered migrations.

    Use this to collect migrations defined across multiple modules.
    """

    _migrations: List[Migration] = field(default_factory=list)

    def add(self, migration: Migration) -> Migration:
        """Add a migration to the registry.

        Args:
            migration: Migration to register.

        Returns:
            The migration (for decorator chaining).
        """
        self._migrations.append(migration)
        return migration

    def register_all(self, manager: MigrationManager) -> None:
        """Register all collected migrations with a manager.

        Args:
            manager: MigrationManager to register with.
        """
        for mig in sorted(self._migrations, key=lambda m: m.from_version):
            manager.register(mig)

    def clear(self) -> None:
        """Clear all registered migrations."""
        self._migrations.clear()


# Global registry instance for decorator-based registration
_global_registry = MigrationRegistry()


def register_migration(
    from_version: int, to_version: int, description: str = ""
) -> Callable[[Callable[[Dict[str, Any]], Dict[str, Any]]], Migration]:
    """Create and register a migration globally.

    Usage:
        @register_migration(from_version=1, to_version=2)
        def migrate_v1_to_v2(data: dict) -> dict:
            data["health"] = data.pop("hp")
            return data

    Args:
        from_version: Source schema version.
        to_version: Target schema version.
        description: Human-readable description.

    Returns:
        Decorator that creates and registers a Migration.
    """

    def decorator(func: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Migration:
        mig = Migration(
            from_version=from_version,
            to_version=to_version,
            migrate_fn=func,
            description=description or func.__doc__ or "",
        )
        _global_registry.add(mig)
        return mig

    return decorator


def get_global_registry() -> MigrationRegistry:
    """Get the global migration registry."""
    return _global_registry
