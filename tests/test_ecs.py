import warnings
from dataclasses import dataclass

import pytest

from pyguara.ecs.manager import EntityManager
from pyguara.ecs.component import BaseComponent, StrictComponent
from pyguara.ecs.entity import Entity


# -- Mocks --
@dataclass
class Position(BaseComponent):
    x: float = 0
    y: float = 0


@dataclass
class Health(BaseComponent):
    hp: int = 100


@dataclass
class Velocity(BaseComponent):
    vx: float = 0


def test_create_entity() -> None:
    manager = EntityManager()
    entity = manager.create_entity()
    assert entity.id is not None
    assert manager.get_entity(entity.id) == entity


def test_add_component() -> None:
    manager = EntityManager()
    entity = manager.create_entity()

    pos = Position(10, 20)
    entity.add_component(pos)

    assert entity.has_component(Position)
    assert entity.get_component(Position) == pos
    # Check attribute cache
    assert entity.position == pos


def test_ecs_query() -> None:
    manager = EntityManager()

    # Ent 1: Pos + Health
    e1 = manager.create_entity()
    e1.add_component(Position())
    e1.add_component(Health())

    # Ent 2: Pos only
    e2 = manager.create_entity()
    e2.add_component(Position())

    # Ent 3: Health only
    e3 = manager.create_entity()
    e3.add_component(Health())

    # Query: Position + Health
    results = list(manager.get_entities_with(Position, Health))

    assert len(results) == 1
    assert results[0] == e1

    # Query: Position
    results_pos = list(manager.get_entities_with(Position))
    assert len(results_pos) == 2
    assert set(results_pos) == {e1, e2}


def test_remove_entity() -> None:
    manager = EntityManager()
    e1 = manager.create_entity()
    e1.add_component(Position())

    eid = e1.id
    manager.remove_entity(eid)

    assert manager.get_entity(eid) is None
    # Index should be clear
    assert len(list(manager.get_entities_with(Position))) == 0


def test_component_added_after_registration() -> None:
    """Ensure adding a component *after* entity creation updates the manager's index."""
    manager = EntityManager()
    e1 = manager.create_entity()

    # Initially has no Position
    assert len(list(manager.get_entities_with(Position))) == 0

    # Add component dynamically
    e1.add_component(Position())

    # Manager should know about it now (via Observer hook)
    assert len(list(manager.get_entities_with(Position))) == 1


def test_snake_case_conversion() -> None:
    """Verify the naming optimization logic."""

    class RigidBody(BaseComponent):
        pass

    class AIController(BaseComponent):
        pass

    assert Entity._get_snake_name(Position) == "position"
    assert Entity._get_snake_name(RigidBody) == "rigid_body"
    # Note: Regex logic for AIController might depend on implementation details
    # standard regex: AIController -> ai_controller (usually) or a_i_controller
    # Let's verify what the actual impl does:
    # s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", type_name)
    # s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
    # AIController -> AI_Controller -> ai_controller
    assert Entity._get_snake_name(AIController) == "ai_controller"


# ==================== Component Removal Tests (P0-001) ====================


def test_component_removal_updates_index() -> None:
    """Ensure removing a component updates manager's inverted index.

    This is the core test for P0-001. Previously, removing a component
    would leave stale entries in the index, causing queries to return
    entities without the component.
    """
    manager = EntityManager()
    e1 = manager.create_entity()
    e1.add_component(Position())

    # Verify component is in index
    assert len(list(manager.get_entities_with(Position))) == 1

    # Remove component
    e1.remove_component(Position)

    # CRITICAL: Index should now be empty
    assert len(list(manager.get_entities_with(Position))) == 0

    # Verify component is actually removed from entity
    assert not e1.has_component(Position)


def test_partial_removal_from_multiple_entities() -> None:
    """Removing a component from one entity shouldn't affect others.

    This tests that the index update is surgical - only the specific
    entity is removed from the component index.
    """
    manager = EntityManager()
    e1 = manager.create_entity()
    e2 = manager.create_entity()
    e3 = manager.create_entity()

    # All three entities have Position
    e1.add_component(Position())
    e2.add_component(Position())
    e3.add_component(Position())

    # All 3 should be in the query
    assert len(list(manager.get_entities_with(Position))) == 3

    # Remove Position from e2 only
    e2.remove_component(Position)

    # Should have exactly 2 entities now
    results = list(manager.get_entities_with(Position))
    assert len(results) == 2
    assert set(results) == {e1, e3}

    # Verify e2 no longer has the component
    assert not e2.has_component(Position)


def test_multiple_components_removed_from_same_entity() -> None:
    """Test removing multiple components from the same entity.

    Ensures the index stays consistent when multiple components
    are removed sequentially.
    """
    manager = EntityManager()
    e1 = manager.create_entity()

    # Add multiple components
    e1.add_component(Position())
    e1.add_component(Health())
    e1.add_component(Velocity())

    # Verify all are indexed
    assert len(list(manager.get_entities_with(Position))) == 1
    assert len(list(manager.get_entities_with(Health))) == 1
    assert len(list(manager.get_entities_with(Velocity))) == 1

    # Remove Position
    e1.remove_component(Position)
    assert len(list(manager.get_entities_with(Position))) == 0
    assert len(list(manager.get_entities_with(Health))) == 1  # Still there
    assert len(list(manager.get_entities_with(Velocity))) == 1  # Still there

    # Remove Health
    e1.remove_component(Health)
    assert len(list(manager.get_entities_with(Position))) == 0
    assert len(list(manager.get_entities_with(Health))) == 0
    assert len(list(manager.get_entities_with(Velocity))) == 1  # Still there

    # Remove Velocity
    e1.remove_component(Velocity)
    assert len(list(manager.get_entities_with(Position))) == 0
    assert len(list(manager.get_entities_with(Health))) == 0
    assert len(list(manager.get_entities_with(Velocity))) == 0


def test_remove_nonexistent_component() -> None:
    """Removing a component that doesn't exist should be a no-op.

    This is an edge case - the current implementation silently ignores
    removal of components that don't exist.
    """
    manager = EntityManager()
    e1 = manager.create_entity()

    # Entity has no components
    assert len(list(manager.get_entities_with(Position))) == 0

    # Try to remove non-existent component (should not raise)
    e1.remove_component(Position)  # No-op

    # Still no entities with Position
    assert len(list(manager.get_entities_with(Position))) == 0


def test_query_after_removal_returns_correct_components() -> None:
    """Verify that queries after removal return entities with correct components.

    This integration test ensures the whole system works: add, remove, query.
    """
    manager = EntityManager()

    # Create entities with different component combinations
    e1 = manager.create_entity()
    e1.add_component(Position())
    e1.add_component(Health())

    e2 = manager.create_entity()
    e2.add_component(Position())
    e2.add_component(Health())

    e3 = manager.create_entity()
    e3.add_component(Position())

    # All have Position
    assert len(list(manager.get_entities_with(Position))) == 3

    # Two have Health
    assert len(list(manager.get_entities_with(Health))) == 2

    # Remove Health from e1
    e1.remove_component(Health)

    # Now only e2 has Health
    health_entities = list(manager.get_entities_with(Health))
    assert len(health_entities) == 1
    assert health_entities[0] == e2

    # All still have Position
    assert len(list(manager.get_entities_with(Position))) == 3

    # Query for Position + Health should return only e2
    combo_entities = list(manager.get_entities_with(Position, Health))
    assert len(combo_entities) == 1
    assert combo_entities[0] == e2


# ==================== Strict Component Typing Tests (P2-006) ====================


def test_data_only_component_no_warning() -> None:
    """Data-only components should not raise warnings."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @dataclass
        class DataOnlyComponent(BaseComponent):
            value: int = 0
            name: str = ""

        # No warnings should be issued for data-only components
        component_warnings = [
            warning for warning in w if "DataOnlyComponent" in str(warning.message)
        ]
        assert len(component_warnings) == 0


def test_base_component_warns_on_logic_methods() -> None:
    """BaseComponent should warn when logic methods are detected."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        class ComponentWithLogic(BaseComponent):
            def __init__(self) -> None:
                super().__init__()
                self.value = 0

            def update(self) -> None:
                """This method contains logic - should trigger warning."""
                self.value += 1

        # Should have exactly one warning about the logic method
        component_warnings = [
            warning for warning in w if "ComponentWithLogic" in str(warning.message)
        ]
        assert len(component_warnings) == 1
        assert "update" in str(component_warnings[0].message)


def test_base_component_allows_methods_with_flag() -> None:
    """BaseComponent with _allow_methods=True should not warn."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        class LegacyComponent(BaseComponent):
            _allow_methods = True

            def __init__(self) -> None:
                super().__init__()
                self.value = 0

            def update(self) -> None:
                """This method should NOT trigger warning due to _allow_methods."""
                self.value += 1

            def process(self) -> None:
                """Another logic method."""
                pass

        # No warnings should be issued when _allow_methods is True
        component_warnings = [
            warning for warning in w if "LegacyComponent" in str(warning.message)
        ]
        assert len(component_warnings) == 0


def test_base_component_allows_properties() -> None:
    """Properties should be allowed in components without warnings."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        class ComponentWithProperty(BaseComponent):
            def __init__(self) -> None:
                super().__init__()
                self._value = 0

            @property
            def value(self) -> int:
                """Read-only property - should be allowed."""
                return self._value

            @value.setter
            def value(self, v: int) -> None:
                """Property setter - should be allowed."""
                self._value = v

        # No warnings should be issued for properties
        component_warnings = [
            warning for warning in w if "ComponentWithProperty" in str(warning.message)
        ]
        assert len(component_warnings) == 0


def test_strict_component_data_only_passes() -> None:
    """StrictComponent should allow data-only components."""

    # This should not raise any exception
    @dataclass
    class StrictDataComponent(StrictComponent):
        x: float = 0.0
        y: float = 0.0
        name: str = ""

    # Verify it can be instantiated
    component = StrictDataComponent(x=1.0, y=2.0, name="test")
    assert component.x == 1.0
    assert component.y == 2.0


def test_strict_component_raises_on_logic_methods() -> None:
    """StrictComponent should raise TypeError when logic methods are detected."""
    with pytest.raises(TypeError, match="has logic methods"):

        class StrictComponentWithLogic(StrictComponent):
            def __init__(self) -> None:
                super().__init__()
                self.value = 0

            def update(self) -> None:
                """This should cause TypeError."""
                self.value += 1


def test_strict_component_raises_with_method_names() -> None:
    """StrictComponent error should list the offending method names."""
    with pytest.raises(TypeError, match="calculate"):

        class ComponentWithCalculate(StrictComponent):
            def __init__(self) -> None:
                super().__init__()

            def calculate(self) -> int:
                return 42


def test_strict_component_allows_properties() -> None:
    """StrictComponent should allow properties."""

    # This should not raise
    class StrictWithProperty(StrictComponent):
        def __init__(self) -> None:
            super().__init__()
            self._cached = None

        @property
        def cached(self) -> object:
            """Property accessor - should be allowed."""
            return self._cached

    component = StrictWithProperty()
    assert component.cached is None
