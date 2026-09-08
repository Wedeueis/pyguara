"""Integration tests for the persistence subsystem.

Covers ``FileStorageBackend`` as a blob store and ``PersistenceManager``
end to end against real files under ``tmp_path``.
"""

import gzip
import json

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
