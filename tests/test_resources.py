import pytest
from unittest.mock import MagicMock, patch
from pyguara.resources.manager import ResourceManager
from pyguara.resources.loader import IResourceLoader
from pyguara.resources.types import Resource


class MockRes(Resource):
    @property
    def native_handle(self) -> str:
        return "mock"


class MockLoader(IResourceLoader):
    @property
    def supported_extensions(self) -> list[str]:
        return [".mock"]

    def load(self, path: str) -> MockRes:
        return MockRes(path)


def test_resource_caching() -> None:
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


def test_loader_selection() -> None:
    manager = ResourceManager()
    loader = MockLoader()
    manager.register_loader(loader)

    # Should select MockLoader for .mock extension
    res = manager.load("file.mock", MockRes)
    assert isinstance(res, MockRes)


def test_wrong_type_error() -> None:
    manager = ResourceManager()
    manager.register_loader(MockLoader())

    class OtherRes(Resource):
        @property
        def native_handle(self) -> None:
            return None

    with pytest.raises(TypeError):
        manager.load("file.mock", OtherRes)


def test_indexing() -> None:
    manager = ResourceManager()
    manager.register_loader(MockLoader())

    with patch("pathlib.Path.rglob") as mock_glob:
        mock_file = MagicMock()
        mock_file.is_file.return_value = True
        mock_file.suffix = ".mock"
        mock_file.stem = "hero"
        mock_file.name = "hero.mock"
        # Configure __str__ to return the path
        type(mock_file).__str__ = lambda self: "assets/hero.mock"  # type: ignore[method-assign]

        mock_glob.return_value = [mock_file]

        with patch("pathlib.Path.exists", return_value=True):
            manager.index_directory("assets")

    assert "hero" in manager._path_index
    assert manager._path_index["hero"] == "assets/hero.mock"


def test_reference_counting_basic() -> None:
    """Test that load increments ref count and release decrements it."""
    manager = ResourceManager()
    manager.register_loader(MockLoader())

    # Load resource - should set ref count to 1
    res1 = manager.load("test.mock", MockRes)
    assert "test.mock" in manager._reference_counts
    assert manager._reference_counts["test.mock"] == 1

    # Load again - should increment to 2
    res2 = manager.load("test.mock", MockRes)
    assert res1 is res2  # Same instance
    assert manager._reference_counts["test.mock"] == 2

    # Release once - ref count should be 1
    manager.release("test.mock")
    assert manager._reference_counts["test.mock"] == 1
    assert "test.mock" in manager._cache  # Still cached

    # Release again - ref count reaches 0, auto-unload
    manager.release("test.mock")
    assert "test.mock" not in manager._cache
    assert "test.mock" not in manager._reference_counts


def test_acquire_release() -> None:
    """Test explicit acquire and release methods."""
    manager = ResourceManager()
    manager.register_loader(MockLoader())

    # Load resource (ref count = 1)
    manager.load("test.mock", MockRes)
    assert manager._reference_counts["test.mock"] == 1

    # Acquire additional reference (ref count = 2)
    manager.acquire("test.mock")
    assert manager._reference_counts["test.mock"] == 2

    # Release once (ref count = 1)
    manager.release("test.mock")
    assert "test.mock" in manager._cache

    # Release again (ref count = 0, auto-unload)
    manager.release("test.mock")
    assert "test.mock" not in manager._cache


def test_acquire_unloaded_resource_error() -> None:
    """Test that acquire raises error for unloaded resource."""
    manager = ResourceManager()
    manager.register_loader(MockLoader())

    with pytest.raises(KeyError, match="Cannot acquire reference to unloaded resource"):
        manager.acquire("nonexistent.mock")


def test_release_unloaded_resource_error() -> None:
    """Test that release raises error for unloaded resource."""
    manager = ResourceManager()
    manager.register_loader(MockLoader())

    with pytest.raises(KeyError, match="Cannot release reference to unloaded resource"):
        manager.release("nonexistent.mock")


def test_release_zero_refcount_error() -> None:
    """Test that release raises error when ref count is already zero."""
    manager = ResourceManager()
    manager.register_loader(MockLoader())

    # Load and then release to zero
    manager.load("test.mock", MockRes)
    manager.release("test.mock")

    # Try to release again - should error
    with pytest.raises(KeyError):
        manager.release("test.mock")


def test_unload_unused() -> None:
    """Test batch unloading of zero-ref resources."""
    manager = ResourceManager()
    manager.register_loader(MockLoader())

    # Load 3 resources
    manager.load("res1.mock", MockRes)
    manager.load("res2.mock", MockRes)
    manager.load("res3.mock", MockRes)

    # Release res1 and res2 to zero
    manager.release("res1.mock")
    manager.release("res2.mock")

    # res3 still has ref count 1, acquire another ref for res1
    manager._reference_counts["res1.mock"] = 0  # Manually set to simulate zero refs
    manager._cache["res1.mock"] = MockRes("res1.mock")  # Re-add to cache

    # Batch unload
    count = manager.unload_unused()

    # Should have unloaded res1 (0 refs) but not res3 (1 ref)
    assert count >= 1
    assert "res3.mock" in manager._cache
    assert manager._reference_counts["res3.mock"] == 1


def test_force_unload() -> None:
    """Test force unload bypasses reference counting."""
    manager = ResourceManager()
    manager.register_loader(MockLoader())

    # Load resource (ref count = 1)
    manager.load("test.mock", MockRes)
    assert manager._reference_counts["test.mock"] == 1

    # Force unload should work even with active references
    manager.unload("test.mock", force=True)
    assert "test.mock" not in manager._cache
    assert "test.mock" not in manager._reference_counts


def test_cache_stats() -> None:
    """Test get_cache_stats returns correct information."""
    manager = ResourceManager()
    manager.register_loader(MockLoader())

    # Load 2 resources
    manager.load("res1.mock", MockRes)
    manager.load("res2.mock", MockRes)

    # Acquire additional ref for res1
    manager.acquire("res1.mock")

    stats = manager.get_cache_stats()

    assert stats["resource_count"] == 2
    assert stats["total_references"] == 3  # res1=2, res2=1
    assert "res1.mock" in stats["resources"]
    assert stats["resources"]["res1.mock"]["ref_count"] == 2
    assert stats["resources"]["res2.mock"]["ref_count"] == 1
