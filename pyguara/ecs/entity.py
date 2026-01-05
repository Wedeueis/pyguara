"""Entity class implementation."""

import uuid
from typing import Dict, Optional, Type, TypeVar, Any

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

    def __init__(self, entity_id: Optional[str] = None) -> None:
        """Initialize a new entity.

        Args:
            entity_id: Optional unique ID. Generates UUID if None.
        """
        self.id = entity_id or str(uuid.uuid4())
        self.tags: set[str] = set()
        self._components: Dict[Type[Component], Component] = {}
        # Cache for property access optimization
        self._property_cache: Dict[str, Component] = {}

    def add_component(self, component: C) -> C:
        """Add a component instance to the entity.

        Args:
            component: The initialized component instance.

        Returns:
            The added component.

        Raises:
            ValueError: If a component of the same type already exists.
        """
        component_type = type(component)
        if component_type in self._components:
            raise ValueError(
                f"Entity {self.id} already has component {component_type.__name__}"
            )

        self._components[component_type] = component
        component.entity = self

        # Trigger lifecycle hook
        if hasattr(component, "on_attach"):
            component.on_attach(self)

        # Clear cache to ensure name conflicts don't persist
        self._property_cache.clear()

        return component

    def get_component(self, component_type: Type[C]) -> Optional[C]:
        """Retrieve a component by its type.

        Args:
            component_type: The class of the component to retrieve.

        Returns:
            The component instance or None if not found.
        """
        return self._components.get(component_type)  # type: ignore

    def require_component(self, component_type: Type[C]) -> C:
        """Retrieve a component or raise an error if missing.

        Args:
            component_type: The class of the component to retrieve.

        Returns:
            The component instance.

        Raises:
            KeyError: If the component is missing.
        """
        if component_type not in self._components:
            raise KeyError(
                f"Entity {self.id} missing required component {component_type.__name__}"
            )
        return self._components[component_type]  # type: ignore

    def remove_component(self, component_type: Type[Component]) -> None:
        """Remove a component by type.

        Args:
            component_type: The class of the component to remove.
        """
        if component_type in self._components:
            component = self._components.pop(component_type)
            if hasattr(component, "on_detach"):
                component.on_detach()

            # Clear cache
            self._property_cache.clear()

    def has_component(self, component_type: Type[Component]) -> bool:
        """Check if the entity has a specific component.

        Args:
            component_type: The class to check for.

        Returns:
            True if present.
        """
        return component_type in self._components

    def __getattr__(self, name: str) -> Any:
        """Allow accessing components via snake_case properties.

        Example:
            entity.rigid_body  -> returns RigidBody component
            entity.transform   -> returns Transform component

        Args:
            name: The attribute name being accessed.

        Returns:
            The component if found.

        Raises:
            AttributeError: If no matching component is found.
        """
        # 1. Check cache first
        if name in self._property_cache:
            return self._property_cache[name]

        # 2. Search components
        for comp_type, comp_instance in self._components.items():
            # Convert ClassName to snake_case simple heuristic
            # (e.g. RigidBody -> rigid_body, Transform -> transform)
            type_name = comp_type.__name__

            # Simple conversion: "Transform" -> "transform"
            if type_name.lower() == name:
                self._property_cache[name] = comp_instance
                return comp_instance

            # Handle CamelCase to snake_case (e.g. RigidBody -> rigid_body)
            # This is a basic implementation; robust regex could be used if strictness needed
            import re

            s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", type_name)
            snake_name = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

            if snake_name == name:
                self._property_cache[name] = comp_instance
                return comp_instance

        # 3. Not found
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute or component '{name}'"
        )

    def __repr__(self) -> str:
        """Get the entity description as a string."""
        comps = ", ".join(c.__name__ for c in self._components)
        return f"Entity(id={self.id}, components=[{comps}])"
