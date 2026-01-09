import pytest
from unittest.mock import MagicMock, patch
from pyguara.resources.manager import ResourceManager
from pyguara.resources.loader import IResourceLoader
from pyguara.resources.types import Resource


class MockRes(Resource):
    @property
    def native_handle(self):
        return "mock"


class MockLoader(IResourceLoader):
    @property
    def supported_extensions(self):
        return [".mock"]

    def load(self, path):
        return MockRes(path)


def test_resource_caching():
    manager = ResourceManager()
    loader = MockLoader()
    manager.register_loader(loader)

    # Mock index
    manager._path_index["test"] = "assets/test.mock"

    # 1. Load (Cache Miss)
    res1 = manager.load("test", MockRes)
    assert res1.path == "assets/test.mock"

    # 2. Load (Cache Hit)
    res2 = manager.load("test", MockRes)
    assert res1 is res2  # Same instance


def test_loader_selection():
    manager = ResourceManager()
    loader = MockLoader()
    manager.register_loader(loader)

    # Should select MockLoader for .mock extension
    res = manager.load("file.mock", MockRes)
    assert isinstance(res, MockRes)


def test_wrong_type_error():
    manager = ResourceManager()
    manager.register_loader(MockLoader())

    class OtherRes(Resource):
        @property
        def native_handle(self):
            return None

    with pytest.raises(TypeError):
        manager.load("file.mock", OtherRes)


def test_indexing():
    manager = ResourceManager()
    manager.register_loader(MockLoader())

    with patch("pathlib.Path.rglob") as mock_glob:
        mock_file = MagicMock()
        mock_file.is_file.return_value = True
        mock_file.suffix = ".mock"
        mock_file.stem = "hero"
        mock_file.name = "hero.mock"
        mock_file.__str__.return_value = "assets/hero.mock"

        mock_glob.return_value = [mock_file]

        with patch("pathlib.Path.exists", return_value=True):
            manager.index_directory("assets")

    assert "hero" in manager._path_index
    assert manager._path_index["hero"] == "assets/hero.mock"
