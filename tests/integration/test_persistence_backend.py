"""Integration tests for Persistence System backend."""

import pytest
import tempfile
import json
from pathlib import Path
from typing import Generator

from pyguara.persistence.storage import FileStorageBackend
from pyguara.persistence.manager import PersistenceManager


@pytest.fixture
def temp_storage_path() -> Generator[Path, None, None]:
    """Create a temporary directory for saves."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


def test_file_storage_save_load(temp_storage_path: Path) -> None:
    """FileStorageBackend should save and load data."""
    backend = FileStorageBackend(base_path=str(temp_storage_path))

    data = {"player_xp": 100, "level": 2}
    data_bytes = json.dumps(data).encode("utf-8")
    meta = {"version": 1}

    # Save
    backend.save("save1", data_bytes, meta)

    # Check file exists
    assert (temp_storage_path / "save1.dat").exists()
    assert (temp_storage_path / "save1.meta").exists()

    # Load
    loaded = backend.load("save1")
    assert loaded is not None
    loaded_data, loaded_meta = loaded
    assert loaded_data == data_bytes
    assert loaded_meta == meta


def test_file_storage_missing_file(temp_storage_path: Path) -> None:
    """FileStorageBackend should handle missing files."""
    backend = FileStorageBackend(base_path=str(temp_storage_path))

    # Load nonexistent
    assert backend.load("ghost") is None

    # Delete nonexistent (should return False)
    assert not backend.delete("ghost")


def test_file_storage_list_slots(temp_storage_path: Path) -> None:
    """FileStorageBackend should list available save slots."""
    backend = FileStorageBackend(base_path=str(temp_storage_path))

    backend.save("slot_a", b"", {})
    backend.save("slot_b", b"", {})

    slots = backend.list_keys()
    assert len(slots) == 2
    assert "slot_a" in slots
    assert "slot_b" in slots


def test_persistence_manager_integration(temp_storage_path: Path) -> None:
    """PersistenceManager should coordinate with backend."""
    storage = FileStorageBackend(base_path=str(temp_storage_path))
    manager = PersistenceManager(storage)

    game_data = {"score": 500}

    # Save
    manager.save_data("autosave", game_data)

    # Verify metadata added
    raw = storage.load("autosave")
    assert raw is not None
    data_bytes, meta = raw

    # PersistenceManager serializes to JSON bytes by default
    assert json.loads(data_bytes.decode("utf-8")) == game_data
    assert "timestamp" in meta

    # Load
    loaded_data = manager.load_data("autosave")
    assert loaded_data == game_data
