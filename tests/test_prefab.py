"""Tests for the prefab system."""

import dataclasses
import enum
import json
import tempfile
from pathlib import Path

import pytest

from pyguara.common.components import Tag, Transform
from pyguara.common.types import Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.ecs.manager import EntityManager
from pyguara.prefabs.factory import PrefabFactory
from pyguara.prefabs.loader import Prefab, PrefabCache, PrefabLoader
from pyguara.prefabs.registry import ComponentRegistry
from pyguara.prefabs.types import PrefabChild, PrefabData, PrefabInstance


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
        """An unregistered component is skipped with a warning, not fatal."""
        import logging

        prefab = PrefabData(
            name="WithUnknown",
            components={
                "Tag": {"name": "ok"},
                "UnknownComponent": {"foo": "bar"},
            },
        )

        with caplog.at_level(logging.WARNING):
            entity = prefab_factory.create(prefab)

        assert "UnknownComponent" in caplog.text
        # The registered component still lands; only the unknown one is dropped.
        assert entity.get_component(Tag).name == "ok"


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


class Facing(enum.Enum):
    """Non-SCREAMING_CASE enum: the old `value.upper()` path could not build it."""

    left = 1
    right = 2


@dataclasses.dataclass
class Mover(BaseComponent):
    """A component with an enum field and a non-Transform Vector2 field."""

    facing: Facing = Facing.left
    speed: float = 0.0
    anchor: Vector2 = dataclasses.field(default_factory=lambda: Vector2(0, 0))


@pytest.fixture
def registry_with_mover(component_registry):
    component_registry.register(Mover)
    return component_registry


@pytest.fixture
def factory_with_mover(entity_manager, registry_with_mover):
    return PrefabFactory(entity_manager, registry_with_mover)


class TestPrefabChildren:
    """`_create_children` had zero tests; the headline defect lived here."""

    def _resolver(self, mapping):
        return lambda path: mapping.get(path)

    def test_children_do_not_raise_with_a_resolver_set(
        self, prefab_factory, entity_manager
    ):
        """Regression: a prefab with children used to hit a nonexistent
        `Entity.get_component_by_name` and raise AttributeError whenever a
        resolver was set (every real Scene sets one)."""
        child = PrefabData(
            name="Child", components={"Transform": {"position": {"x": 0, "y": 0}}}
        )
        parent = PrefabData(
            name="Parent",
            components={"Transform": {"position": {"x": 100, "y": 100}}},
            children=[PrefabChild(prefab="child", name="the_child")],
        )
        prefab_factory.set_prefab_resolver(self._resolver({"child": child}))

        prefab_factory.create(parent)  # must not raise

        assert entity_manager.get_entity("the_child") is not None

    def test_child_transform_is_parented_and_follows_the_parent(
        self, prefab_factory, entity_manager
    ):
        child = PrefabData(
            name="Child", components={"Transform": {"position": {"x": 0, "y": 0}}}
        )
        parent = PrefabData(
            name="Parent",
            components={"Transform": {"position": {"x": 100, "y": 100}}},
            children=[
                PrefabChild(prefab="child", name="kid", offset={"x": 10, "y": 0})
            ],
        )
        prefab_factory.set_prefab_resolver(self._resolver({"child": child}))

        parent_entity = prefab_factory.create(parent)
        child_t = entity_manager.get_entity("kid").get_component(Transform)
        parent_t = parent_entity.get_component(Transform)

        assert child_t.parent is parent_t
        # offset is applied in the parent's local space
        assert (child_t.position.x, child_t.position.y) == (10, 0)
        assert (child_t.world_position.x, child_t.world_position.y) == (110, 100)

        parent_t.position = Vector2(200, 100)
        assert (child_t.world_position.x, child_t.world_position.y) == (210, 100)

    def test_child_records_its_source_path(self, prefab_factory, entity_manager):
        child = PrefabData(name="Child", components={"Tag": {"name": "c"}})
        parent = PrefabData(
            name="Parent",
            components={"Tag": {"name": "p"}},
            children=[PrefabChild(prefab="enemies/child.prefab.json", name="kid")],
        )
        prefab_factory.set_prefab_resolver(
            self._resolver({"enemies/child.prefab.json": child})
        )

        prefab_factory.create(parent)
        kid = entity_manager.get_entity("kid")
        assert (
            kid.get_component(PrefabInstance).prefab_path == "enemies/child.prefab.json"
        )

    def test_children_without_resolver_are_skipped_with_a_warning(
        self, prefab_factory, entity_manager, caplog
    ):
        import logging

        parent = PrefabData(
            name="Parent",
            components={"Tag": {"name": "p"}},
            children=[PrefabChild(prefab="child")],
        )
        # no resolver set
        with caplog.at_level(logging.WARNING):
            entity = prefab_factory.create(parent)

        assert "resolver" in caplog.text.lower()
        assert list(entity_manager.get_all_entities()) == [entity]

    def test_offset_without_a_child_transform_warns(
        self, prefab_factory, entity_manager, caplog
    ):
        import logging

        child = PrefabData(name="Child", components={"Tag": {"name": "c"}})
        parent = PrefabData(
            name="Parent",
            components={"Transform": {"position": {"x": 0, "y": 0}}},
            children=[PrefabChild(prefab="child", name="kid", offset={"x": 5, "y": 5})],
        )
        prefab_factory.set_prefab_resolver(self._resolver({"child": child}))

        with caplog.at_level(logging.WARNING):
            prefab_factory.create(parent)

        assert "offset" in caplog.text.lower()


class TestPrefabInheritanceCycle:
    def test_direct_self_reference_raises_valueerror(self, prefab_factory):
        prefab = PrefabData(name="A", extends="a", components={"Tag": {"name": "a"}})
        prefab_factory.set_prefab_resolver(lambda p: prefab)

        with pytest.raises(ValueError, match="cycle"):
            prefab_factory.create(prefab)

    def test_mutual_reference_raises_and_names_the_chain(self, prefab_factory):
        a = PrefabData(name="A", extends="b", components={"Tag": {"name": "a"}})
        b = PrefabData(name="B", extends="a", components={"Tag": {"name": "b"}})
        prefab_factory.set_prefab_resolver(lambda p: a if p == "a" else b)

        with pytest.raises(ValueError, match="a -> b -> a|b -> a -> b"):
            prefab_factory.create(a)


class TestPrefabInstanceMetadata:
    def test_in_memory_prefab_records_its_name(self, prefab_factory):
        entity = prefab_factory.create(PrefabData(name="Goblin", components={}))
        assert entity.get_component(PrefabInstance).prefab_path == "Goblin"

    def test_create_from_path_records_the_path(self, prefab_factory):
        pf = PrefabData(name="Goblin", components={"Tag": {"name": "enemy"}})
        prefab_factory.set_prefab_resolver(lambda p: pf)

        entity = prefab_factory.create_from_path("assets/prefabs/goblin.prefab.json")

        assert (
            entity.get_component(PrefabInstance).prefab_path
            == "assets/prefabs/goblin.prefab.json"
        )

    def test_overrides_are_recorded(self, prefab_factory):
        entity = prefab_factory.create(
            PrefabData(name="P", components={"Tag": {"name": "a"}}),
            overrides={"Tag": {"name": "b"}},
        )
        assert entity.get_component(PrefabInstance).instance_overrides == {
            "Tag": {"name": "b"}
        }


class TestPrefabFactoryFailsLoud:
    def test_unknown_field_raises(self, prefab_factory):
        prefab = PrefabData(
            name="P", components={"Tag": {"name": "ok", "colour": "red"}}
        )
        with pytest.raises(ValueError, match="no field"):
            prefab_factory.create(prefab)

    def test_bad_enum_value_raises(self, factory_with_mover):
        prefab = PrefabData(name="P", components={"Mover": {"facing": "sideways"}})
        with pytest.raises(ValueError, match="not a valid Facing"):
            factory_with_mover.create(prefab)


class TestComponentRegistryConversion:
    @pytest.mark.parametrize("given", ["left", "LEFT", "Left", 1])
    def test_enum_field_accepts_name_any_case_or_raw_value(
        self, registry_with_mover, given
    ):
        mover = registry_with_mover.create("Mover", {"facing": given})
        assert mover.facing is Facing.left

    def test_non_transform_vector2_field_is_converted(self, registry_with_mover):
        mover = registry_with_mover.create("Mover", {"anchor": {"x": 3, "y": 4}})
        assert isinstance(mover.anchor, Vector2)
        assert (mover.anchor.x, mover.anchor.y) == (3, 4)

    def test_unknown_field_raises(self, registry_with_mover):
        with pytest.raises(ValueError, match="no field"):
            registry_with_mover.create("Mover", {"speeed": 1.0})

    def test_clear_leaves_registry_able_to_round_trip_transform(self):
        registry = ComponentRegistry()
        registry.register(Transform)
        registry.clear()
        # Transform is not a dataclass and has a custom __init__; only the
        # re-seeded builtin deserializer can rebuild it from raw dict data.
        registry.register(Transform)

        t = registry.create("Transform", {"position": {"x": 1, "y": 2}})

        assert isinstance(t, Transform)
        assert (t.position.x, t.position.y) == (1, 2)

    def test_clear_drops_user_registrations(self):
        registry = ComponentRegistry()
        registry.register(Tag)
        registry.clear()
        assert not registry.has("Tag")


class TestPrefabLoaderRejectsMalformed:
    @pytest.mark.parametrize(
        "body,suffix",
        [("[1, 2, 3]", ".prefab.json"), ("- a\n- b\n", ".prefab")],
    )
    def test_non_mapping_top_level_raises_valueerror(self, body, suffix):
        loader = PrefabLoader()
        with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False) as f:
            f.write(body)
            f.flush()
            try:
                with pytest.raises(ValueError, match="mapping"):
                    loader.load(f.name)
            finally:
                Path(f.name).unlink()


class TestPrefabRoundTrip:
    """No existing test went file -> PrefabLoader -> PrefabFactory."""

    def test_load_then_instantiate(self, prefab_factory):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".prefab.json", delete=False
        ) as f:
            json.dump(
                {
                    "name": "Crate",
                    "components": {
                        "Transform": {"position": {"x": 12, "y": 34}},
                        "Tag": {"name": "prop"},
                    },
                },
                f,
            )
            f.flush()
            try:
                data = PrefabLoader().load(f.name).data
                entity = prefab_factory.create(data, source_path=f.name)
            finally:
                Path(f.name).unlink()

        assert entity.get_component(Transform).position.x == 12
        assert entity.get_component(Tag).name == "prop"
        assert entity.get_component(PrefabInstance).prefab_path == f.name
