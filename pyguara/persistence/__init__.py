"""Data persistence system.

Provides save/load functionality with:
- Multiple serialization formats (JSON, MessagePack, binary)
- Integrity verification via checksums, with fallback to a backup copy
- Schema migration support for versioned save files
- Pluggable storage backends, including the per-user data directory
"""

from pyguara.persistence.manager import (
    CONTAINER_FORMAT_VERSION,
    PersistenceManager,
    UnsupportedSaveFormatError,
)
from pyguara.persistence.migration import (
    Migration,
    MigrationError,
    MigrationManager,
    MigrationRegistry,
    get_global_registry,
    migration,
    register_migration,
)
from pyguara.persistence.multi_scope import MultiScopePersistence, SaveProfile
from pyguara.persistence.storage import FileStorageBackend, user_data_path
from pyguara.persistence.types import (
    BackupCapableStorage,
    HeaderReadableStorage,
    SaveMetadata,
    SerializationFormat,
    StorageBackend,
)

__all__ = [
    "CONTAINER_FORMAT_VERSION",
    "BackupCapableStorage",
    "FileStorageBackend",
    "HeaderReadableStorage",
    "Migration",
    "MigrationError",
    "MigrationManager",
    "MigrationRegistry",
    "MultiScopePersistence",
    "PersistenceManager",
    "SaveMetadata",
    "SaveProfile",
    "SerializationFormat",
    "StorageBackend",
    "UnsupportedSaveFormatError",
    "get_global_registry",
    "user_data_path",
    "migration",
    "register_migration",
]
