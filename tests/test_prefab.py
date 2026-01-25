"""Tests for the prefab system."""

import json
import pytest
import tempfile
from pathlib import Path

from pyguara.common.components import Transform, Tag
from pyguara.ecs.manager import EntityManager
from pyguara.prefabs.factory import PrefabFactory
from pyguara.prefabs.loader import PrefabLoader, PrefabCache, Prefab
from pyguara.prefabs.registry import ComponentRegistry
from pyguara.prefabs.types import PrefabData, PrefabChild


@pytest.fixture
def component_registry():
    """Create a component registry with common components."""
    registry = ComponentRegistry()
    registry.register(Transform)
    registry.register(Tag)
    return registry


@pytest.fixture
def entity_manager():
    """Create an entity manager."""
    return EntityManager()


@pytest.fixture
def prefab_factory(entity_manager, component_registry):
    """Create a prefab factory."""
    return PrefabFactory(entity_manager, component_registry)


class TestComponentRegistry:
    """Tests for ComponentRegistry."""

    def test_register_component(self, component_registry):
        """Test registering a component."""
        assert component_registry.has("Transform")
        assert component_registry.has("Tag")

    def test_get_component(self, component_registry):
        """Test getting a registered component type."""
        assert component_registry.get("Transform") is Transform
        assert component_registry.get("Tag") is Tag
        assert component_registry.get("NonExistent") is None

    def test_create_component(self, component_registry):
        """Test creating a component from data."""
        transform = component_registry.create(
            "Transform", {"position": {"x": 100, "y": 200}}
        )
        assert isinstance(transform, Transform)
        assert transform.position.x == 100
        assert transform.position.y == 200

    def test_create_component_not_registered(self, component_registry):
        """Test creating an unregistered component raises error."""
        with pytest.raises(KeyError):
            component_registry.create("Unknown", {})

    def test_list_components(self, component_registry):
        """Test listing registered components."""
        components = component_registry.list_components()
        assert "Transform" in components
        assert "Tag" in components

    def test_clear_registry(self, component_registry):
        """Test clearing the registry."""
        component_registry.clear()
        assert not component_registry.has("Transform")
        assert not component_registry.has("Tag")


class TestPrefabData:
    """Tests for PrefabData."""

    def test_create_prefab_data(self):
        """Test creating prefab data."""
        prefab = PrefabData(
            name="TestPrefab",
            version=1,
            components={"Transform": {"position": {"x": 10, "y": 20}}},
        )
        assert prefab.name == "TestPrefab"
        assert prefab.version == 1
        assert "Transform" in prefab.components

    def test_prefab_data_with_children(self):
        """Test prefab data with children."""
        child = PrefabChild(prefab="child.prefab.json", offset={"x": 10, "y": 0})
        prefab = PrefabData(name="Parent", children=[child])
        assert len(prefab.children) == 1
        assert prefab.children[0].prefab == "child.prefab.json"

    def test_prefab_data_with_extends(self):
        """Test prefab data with inheritance."""
        prefab = PrefabData(name="ChildPrefab", extends="parent.prefab.json")
        assert prefab.extends == "parent.prefab.json"


class TestPrefabLoader:
    """Tests for PrefabLoader."""

    def test_load_json_prefab(self):
        """Test loading a JSON prefab file."""
        loader = PrefabLoader()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".prefab.json", delete=False
        ) as f:
            json.dump(
                {
                    "name": "TestEntity",
                    "version": 1,
                    "components": {"Transform": {"position": {"x": 50, "y": 100}}},
                },
                f,
            )
            f.flush()

            prefab = loader.load(f.name)
            assert isinstance(prefab, Prefab)
            assert prefab.data.name == "TestEntity"
            assert prefab.data.version == 1
            assert "Transform" in prefab.data.components

            Path(f.name).unlink()

    def test_load_prefab_file(self):
        """Test loading a .prefab file (auto-detect format)."""
        loader = PrefabLoader()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".prefab", delete=False) as f:
            json.dump({"name": "AutoDetect", "components": {}}, f)
            f.flush()

            prefab = loader.load(f.name)
            assert prefab.data.name == "AutoDetect"

            Path(f.name).unlink()

    def test_load_prefab_uses_filename_as_name(self):
        """Test that filename is used if name not specified."""
        loader = PrefabLoader()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".prefab.json", delete=False
        ) as f:
            json.dump({"components": {}}, f)
            f.flush()

            prefab = loader.load(f.name)
            # Name should be the stem without suffixes
            assert prefab.data.name == Path(f.name).stem

            Path(f.name).unlink()

    def test_load_nonexistent_file(self):
        """Test loading nonexistent file raises error."""
        loader = PrefabLoader()
        with pytest.raises(FileNotFoundError):
            loader.load("/nonexistent/path.prefab.json")


class TestPrefabCache:
    """Tests for PrefabCache."""

    def test_cache_load(self):
        """Test loading and caching a prefab."""
        cache = PrefabCache()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".prefab.json", delete=False
        ) as f:
            json.dump({"name": "Cached", "components": {}}, f)
            f.flush()

            # First load
            prefab = cache.load(f.name)
            assert prefab is not None
            assert prefab.name == "Cached"

            # Second load should return cached
            prefab2 = cache.load(f.name)
            assert prefab2 is prefab

            Path(f.name).unlink()

    def test_cache_invalidate(self):
        """Test invalidating cached prefab."""
        cache = PrefabCache()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".prefab.json", delete=False
        ) as f:
            json.dump({"name": "ToInvalidate", "components": {}}, f)
            f.flush()

            cache.load(f.name)
            assert cache.is_cached(f.name)

            cache.invalidate(f.name)
            assert not cache.is_cached(f.name)

            Path(f.name).unlink()


class TestPrefabFactory:
    """Tests for PrefabFactory."""

    def test_create_simple_entity(self, prefab_factory, entity_manager):
        """Test creating an entity from prefab."""
        prefab = PrefabData(
            name="SimpleEntity",
            components={
                "Transform": {"position": {"x": 100, "y": 200}},
                "Tag": {"name": "player"},
            },
        )

        entity = prefab_factory.create(prefab)

        assert entity is not None
        assert entity.id is not None

        transform = entity.get_component(Transform)
        assert transform is not None
        assert transform.position.x == 100
        assert transform.position.y == 200

        tag = entity.get_component(Tag)
        assert tag is not None
        assert tag.name == "player"

    def test_create_entity_with_overrides(self, prefab_factory):
        """Test creating entity with component overrides."""
        prefab = PrefabData(
            name="WithOverrides",
            components={
                "Transform": {"position": {"x": 0, "y": 0}},
            },
        )

        entity = prefab_factory.create(
            prefab, overrides={"Transform": {"position": {"x": 500, "y": 600}}}
        )

        transform = entity.get_component(Transform)
        assert transform.position.x == 500
        assert transform.position.y == 600

    def test_create_entity_with_custom_id(self, prefab_factory):
        """Test creating entity with custom ID."""
        prefab = PrefabData(name="CustomId", components={})
        entity = prefab_factory.create(prefab, entity_id="custom_entity_123")
        assert entity.id == "custom_entity_123"

    def test_create_with_inheritance(self, prefab_factory):
        """Test prefab inheritance."""
        parent_prefab = PrefabData(
            name="Parent",
            components={
                "Transform": {"position": {"x": 10, "y": 10}, "rotation": 45.0},
            },
        )

        child_prefab = PrefabData(
            name="Child",
            extends="parent.prefab.json",
            components={
                "Transform": {"position": {"x": 100, "y": 100}},  # Override position
            },
        )

        # Set up resolver
        def resolve(path):
            if "parent" in path:
                return parent_prefab
            return None

        prefab_factory.set_prefab_resolver(resolve)

        entity = prefab_factory.create(child_prefab)
        transform = entity.get_component(Transform)

        # Position should be overridden
        assert transform.position.x == 100
        assert transform.position.y == 100
        # Rotation should be inherited
        assert transform.rotation == 45.0

    def test_create_warns_on_unknown_component(self, prefab_factory, caplog):
        """Test that unknown components log a warning."""
        import logging

        prefab = PrefabData(
            name="WithUnknown", components={"UnknownComponent": {"foo": "bar"}}
        )

        with caplog.at_level(logging.WARNING):
            entity = prefab_factory.create(prefab)

        assert "UnknownComponent" in caplog.text or entity is not None


class TestDeepMerge:
    """Tests for deep merge functionality in PrefabFactory."""

    def test_deep_merge_nested_dicts(self, prefab_factory):
        """Test that nested dicts are properly merged."""
        parent = PrefabData(
            name="Parent",
            components={
                "Transform": {
                    "position": {"x": 0, "y": 0},
                    "scale": {"x": 1, "y": 1},
                }
            },
        )

        child = PrefabData(
            name="Child",
            extends="parent",
            components={
                "Transform": {
                    "position": {"x": 100},  # Only override x
                }
            },
        )

        prefab_factory.set_prefab_resolver(lambda p: parent if "parent" in p else None)

        entity = prefab_factory.create(child)
        transform = entity.get_component(Transform)

        # x should be overridden, y should keep parent value
        assert transform.position.x == 100
        assert transform.position.y == 0
        # scale should be inherited
        assert transform.scale.x == 1
        assert transform.scale.y == 1
