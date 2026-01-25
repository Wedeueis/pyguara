"""Prefab factory for entity instantiation.

Handles creating entities from prefab data, including inheritance
resolution and component hydration.
"""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from pyguara.common.types import Vector2
from pyguara.prefabs.types import PrefabChild, PrefabData, PrefabInstance

if TYPE_CHECKING:
    from pyguara.ecs.entity import Entity
    from pyguara.ecs.manager import EntityManager
    from pyguara.prefabs.registry import ComponentRegistry

logger = logging.getLogger(__name__)


class PrefabFactory:
    """Factory for instantiating entities from prefab data.

    The factory handles:
    - Prefab inheritance resolution
    - Component creation via ComponentRegistry
    - Child entity instantiation
    - Position offset application

    Example:
        factory = PrefabFactory(entity_manager, component_registry)

        # Load prefab data (from PrefabLoader or manually)
        prefab = PrefabData(
            name="Player",
            components={"Transform": {"position": {"x": 100, "y": 100}}}
        )

        # Instantiate
        entity = factory.create(prefab)
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        component_registry: ComponentRegistry,
        prefab_resolver: Optional[Callable[[str], Optional[PrefabData]]] = None,
    ) -> None:
        """Initialize the factory.

        Args:
            entity_manager: The entity manager to create entities in.
            component_registry: Registry for component instantiation.
            prefab_resolver: Optional callback to resolve prefab paths to data.
                Used for inheritance and child prefab loading.
        """
        self._entity_manager = entity_manager
        self._registry = component_registry
        self._prefab_resolver = prefab_resolver

    def set_prefab_resolver(
        self, resolver: Callable[[str], Optional[PrefabData]]
    ) -> None:
        """Set the prefab resolver callback.

        Args:
            resolver: Function that takes a prefab path and returns PrefabData.
        """
        self._prefab_resolver = resolver

    def create(
        self,
        prefab: PrefabData,
        entity_id: Optional[str] = None,
        overrides: Optional[Dict[str, Dict[str, Any]]] = None,
        parent_position: Optional[Vector2] = None,
    ) -> Entity:
        """Create an entity from a prefab.

        Args:
            prefab: The prefab data to instantiate.
            entity_id: Optional custom entity ID.
            overrides: Optional component data overrides.
            parent_position: Optional parent position for offset calculation.

        Returns:
            The created entity with all components.
        """
        # Resolve inheritance
        resolved_components = self._resolve_inheritance(prefab)

        # Apply overrides
        if overrides:
            resolved_components = self._apply_overrides(resolved_components, overrides)

        # Create entity
        entity = self._entity_manager.create_entity(entity_id)

        # Add prefab metadata component
        entity.add_component(
            PrefabInstance(
                prefab_path=prefab.name,
                instance_overrides=overrides or {},
            )
        )

        # Create and add components
        for comp_name, comp_data in resolved_components.items():
            if not self._registry.has(comp_name):
                logger.warning(f"Component '{comp_name}' not registered, skipping")
                continue

            try:
                component = self._registry.create(comp_name, comp_data)

                # Apply parent position offset for Transform
                if comp_name == "Transform" and parent_position is not None:
                    if hasattr(component, "position"):
                        component.position = Vector2(
                            component.position.x + parent_position.x,
                            component.position.y + parent_position.y,
                        )

                entity.add_component(component)
            except Exception as e:
                logger.error(f"Failed to create component '{comp_name}': {e}")

        # Create children
        children = self._create_children(prefab.children, entity)
        for child in children:
            # Optionally link children to parent here
            pass

        logger.debug(f"Created entity from prefab '{prefab.name}': {entity.id}")
        return entity

    def create_from_path(
        self,
        prefab_path: str,
        entity_id: Optional[str] = None,
        overrides: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Optional[Entity]:
        """Create an entity from a prefab path.

        Args:
            prefab_path: Path to the prefab file.
            entity_id: Optional custom entity ID.
            overrides: Optional component data overrides.

        Returns:
            The created entity, or None if prefab couldn't be resolved.
        """
        if not self._prefab_resolver:
            logger.error("No prefab resolver set, cannot load from path")
            return None

        prefab = self._prefab_resolver(prefab_path)
        if not prefab:
            logger.error(f"Failed to resolve prefab: {prefab_path}")
            return None

        return self.create(prefab, entity_id, overrides)

    def _resolve_inheritance(self, prefab: PrefabData) -> Dict[str, Dict[str, Any]]:
        """Resolve prefab inheritance chain.

        Merges component data from parent prefabs, with child overriding parent.

        Args:
            prefab: The prefab to resolve.

        Returns:
            Merged component data dictionary.
        """
        if not prefab.extends or not self._prefab_resolver:
            return copy.deepcopy(prefab.components)

        # Load parent prefab
        parent_prefab = self._prefab_resolver(prefab.extends)
        if not parent_prefab:
            logger.warning(f"Parent prefab not found: {prefab.extends}")
            return copy.deepcopy(prefab.components)

        # Recursively resolve parent inheritance
        parent_components = self._resolve_inheritance(parent_prefab)

        # Deep merge: child overrides parent
        merged = self._deep_merge(parent_components, prefab.components)
        return merged

    def _apply_overrides(
        self,
        components: Dict[str, Dict[str, Any]],
        overrides: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """Apply runtime overrides to component data.

        Args:
            components: Base component data.
            overrides: Override data to apply.

        Returns:
            Merged component data.
        """
        return self._deep_merge(components, overrides)

    def _deep_merge(
        self,
        base: Dict[str, Any],
        override: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Deep merge two dictionaries.

        Override values replace base values. Nested dicts are merged recursively.

        Args:
            base: Base dictionary.
            override: Override dictionary.

        Returns:
            Merged dictionary.
        """
        result = copy.deepcopy(base)

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = copy.deepcopy(value)

        return result

    def _create_children(
        self,
        children: List[PrefabChild],
        parent_entity: Entity,
    ) -> List[Entity]:
        """Create child entities from prefab children.

        Args:
            children: List of child prefab references.
            parent_entity: The parent entity.

        Returns:
            List of created child entities.
        """
        if not self._prefab_resolver:
            return []

        created: List[Entity] = []

        for child in children:
            child_prefab = self._prefab_resolver(child.prefab)
            if not child_prefab:
                logger.warning(f"Child prefab not found: {child.prefab}")
                continue

            # Calculate parent position for offset
            parent_pos = None
            transform = parent_entity.get_component_by_name("Transform")
            if transform and hasattr(transform, "position"):
                parent_pos = transform.position
                if child.offset:
                    parent_pos = Vector2(
                        parent_pos.x + child.offset.get("x", 0),
                        parent_pos.y + child.offset.get("y", 0),
                    )

            # Create child entity
            child_entity = self.create(
                child_prefab,
                entity_id=child.name,
                overrides=child.overrides,
                parent_position=parent_pos,
            )
            created.append(child_entity)

        return created
