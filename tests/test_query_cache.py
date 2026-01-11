"""Tests for P1-008: ECS Query Cache optimization."""

from pyguara.ecs.manager import EntityManager
from pyguara.common.components import Transform
from pyguara.physics.components import RigidBody
from pyguara.ecs.component import BaseComponent
from dataclasses import dataclass


@dataclass
class MockComponent(BaseComponent):
    """Mock component for testing."""

    value: int = 0


class TestQueryCacheRegistration:
    """Test query cache registration and basic functionality."""

    def test_register_cached_query(self):
        """Query can be registered for caching."""
        manager = EntityManager()

        # Should not raise
        manager.register_cached_query(Transform, RigidBody)

    def test_multiple_query_registration(self):
        """Multiple different queries can be registered."""
        manager = EntityManager()

        manager.register_cached_query(Transform, RigidBody)
        manager.register_cached_query(Transform, MockComponent)
        manager.register_cached_query(RigidBody, MockComponent)

        # Should not raise

    def test_duplicate_registration_is_safe(self):
        """Registering same query twice doesn't cause issues."""
        manager = EntityManager()

        manager.register_cached_query(Transform, RigidBody)
        manager.register_cached_query(Transform, RigidBody)  # Duplicate

        # Should not raise


class TestQueryCacheBasicFunctionality:
    """Test basic cached query functionality."""

    def test_cached_query_returns_matching_entities(self):
        """Cached query returns entities with all required components."""
        manager = EntityManager()
        manager.register_cached_query(Transform, RigidBody)

        # Create entity with both components
        e1 = manager.create_entity()
        e1.add_component(Transform())
        e1.add_component(RigidBody())

        # Create entity with only one component
        e2 = manager.create_entity()
        e2.add_component(Transform())

        # Query should return only e1
        results = list(manager.get_entities_with_cached(Transform, RigidBody))
        assert len(results) == 1
        assert results[0].id == e1.id

    def test_cached_query_empty_when_no_matches(self):
        """Cached query returns empty when no entities match."""
        manager = EntityManager()
        manager.register_cached_query(Transform, RigidBody)

        # Create entity with only one component
        e1 = manager.create_entity()
        e1.add_component(Transform())

        # Query should return empty
        results = list(manager.get_entities_with_cached(Transform, RigidBody))
        assert len(results) == 0

    def test_cached_query_multiple_matches(self):
        """Cached query returns all matching entities."""
        manager = EntityManager()
        manager.register_cached_query(Transform, RigidBody)

        # Create 5 entities with both components
        entities = []
        for _ in range(5):
            e = manager.create_entity()
            e.add_component(Transform())
            e.add_component(RigidBody())
            entities.append(e)

        # Query should return all 5
        results = list(manager.get_entities_with_cached(Transform, RigidBody))
        assert len(results) == 5
        result_ids = {e.id for e in results}
        expected_ids = {e.id for e in entities}
        assert result_ids == expected_ids


class TestQueryCacheDynamicUpdates:
    """Test cache invalidation when components change."""

    def test_cache_updates_when_component_added(self):
        """Cache automatically updates when component is added."""
        manager = EntityManager()
        manager.register_cached_query(Transform, RigidBody)

        e1 = manager.create_entity()
        e1.add_component(Transform())

        # Initially not in cache (missing RigidBody)
        results = list(manager.get_entities_with_cached(Transform, RigidBody))
        assert len(results) == 0

        # Add missing component
        e1.add_component(RigidBody())

        # Should now appear in cache
        results = list(manager.get_entities_with_cached(Transform, RigidBody))
        assert len(results) == 1
        assert results[0].id == e1.id

    def test_cache_updates_when_component_removed(self):
        """Cache automatically updates when component is removed."""
        manager = EntityManager()
        manager.register_cached_query(Transform, RigidBody)

        e1 = manager.create_entity()
        e1.add_component(Transform())
        e1.add_component(RigidBody())

        # Initially in cache
        results = list(manager.get_entities_with_cached(Transform, RigidBody))
        assert len(results) == 1

        # Remove component
        e1.remove_component(RigidBody)

        # Should no longer appear in cache
        results = list(manager.get_entities_with_cached(Transform, RigidBody))
        assert len(results) == 0

    def test_cache_updates_multiple_component_changes(self):
        """Cache handles multiple component add/remove operations."""
        manager = EntityManager()
        manager.register_cached_query(Transform, RigidBody, MockComponent)

        e1 = manager.create_entity()
        e1.add_component(Transform())

        # Add RigidBody (still missing MockComponent)
        e1.add_component(RigidBody())
        results = list(
            manager.get_entities_with_cached(Transform, RigidBody, MockComponent)
        )
        assert len(results) == 0

        # Add MockComponent (now complete)
        e1.add_component(MockComponent())
        results = list(
            manager.get_entities_with_cached(Transform, RigidBody, MockComponent)
        )
        assert len(results) == 1

        # Remove Transform (incomplete again)
        e1.remove_component(Transform)
        results = list(
            manager.get_entities_with_cached(Transform, RigidBody, MockComponent)
        )
        assert len(results) == 0


class TestQueryCacheMultipleQueries:
    """Test behavior with multiple registered queries."""

    def test_independent_cache_invalidation(self):
        """Different cached queries update independently."""
        manager = EntityManager()
        manager.register_cached_query(Transform, RigidBody)
        manager.register_cached_query(Transform, MockComponent)

        e1 = manager.create_entity()
        e1.add_component(Transform())
        e1.add_component(RigidBody())

        # First query should have 1 result
        results1 = list(manager.get_entities_with_cached(Transform, RigidBody))
        assert len(results1) == 1

        # Second query should have 0 results
        results2 = list(manager.get_entities_with_cached(Transform, MockComponent))
        assert len(results2) == 0

        # Add MockComponent
        e1.add_component(MockComponent())

        # First query still has 1 result
        results1 = list(manager.get_entities_with_cached(Transform, RigidBody))
        assert len(results1) == 1

        # Second query now has 1 result
        results2 = list(manager.get_entities_with_cached(Transform, MockComponent))
        assert len(results2) == 1


class TestQueryCacheFallback:
    """Test fallback behavior when query is not registered."""

    def test_uncached_query_fallback(self):
        """Uncached query falls back to standard get_entities_with."""
        manager = EntityManager()

        # Don't register the query
        # manager.register_cached_query(Transform, RigidBody)

        e1 = manager.create_entity()
        e1.add_component(Transform())
        e1.add_component(RigidBody())

        # Should still work via fallback
        results = list(manager.get_entities_with_cached(Transform, RigidBody))
        assert len(results) == 1
        assert results[0].id == e1.id


class TestQueryCacheEdgeCases:
    """Test edge cases and error conditions."""

    def test_cache_with_no_entities(self):
        """Cache works correctly with no entities."""
        manager = EntityManager()
        manager.register_cached_query(Transform, RigidBody)

        results = list(manager.get_entities_with_cached(Transform, RigidBody))
        assert len(results) == 0

    def test_cache_after_entity_removal(self):
        """Cache updates correctly when entities are removed."""
        manager = EntityManager()
        manager.register_cached_query(Transform, RigidBody)

        e1 = manager.create_entity()
        e1.add_component(Transform())
        e1.add_component(RigidBody())

        # Verify in cache
        results = list(manager.get_entities_with_cached(Transform, RigidBody))
        assert len(results) == 1

        # Remove entity entirely
        manager.remove_entity(e1.id)

        # Should no longer appear
        results = list(manager.get_entities_with_cached(Transform, RigidBody))
        assert len(results) == 0

    def test_cache_with_single_component_query(self):
        """Cache works with single-component queries."""
        manager = EntityManager()
        manager.register_cached_query(Transform)

        e1 = manager.create_entity()
        e1.add_component(Transform())

        e2 = manager.create_entity()
        e2.add_component(RigidBody())

        results = list(manager.get_entities_with_cached(Transform))
        assert len(results) == 1
        assert results[0].id == e1.id


class TestQueryCacheConsistency:
    """Test that cached queries always match standard queries."""

    def test_cached_matches_standard_query(self):
        """Cached query returns same results as standard query."""
        manager = EntityManager()
        manager.register_cached_query(Transform, RigidBody)

        # Create mixed entities
        for i in range(10):
            e = manager.create_entity()
            e.add_component(Transform())
            if i % 2 == 0:
                e.add_component(RigidBody())

        # Both queries should return same entities
        cached_results = set(
            e.id for e in manager.get_entities_with_cached(Transform, RigidBody)
        )
        standard_results = set(
            e.id for e in manager.get_entities_with(Transform, RigidBody)
        )

        assert cached_results == standard_results
        assert len(cached_results) == 5  # Half of 10

    def test_consistency_after_modifications(self):
        """Cached and standard queries remain consistent after modifications."""
        manager = EntityManager()
        manager.register_cached_query(Transform, RigidBody)

        entities = []
        for _ in range(5):
            e = manager.create_entity()
            e.add_component(Transform())
            e.add_component(RigidBody())
            entities.append(e)

        # Modify some entities
        entities[0].remove_component(RigidBody)
        entities[2].add_component(MockComponent())
        entities[4].remove_component(Transform)

        # Check consistency
        cached_results = set(
            e.id for e in manager.get_entities_with_cached(Transform, RigidBody)
        )
        standard_results = set(
            e.id for e in manager.get_entities_with(Transform, RigidBody)
        )

        assert cached_results == standard_results
