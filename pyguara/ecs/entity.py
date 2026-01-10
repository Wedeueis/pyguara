"""Entity class implementation with performance optimizations."""

import re
import uuid
from typing import Dict, Optional, Type, TypeVar, Any, Callable, Set

from pyguara.ecs.component import Component

C = TypeVar("C", bound=Component)


class Entity:
    """A generic container for components.

    Represents a game object in the world. It has a unique ID and a collection
    of components.

    Attributes:
        id (str): Unique identifier for the entity.
        tags (set[str]): Set of string tags for quick categorization.
    """

    # Static cache to store "RigidBody" -> "rigid_body" conversions globally.
    # This ensures we never run regex more than once per Component Type.
    _NAME_CACHE: Dict[Type[Component], str] = {}

    def __init__(self, entity_id: Optional[str] = None) -> None:
        """Initialize a new entity."""
        self.id = entity_id or str(uuid.uuid4())
        self.tags: Set[str] = set()

        self._components: Dict[
            Type[Component], Component
        ] = {}  # Direct attribute cache (e.g., self.transform)
        self._property_cache: Dict[str, Component] = {}

        # Callback hook for the EntityManager to keep indexes in sync
        # Signature: (entity_id: str, component_type: Type[Component]) -> None
        self._on_component_added: Optional[Callable[[str, Type[Component]], None]] = (
            None
        )
        self._on_component_removed: Optional[Callable[[str, Type[Component]], None]] = (
            None
        )

    def add_component(self, component: C) -> C:
        """Add a component instance to the entity.

        This method immediately updates the property cache (allowing entity.rigid_body)
        and notifies any listeners (like the EntityManager) to update their indexes.

        Args:
            component: The initialized component instance.

        Returns:
            The added component.
        """
        component_type = type(component)
        if component_type in self._components:
            raise ValueError(
                f"Entity {self.id} already has component {component_type.__name__}"
            )

        # 1. Store Component
        self._components[component_type] = component
        component.on_attach(self)

        # 2. Update Attribute Cache (Optimization B)
        # We calculate the snake_case name once and store it.
        snake_name = self._get_snake_name(component_type)
        self._property_cache[snake_name] = component

        # 3. Notify Listener (Optimization A)
        if self._on_component_added:
            self._on_component_added(self.id, component_type)

        return component

    def get_component(self, component_type: Type[C]) -> C:
        """
        Retrieve a component by its type.

        This is the preferred, fastest, and most type-safe method of access.
        """
        try:
            return self._components[component_type]  # type: ignore
        except KeyError:
            raise KeyError(
                f"Entity {self.id} has no component {component_type.__name__}"
            )

    def has_component(self, component_type: Type[Component]) -> bool:
        """Check if the entity possesses a specific component type."""
        return component_type in self._components

    def remove_component(self, component_type: Type[Component]) -> None:
        """Remove a component by type.

        This method removes the component from the entity and updates the
        EntityManager's inverted indexes to ensure queries remain consistent.

        Args:
            component_type: The type of component to remove.
        """
        if component_type in self._components:
            comp = self._components.pop(component_type)
            comp.on_detach()

            # Remove from property cache
            snake_name = self._get_snake_name(component_type)
            if snake_name in self._property_cache:
                del self._property_cache[snake_name]

            # Notify the manager to update indexes
            if self._on_component_removed:
                self._on_component_removed(self.id, component_type)

    def __getattr__(self, name: str) -> Any:
        """
        Fallback attribute access.

        Performance Note: This is only hit if the attribute is NOT in _property_cache.
        Since add_component populates the cache, this is rarely called for valid components.
        """
        if name in self._property_cache:
            return self._property_cache[name]

        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute or component '{name}'"
        )

    @classmethod
    def _get_snake_name(cls, component_type: Type[Component]) -> str:
        """
        Convert ClassName to snake_case using a static cache.

        This solves the "Regex-in-Update-Loop" problem.
        """
        if component_type in cls._NAME_CACHE:
            return cls._NAME_CACHE[component_type]

        type_name = component_type.__name__

        # Fast common case: "Transform" -> "transform"
        if type_name.isalpha() and type_name[0].isupper() and type_name[1:].islower():
            snake_name = type_name.lower()
        else:
            # Regex fallback for complex names like "RigidBody" -> "rigid_body"
            s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", type_name)
            snake_name = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

        cls._NAME_CACHE[component_type] = snake_name
        return snake_name

    def __repr__(self) -> str:
        """Return entity string representation."""
        comps = ", ".join(c.__name__ for c in self._components)
        return f"Entity(id={self.id}, components=[{comps}])"
