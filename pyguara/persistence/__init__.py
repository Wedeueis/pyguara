"""Data persistence system.

Provides save/load functionality with:
- Multiple serialization formats (JSON, MessagePack, binary)
- Integrity verification via checksums
- Schema migration support for versioned save files
- Pluggable storage backends
"""

from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.migration import (
    Migration,
    MigrationError,
    MigrationManager,
    MigrationRegistry,
    get_global_registry,
    migration,
    register_migration,
)
from pyguara.persistence.types import SaveMetadata, SerializationFormat, StorageBackend

__all__ = [
    "Migration",
    "MigrationError",
    "MigrationManager",
    "MigrationRegistry",
    "PersistenceManager",
    "SaveMetadata",
    "SerializationFormat",
    "StorageBackend",
    "get_global_registry",
    "migration",
    "register_migration",
]
