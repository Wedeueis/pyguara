"""Integration tests for `MultiScopePersistence`/`SaveProfile` against real
files under `tmp_path`, matching `test_persistence_backend.py`'s approach.
"""

import pytest

from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.migration import MigrationManager
from pyguara.persistence.multi_scope import MultiScopePersistence, SaveProfile
from pyguara.persistence.storage import FileStorageBackend


class TestFromDirectories:
    def test_each_scope_gets_its_own_subdirectory(self, tmp_path):
        multi = MultiScopePersistence.from_directories(str(tmp_path), ["run", "meta"])

        multi.store("run").save_data("progress", {"floor": 3})
        multi.store("meta").save_data("progress", {"unlocks": ["dash"]})

        assert (tmp_path / "run" / "progress.save").exists()
        assert (tmp_path / "meta" / "progress.save").exists()
        # Same key, different scopes: never overwrite each other.
        assert multi.store("run").load_data("progress") == {"floor": 3}
        assert multi.store("meta").load_data("progress") == {"unlocks": ["dash"]}

    def test_store_raises_for_an_unknown_scope(self, tmp_path):
        multi = MultiScopePersistence.from_directories(str(tmp_path), ["run"])

        with pytest.raises(KeyError):
            multi.store("meta")


class TestConstructorAcceptsIndependentMigrationManagers:
    def test_scopes_do_not_share_a_migration_manager(self, tmp_path):
        run_migrations = MigrationManager(current_version=3)
        meta_migrations = MigrationManager(current_version=7)
        multi = MultiScopePersistence(
            {
                "run": PersistenceManager(
                    FileStorageBackend(base_path=str(tmp_path / "run")),
                    migration_manager=run_migrations,
                ),
                "meta": PersistenceManager(
                    FileStorageBackend(base_path=str(tmp_path / "meta")),
                    migration_manager=meta_migrations,
                ),
            }
        )

        assert multi.store("run").migration_manager.current_version == 3
        assert multi.store("meta").migration_manager.current_version == 7


class TestSaveProfile:
    def test_begin_run_returns_a_profile_bound_to_the_named_scope(self, tmp_path):
        multi = MultiScopePersistence.from_directories(str(tmp_path), ["run", "meta"])

        profile = multi.begin_run("run")

        assert isinstance(profile, SaveProfile)
        assert profile.scope_name == "run"
        assert profile.ended is False

    def test_begin_run_defaults_to_the_run_scope(self, tmp_path):
        multi = MultiScopePersistence.from_directories(str(tmp_path), ["run", "meta"])

        profile = multi.begin_run()

        assert profile.scope_name == "run"

    def test_save_and_load_roundtrip_through_the_scopes_store(self, tmp_path):
        multi = MultiScopePersistence.from_directories(str(tmp_path), ["run"])
        profile = multi.begin_run("run")

        profile.save("state", {"hp": 10})

        assert profile.load("state") == {"hp": 10}
        assert (tmp_path / "run" / "state.save").exists()

    def test_end_with_delete_data_wipes_only_this_scope(self, tmp_path):
        multi = MultiScopePersistence.from_directories(str(tmp_path), ["run", "meta"])
        multi.store("meta").save_data("unlocks", ["dash"])
        profile = multi.begin_run("run")
        profile.save("state", {"hp": 10})

        profile.end(delete_data=True)

        assert multi.store("run").storage.list_keys() == []
        # The other scope is untouched.
        assert multi.store("meta").load_data("unlocks") == ["dash"]

    def test_end_without_delete_data_keeps_it(self, tmp_path):
        multi = MultiScopePersistence.from_directories(str(tmp_path), ["run"])
        profile = multi.begin_run("run")
        profile.save("state", {"hp": 10})

        profile.end(delete_data=False)

        assert multi.store("run").load_data("state") == {"hp": 10}

    def test_end_is_idempotent(self, tmp_path):
        multi = MultiScopePersistence.from_directories(str(tmp_path), ["run"])
        profile = multi.begin_run("run")
        profile.save("state", {"hp": 10})

        profile.end(delete_data=True)
        profile.end(delete_data=True)  # must not raise, must not re-log oddly

        assert profile.ended is True

    def test_save_after_end_raises(self, tmp_path):
        multi = MultiScopePersistence.from_directories(str(tmp_path), ["run"])
        profile = multi.begin_run("run")
        profile.end()

        with pytest.raises(RuntimeError):
            profile.save("state", {"hp": 10})

    def test_load_after_end_raises(self, tmp_path):
        multi = MultiScopePersistence.from_directories(str(tmp_path), ["run"])
        profile = multi.begin_run("run")
        profile.end()

        with pytest.raises(RuntimeError):
            profile.load("state")
