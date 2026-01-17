"""Integration tests for Resource Loaders using real files."""

import pytest
import json
import tempfile
from pathlib import Path
from typing import Generator

from pyguara.resources.loaders.data_loader import JsonLoader
from pyguara.resources.manager import ResourceManager
from pyguara.resources.types import Resource


class MockDataResource(Resource):
    """Mock resource to hold JSON data."""

    def __init__(self, path: str, data: dict):
        super().__init__(path)
        self.data = data

    @property
    def native_handle(self) -> dict:
        return self.data


@pytest.fixture
def temp_assets() -> Generator[Path, None, None]:
    """Create a temporary directory with asset files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir)

        # Create a valid JSON file
        data = {"name": "Test", "value": 42}
        json_path = path / "test.json"
        with open(json_path, "w") as f:
            json.dump(data, f)

        yield path


def test_json_loader_success(temp_assets: Path) -> None:
    """JsonLoader should load valid JSON files."""
    loader = JsonLoader()
    file_path = str(temp_assets / "test.json")

    resource = loader.load(file_path)

    assert resource is not None
    assert resource.path == file_path
    # DataResource exposes dict via native_handle
    assert resource.native_handle["name"] == "Test"
    assert resource.native_handle["value"] == 42


def test_json_loader_file_not_found() -> None:
    """JsonLoader should raise FileNotFoundError for missing files."""
    loader = JsonLoader()
    with pytest.raises(FileNotFoundError):
        loader.load("non_existent_file.json")


def test_json_loader_invalid_json(temp_assets: Path) -> None:
    """JsonLoader should raise JSONDecodeError for invalid content."""
    loader = JsonLoader()
    file_path = temp_assets / "bad.json"
    with open(file_path, "w") as f:
        f.write("{ invalid json")

    with pytest.raises(json.JSONDecodeError):
        loader.load(str(file_path))


def test_resource_manager_integration(temp_assets: Path) -> None:
    """ResourceManager should use JsonLoader correctly."""
    manager = ResourceManager()
    manager.register_loader(JsonLoader())

    file_path = str(temp_assets / "test.json")
    # Note: JsonLoader returns DataResource, but we check base Resource properties
    resource = manager.load(file_path, Resource)

    assert resource.path == file_path
    # Check if native handle is dict
    assert isinstance(resource.native_handle, dict)
    assert resource.native_handle["name"] == "Test"
