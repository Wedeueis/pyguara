"""Migration registry module.

This module collects all migrations for the persistence system.
Add your migrations here or import them from submodules.

Usage:
    # Define migrations using the decorator
    from pyguara.persistence.migration import register_migration

    @register_migration(from_version=1, to_version=2, description="Example migration")
    def migrate_v1_to_v2(data: dict) -> dict:
        # Transform data from v1 to v2 format
        return data

    # Or define migrations manually and add to the registry
    from pyguara.persistence.migration import Migration, get_global_registry

    def my_migration(data: dict) -> dict:
        return data

    get_global_registry().add(Migration(
        from_version=2,
        to_version=3,
        migrate_fn=my_migration,
        description="Another migration"
    ))
"""

from pyguara.persistence.migration import (
    Migration,
    MigrationManager,
    MigrationRegistry,
    get_global_registry,
    migration,
    register_migration,
)

__all__ = [
    "Migration",
    "MigrationManager",
    "MigrationRegistry",
    "get_global_registry",
    "migration",
    "register_migration",
]
