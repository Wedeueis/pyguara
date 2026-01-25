"""Tests for the schema migration system."""

import pytest

from pyguara.persistence.migration import (
    Migration,
    MigrationError,
    MigrationManager,
    MigrationRegistry,
    migration,
)


class TestMigration:
    """Tests for Migration dataclass."""

    def test_create_migration(self):
        """Test creating a basic migration."""

        def migrate_fn(data):
            return data

        m = Migration(
            from_version=1,
            to_version=2,
            migrate_fn=migrate_fn,
            description="Test migration",
        )

        assert m.from_version == 1
        assert m.to_version == 2
        assert m.description == "Test migration"

    def test_migration_invalid_versions(self):
        """Test that migration rejects invalid version ordering."""

        def migrate_fn(data):
            return data

        with pytest.raises(ValueError, match="must be greater than"):
            Migration(from_version=2, to_version=2, migrate_fn=migrate_fn)

        with pytest.raises(ValueError, match="must be greater than"):
            Migration(from_version=3, to_version=2, migrate_fn=migrate_fn)

    def test_migration_apply(self):
        """Test applying a migration."""

        def add_field(data):
            data["new_field"] = "default"
            return data

        m = Migration(from_version=1, to_version=2, migrate_fn=add_field)
        result = m.apply({"existing": "value"})

        assert result["existing"] == "value"
        assert result["new_field"] == "default"


class TestMigrationManager:
    """Tests for MigrationManager."""

    def test_register_migration(self):
        """Test registering a migration."""
        manager = MigrationManager(current_version=2)

        def migrate_fn(data):
            return data

        m = Migration(from_version=1, to_version=2, migrate_fn=migrate_fn)
        manager.register(m)

        assert manager.has_migration_path(1)

    def test_register_duplicate_migration(self):
        """Test that duplicate migrations are rejected."""
        manager = MigrationManager(current_version=3)

        def migrate_fn(data):
            return data

        m1 = Migration(from_version=1, to_version=2, migrate_fn=migrate_fn)
        m2 = Migration(from_version=1, to_version=2, migrate_fn=migrate_fn)

        manager.register(m1)
        with pytest.raises(ValueError, match="already registered"):
            manager.register(m2)

    def test_register_migration_exceeds_current_version(self):
        """Test that migration cannot exceed current version."""
        manager = MigrationManager(current_version=2)

        def migrate_fn(data):
            return data

        m = Migration(from_version=1, to_version=3, migrate_fn=migrate_fn)
        with pytest.raises(ValueError, match="exceeds current_version"):
            manager.register(m)

    def test_get_migration_path(self):
        """Test getting the migration path."""
        manager = MigrationManager(current_version=4)

        def m1(data):
            return data

        def m2(data):
            return data

        def m3(data):
            return data

        manager.register(Migration(1, 2, m1))
        manager.register(Migration(2, 3, m2))
        manager.register(Migration(3, 4, m3))

        path = manager.get_migration_path(1)
        assert len(path) == 3
        assert path[0].from_version == 1
        assert path[1].from_version == 2
        assert path[2].from_version == 3

    def test_get_migration_path_no_path(self):
        """Test getting path when no migration exists."""
        manager = MigrationManager(current_version=3)

        def migrate_fn(data):
            return data

        manager.register(Migration(1, 2, migrate_fn))
        # Missing migration from 2 to 3

        with pytest.raises(ValueError, match="No migration registered"):
            manager.get_migration_path(1)

    def test_get_migration_path_already_current(self):
        """Test that no path is returned when already at current version."""
        manager = MigrationManager(current_version=2)
        path = manager.get_migration_path(2)
        assert path == []

    def test_migrate_single_step(self):
        """Test migrating data one version."""
        manager = MigrationManager(current_version=2)

        def add_health(data):
            data["health"] = data.pop("hp")
            return data

        manager.register(Migration(1, 2, add_health))

        original = {"hp": 100, "name": "Player"}
        result = manager.migrate(original, from_version=1)

        assert "hp" not in result
        assert result["health"] == 100
        assert result["name"] == "Player"

    def test_migrate_multiple_steps(self):
        """Test chained migration through multiple versions."""
        manager = MigrationManager(current_version=4)

        def v1_to_v2(data):
            data["health"] = data.pop("hp")
            return data

        def v2_to_v3(data):
            data["max_health"] = data["health"]
            return data

        def v3_to_v4(data):
            data["stats"] = {
                "health": data.pop("health"),
                "max": data.pop("max_health"),
            }
            return data

        manager.register(Migration(1, 2, v1_to_v2))
        manager.register(Migration(2, 3, v2_to_v3))
        manager.register(Migration(3, 4, v3_to_v4))

        original = {"hp": 100, "name": "Player"}
        result = manager.migrate(original, from_version=1)

        assert result["name"] == "Player"
        assert result["stats"]["health"] == 100
        assert result["stats"]["max"] == 100

    def test_migrate_already_current(self):
        """Test that data at current version is unchanged."""
        manager = MigrationManager(current_version=2)
        original = {"data": "value"}
        result = manager.migrate(original, from_version=2)
        assert result is original

    def test_migrate_future_version(self):
        """Test that future versions raise error."""
        manager = MigrationManager(current_version=2)
        with pytest.raises(ValueError, match="newer than current version"):
            manager.migrate({"data": "value"}, from_version=3)

    def test_migrate_failure_raises_error(self):
        """Test that migration failure raises MigrationError."""
        manager = MigrationManager(current_version=2)

        def bad_migration(data):
            raise KeyError("missing field")

        manager.register(Migration(1, 2, bad_migration))

        with pytest.raises(MigrationError, match="failed"):
            manager.migrate({"data": "value"}, from_version=1)

    def test_needs_migration(self):
        """Test needs_migration check."""
        manager = MigrationManager(current_version=3)
        assert manager.needs_migration(1)
        assert manager.needs_migration(2)
        assert not manager.needs_migration(3)

    def test_has_migration_path(self):
        """Test has_migration_path check."""
        manager = MigrationManager(current_version=3)

        def migrate_fn(data):
            return data

        manager.register(Migration(1, 2, migrate_fn))
        manager.register(Migration(2, 3, migrate_fn))

        assert manager.has_migration_path(1)
        assert manager.has_migration_path(2)
        assert manager.has_migration_path(3)  # Already at current, empty path is valid


class TestMigrationDecorator:
    """Tests for the @migration decorator."""

    def test_migration_decorator(self):
        """Test creating migration via decorator."""

        @migration(from_version=1, to_version=2, description="Rename field")
        def rename_field(data):
            data["new_name"] = data.pop("old_name")
            return data

        assert isinstance(rename_field, Migration)
        assert rename_field.from_version == 1
        assert rename_field.to_version == 2
        assert rename_field.description == "Rename field"

        result = rename_field.apply({"old_name": "value"})
        assert result["new_name"] == "value"

    def test_migration_decorator_uses_docstring(self):
        """Test that decorator uses function docstring as description."""

        @migration(from_version=1, to_version=2)
        def my_migration(data):
            """This is the docstring."""
            return data

        assert my_migration.description == "This is the docstring."


class TestMigrationRegistry:
    """Tests for MigrationRegistry."""

    def test_registry_add_and_register_all(self):
        """Test adding migrations to registry and registering with manager."""
        registry = MigrationRegistry()

        def m1(data):
            return data

        def m2(data):
            return data

        registry.add(Migration(1, 2, m1))
        registry.add(Migration(2, 3, m2))

        manager = MigrationManager(current_version=3)
        registry.register_all(manager)

        assert manager.has_migration_path(1)
        path = manager.get_migration_path(1)
        assert len(path) == 2

    def test_registry_clear(self):
        """Test clearing the registry."""
        registry = MigrationRegistry()

        def m(data):
            return data

        registry.add(Migration(1, 2, m))
        registry.clear()

        manager = MigrationManager(current_version=2)
        registry.register_all(manager)

        assert not manager.has_migration_path(1)
