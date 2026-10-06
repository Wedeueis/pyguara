"""Integration tests for the persistence subsystem.

Covers ``FileStorageBackend`` as a blob store and ``PersistenceManager``
end to end against real files under ``tmp_path``.
"""

import gzip
import json
import pathlib

import pytest

from pyguara.persistence.manager import PersistenceManager
from pyguara.persistence.migration import Migration, MigrationManager
from pyguara.persistence.storage import FileStorageBackend
from pyguara.persistence.types import SerializationFormat


# --------------------------------------------------------------------------- #
# FileStorageBackend                                                           #
# --------------------------------------------------------------------------- #
class TestFileStorageBackend:
    def test_save_load_roundtrip(self, tmp_path):
        backend = FileStorageBackend(base_path=str(tmp_path))
        backend.save("save1", b"hello world")

        assert (tmp_path / "save1.save").exists()
        assert backend.load("save1") == b"hello world"

    def test_load_missing_key_returns_none(self, tmp_path):
        backend = FileStorageBackend(base_path=str(tmp_path))
        assert backend.load("ghost") is None

    def test_save_overwrites_in_place(self, tmp_path):
        backend = FileStorageBackend(base_path=str(tmp_path))
        backend.save("s", b"first")
        backend.save("s", b"second")
        assert backend.load("s") == b"second"
        assert list(tmp_path.glob("*.save")) == [tmp_path / "s.save"]

    @pytest.mark.parametrize(
        "bad_key",
        ["", "slot 1", "slot/1", "slot.1", "../etc/passwd", "a\x00b", "a:b", "a\\b"],
    )
    def test_unsafe_keys_are_rejected_not_mangled(self, tmp_path, bad_key):
        """Keys that would need sanitising raise instead of silently
        collapsing onto each other (two keys -> one file -> lost save)."""
        backend = FileStorageBackend(base_path=str(tmp_path))
        with pytest.raises(ValueError):
            backend.save(bad_key, b"x")
        with pytest.raises(ValueError):
            backend.load(bad_key)

    def test_safe_keys_with_dash_and_underscore_allowed(self, tmp_path):
        backend = FileStorageBackend(base_path=str(tmp_path))
        assert backend.save("slot_1-autosave", b"ok")
        assert backend.load("slot_1-autosave") == b"ok"

    def test_list_keys(self, tmp_path):
        backend = FileStorageBackend(base_path=str(tmp_path))
        backend.save("slot_a", b"")
        backend.save("slot_b", b"")
        (tmp_path / "not-a-save.txt").write_text("ignore me")
        assert sorted(backend.list_keys()) == ["slot_a", "slot_b"]

    def test_delete_reports_whether_a_file_was_removed(self, tmp_path):
        backend = FileStorageBackend(base_path=str(tmp_path))
        backend.save("gone", b"x")
        assert backend.delete("gone") is True
        assert backend.delete("gone") is False
        assert backend.load("gone") is None

    def test_creates_base_path_and_tolerates_existing(self, tmp_path):
        target = tmp_path / "deep" / "saves"
        FileStorageBackend(base_path=str(target))
        # Second construction over an existing directory must not raise.
        FileStorageBackend(base_path=str(target))
        assert target.is_dir()

    def test_sweeps_orphaned_temp_files_on_init(self, tmp_path):
        (tmp_path / ".tmp_crashed").write_bytes(b"partial")
        (tmp_path / "real.save").write_bytes(b"keep")
        backend = FileStorageBackend(base_path=str(tmp_path))
        assert not (tmp_path / ".tmp_crashed").exists()
        assert backend.load("real") == b"keep"


# --------------------------------------------------------------------------- #
# PersistenceManager end to end                                                #
# --------------------------------------------------------------------------- #
@pytest.fixture
def manager(tmp_path):
    return PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))


class TestPersistenceManager:
    def test_save_load_roundtrip(self, manager):
        data = {"score": 500, "name": "Player"}
        assert manager.save_data("autosave", data) is True
        assert manager.load_data("autosave") == data

    def test_blob_is_a_single_file_with_a_json_header_line(self, manager, tmp_path):
        manager.save_data("game", {"level": 3})
        raw = (tmp_path / "game.save").read_bytes()
        header, sep, payload = raw.partition(b"\n")
        assert sep == b"\n"
        meta = json.loads(header)
        assert meta["format"] == "json"
        assert meta["data_type"] == "dict"
        assert meta["version"]  # a real engine version, not hard-coded "1.0.0"
        assert meta["timestamp"].endswith("+00:00")  # timezone-aware UTC
        assert json.loads(payload) == {"level": 3}

    def test_load_missing_returns_none(self, manager):
        assert manager.load_data("nope") is None

    def test_integrity_failure_returns_none(self, manager, tmp_path):
        manager.save_data("game", {"hp": 10})
        path = tmp_path / "game.save"
        header, _, payload = path.read_bytes().partition(b"\n")
        # Flip a value byte: still valid JSON, but no longer matches checksum.
        path.write_bytes(header + b"\n" + payload.replace(b"10", b"99"))
        assert manager.load_data("game") is None
        # ...but skipping the check surfaces the (now different) data
        assert manager.load_data("game", verify_integrity=False) == {"hp": 99}

    def test_save_data_returns_false_when_backend_fails(self, tmp_path):
        class FailingBackend:
            def save(self, key, blob):
                return False

            def load(self, key):
                return None

            def delete(self, key):
                return False

            def list_keys(self):
                return []

        manager = PersistenceManager(FailingBackend())
        assert manager.save_data("k", {"a": 1}) is False

    def test_compression_roundtrip_and_shrinks_payload(self, manager, tmp_path):
        data = {"blob": "x" * 5000}
        manager.save_data("plain", data, compress=False)
        manager.save_data("gz", data, compress=True)

        plain = (tmp_path / "plain.save").stat().st_size
        gz = (tmp_path / "gz.save").stat().st_size
        assert gz < plain // 5

        _, _, payload = (tmp_path / "gz.save").read_bytes().partition(b"\n")
        assert gzip.decompress(payload)  # payload really is gzip
        assert manager.load_data("gz") == data

    def test_msgpack_format_roundtrip(self, manager, tmp_path):
        data = {"a": 1, "nested": {"b": [1, 2, 3]}}
        manager.save_data("mk", data, fmt=SerializationFormat.MSGPACK)
        meta = json.loads((tmp_path / "mk.save").read_bytes().partition(b"\n")[0])
        assert meta["format"] == "msgpack"
        assert manager.load_data("mk") == data

    def test_migration_applied_on_load(self, tmp_path):
        writer = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        writer.save_data("hero", {"hp": 100, "name": "P"}, save_version=1)

        mm = MigrationManager(current_version=2)
        mm.register(
            Migration(
                1,
                2,
                lambda d: {
                    **{k: v for k, v in d.items() if k != "hp"},
                    "health": d["hp"],
                },
            )
        )
        reader = PersistenceManager(
            FileStorageBackend(base_path=str(tmp_path)), migration_manager=mm
        )
        loaded = reader.load_data("hero")
        assert loaded == {"name": "P", "health": 100}

    def test_delete_through_backend(self, manager):
        manager.save_data("temp", {"x": 1})
        assert manager.storage.delete("temp") is True
        assert manager.load_data("temp") is None


# --------------------------------------------------------------------------- #
# Backup, recovery and quarantine                                              #
# --------------------------------------------------------------------------- #
def _corrupt_payload(path) -> None:
    """Damage a save's payload while leaving the header intact.

    This is the failure a backup exists for. The atomic write already rules
    out a *torn* file, so the interesting case is a blob that is structurally
    fine and still will not decode -- bit-rot, a bad migration, a lying
    disk. Truncating the file would only prove the easy case.
    """
    blob = path.read_bytes()
    header, _sep, payload = blob.partition(b"\n")
    path.write_bytes(header + b"\n" + payload[:-3] + b"XXX")


class TestBackupRetention:
    def test_the_first_save_has_no_backup(self, tmp_path):
        backend = FileStorageBackend(base_path=str(tmp_path))
        backend.save("s", b"one")
        assert backend.load_backup("s") is None

    def test_a_second_save_backs_up_the_first(self, tmp_path):
        backend = FileStorageBackend(base_path=str(tmp_path))
        backend.save("s", b"one")
        backend.save("s", b"two")
        assert backend.load("s") == b"two"
        assert backend.load_backup("s") == b"one"

    def test_the_backup_is_not_reported_as_a_save(self, tmp_path):
        """`list_keys()` matches `.save`, and a backup ends `.save.bak` --
        otherwise a save menu would show every slot twice."""
        backend = FileStorageBackend(base_path=str(tmp_path))
        backend.save("s", b"one")
        backend.save("s", b"two")
        assert backend.list_keys() == ["s"]

    def test_delete_takes_the_backup_with_it(self, tmp_path):
        """Leaving it behind would let a later load recover data the caller
        asked to be gone."""
        backend = FileStorageBackend(base_path=str(tmp_path))
        backend.save("s", b"one")
        backend.save("s", b"two")
        backend.delete("s")
        assert backend.load_backup("s") is None
        assert list(tmp_path.glob("s.save*")) == []

    def test_quarantine_moves_the_primary_aside(self, tmp_path):
        backend = FileStorageBackend(base_path=str(tmp_path))
        backend.save("s", b"one")
        target = backend.quarantine("s")
        assert target is not None
        assert backend.load("s") is None
        assert pathlib.Path(target).read_bytes() == b"one"

    def test_quarantine_of_a_missing_key_is_not_an_error(self, tmp_path):
        backend = FileStorageBackend(base_path=str(tmp_path))
        assert backend.quarantine("absent") is None

    def test_quarantined_files_are_not_reported_as_saves(self, tmp_path):
        backend = FileStorageBackend(base_path=str(tmp_path))
        backend.save("s", b"one")
        backend.quarantine("s")
        assert backend.list_keys() == []


class TestRecoveryFromBackup:
    def test_a_corrupt_primary_falls_back_to_the_previous_save(self, tmp_path):
        """The headline behaviour: for a permadeath roguelike this is the
        difference between a lost run and a recovered one."""
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        manager.save_data("slot", {"run": 1})
        manager.save_data("slot", {"run": 2})

        _corrupt_payload(tmp_path / "slot.save")

        assert manager.load_data("slot") == {"run": 1}

    def test_recovery_quarantines_the_corrupt_primary(self, tmp_path):
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        manager.save_data("slot", {"run": 1})
        manager.save_data("slot", {"run": 2})
        _corrupt_payload(tmp_path / "slot.save")

        manager.load_data("slot")

        assert list(tmp_path.glob("slot.save.corrupt.*"))

    def test_recovery_self_heals_so_the_next_load_is_clean(self, tmp_path):
        """A read that left the broken file in place would fail again every
        time, so the backup is promoted to primary on the way out."""
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        manager.save_data("slot", {"run": 1})
        manager.save_data("slot", {"run": 2})
        _corrupt_payload(tmp_path / "slot.save")

        first = manager.load_data("slot")
        second = manager.load_data("slot")

        assert first == second == {"run": 1}
        # The second load found a healthy primary, not another corrupt one.
        assert len(list(tmp_path.glob("slot.save.corrupt.*"))) == 1

    def test_no_backup_means_no_recovery(self, tmp_path):
        """One save, then corruption: there is nothing to fall back to, and
        the old behaviour -- None -- is preserved."""
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        manager.save_data("slot", {"run": 1})
        _corrupt_payload(tmp_path / "slot.save")

        assert manager.load_data("slot") is None

    def test_a_corrupt_backup_is_not_trusted_either(self, tmp_path):
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        manager.save_data("slot", {"run": 1})
        manager.save_data("slot", {"run": 2})
        _corrupt_payload(tmp_path / "slot.save")
        _corrupt_payload(tmp_path / "slot.save.bak")

        assert manager.load_data("slot") is None

    def test_a_missing_header_also_triggers_recovery(self, tmp_path):
        """Integrity failure is not the only way a blob goes bad."""
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        manager.save_data("slot", {"run": 1})
        manager.save_data("slot", {"run": 2})
        (tmp_path / "slot.save").write_bytes(b"no header separator here")

        assert manager.load_data("slot") == {"run": 1}

    def test_a_backend_without_backups_still_works(self, tmp_path):
        """`BackupCapableStorage` is an optional capability, so a minimal
        backend stays valid and simply gets no recovery."""

        class Minimal:
            def __init__(self):
                self.blobs = {}

            def save(self, key, blob):
                self.blobs[key] = blob
                return True

            def load(self, key):
                return self.blobs.get(key)

            def delete(self, key):
                return self.blobs.pop(key, None) is not None

            def list_keys(self):
                return list(self.blobs)

        manager = PersistenceManager(Minimal())
        assert manager.save_data("slot", {"run": 1}) is True
        assert manager.load_data("slot") == {"run": 1}

        manager.storage.blobs["slot"] = b"garbage"
        assert manager.load_data("slot") is None


class TestHeaderRead:
    def test_the_header_is_readable_without_the_payload(self, tmp_path):
        """What a save menu needs: twenty slots' metadata without
        deserialising twenty payloads."""
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        manager.save_data("slot", {"run": 7})

        header = manager.storage.load_header("slot")

        assert header is not None
        assert json.loads(header)["data_type"] == "dict"

    def test_a_missing_key_has_no_header(self, tmp_path):
        backend = FileStorageBackend(base_path=str(tmp_path))
        assert backend.load_header("absent") is None

    def test_a_blob_with_no_newline_has_no_header(self, tmp_path):
        backend = FileStorageBackend(base_path=str(tmp_path))
        backend.save("s", b"no newline anywhere")
        assert backend.load_header("s") is None

    def test_the_scan_is_bounded(self, tmp_path):
        """A corrupt file must not be read into memory in full just to look
        for a newline that is not there."""
        backend = FileStorageBackend(base_path=str(tmp_path))
        backend.save("s", b"x" * 10_000)
        assert backend.load_header("s", max_bytes=128) is None


# --------------------------------------------------------------------------- #
# Save-menu API                                                                #
# --------------------------------------------------------------------------- #
class TestSaveMenuAPI:
    def test_list_saves_reports_written_keys(self, tmp_path):
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        manager.save_data("slot_a", {"a": 1})
        manager.save_data("slot_b", {"b": 2})
        assert sorted(manager.list_saves()) == ["slot_a", "slot_b"]

    def test_exists_and_delete_without_reaching_into_storage(self, tmp_path):
        """Callers used to go through `.storage` for these, which tied game
        code to the backend's interface."""
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        manager.save_data("slot", {"a": 1})

        assert manager.exists("slot") is True
        assert manager.delete("slot") is True
        assert manager.exists("slot") is False
        assert manager.delete("slot") is False

    def test_read_metadata_returns_the_header(self, tmp_path):
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        manager.save_data("slot", {"hp": 3}, save_version=4)

        meta = manager.read_metadata("slot")

        assert meta is not None
        assert meta.data_type == "dict"
        assert meta.save_version == 4
        assert meta.timestamp.tzinfo is not None

    def test_read_metadata_of_a_missing_key_is_none(self, tmp_path):
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        assert manager.read_metadata("absent") is None

    def test_read_metadata_survives_a_corrupt_payload(self, tmp_path):
        """The point of reading only the header: a slot whose *data* is
        broken still shows its timestamp in a load menu."""
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        manager.save_data("slot", {"hp": 3})
        _corrupt_payload(tmp_path / "slot.save")

        meta = manager.read_metadata("slot")

        assert meta is not None
        assert meta.data_type == "dict"

    def test_read_metadata_of_a_broken_header_is_none(self, tmp_path):
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        (tmp_path / "slot.save").write_bytes(b"{not json at all}\npayload")
        assert manager.read_metadata("slot") is None

    def test_read_metadata_tolerates_unknown_future_fields(self, tmp_path):
        """A header written by a newer build must still load, not raise
        `TypeError` on an unexpected keyword."""
        manager = PersistenceManager(FileStorageBackend(base_path=str(tmp_path)))
        manager.save_data("slot", {"hp": 3})

        path = tmp_path / "slot.save"
        header, _sep, payload = path.read_bytes().partition(b"\n")
        raw = json.loads(header)
        raw["something_from_the_future"] = 99
        path.write_bytes(json.dumps(raw).encode("utf-8") + b"\n" + payload)

        meta = manager.read_metadata("slot")
        assert meta is not None
        assert meta.data_type == "dict"

    def test_read_metadata_works_without_a_header_capable_backend(self, tmp_path):
        """`HeaderReadableStorage` is optional; the manager falls back to
        reading the whole blob."""

        class Minimal:
            def __init__(self):
                self.blobs = {}

            def save(self, key, blob):
                self.blobs[key] = blob
                return True

            def load(self, key):
                return self.blobs.get(key)

            def delete(self, key):
                return self.blobs.pop(key, None) is not None

            def list_keys(self):
                return list(self.blobs)

        manager = PersistenceManager(Minimal())
        manager.save_data("slot", {"hp": 3}, save_version=2)

        meta = manager.read_metadata("slot")
        assert meta is not None
        assert meta.save_version == 2
