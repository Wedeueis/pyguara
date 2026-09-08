"""Entity: the component container at the centre of the ECS."""

from __future__ import annotations

import copy
import dataclasses
import re
import uuid
from collections.abc import Callable
from typing import Any, TypeVar, cast

from pyguara.ecs.component import Component

C = TypeVar("C", bound=Component)


class Entity:
    """A uniquely identified container for components.

    An entity holds no logic of its own. Systems query the `EntityManager` for
    entities carrying a given set of components and operate on that data.

    Attributes:
        id: Unique identifier for the entity.
        tags: String tags for categorisation outside the component index.
    """

    # ClassName -> snake_case, computed once per component type so the regex
    # below never runs inside an update loop.
    _NAME_CACHE: dict[type[Component], str] = {}

    def __init__(self, entity_id: str | None = None) -> None:
        """Initialise an entity that is not yet registered with any manager.

        Args:
            entity_id: Explicit id. Defaults to a fresh UUID4 string.
        """
        self.id = entity_id or str(uuid.uuid4())
        self.tags: set[str] = set()

        self._components: dict[type[Component], Component] = {}
        # snake_case name -> component, backing attribute access (entity.transform).
        self._property_cache: dict[str, Component] = {}

        # Set by EntityManager.add_entity() so component changes can keep the
        # manager's inverted index in sync without the entity knowing the manager.
        self._on_component_added: Callable[[str, type[Component]], None] | None = None
        self._on_component_removed: Callable[[str, type[Component]], None] | None = None

        # Set by EntityManager.remove_entity() at the moment of soft-death.
        # Removal is terminal, not reusable: further mutation raises rather
        # than silently no-opping or resurrecting the entity.
        self._is_removed: bool = False

    def add_component(self, component: C) -> C:
        """Attach a component instance to this entity.

        Updates the attribute cache (enabling `entity.rigid_body`) and notifies
        the owning manager, if any, so its indexes stay consistent.

        Args:
            component: An initialised component instance.

        Returns:
            The component that was added.

        Raises:
            RuntimeError: If this entity has been removed (soft-dead).
            ValueError: If a component of the same type is already attached.
        """
        if self._is_removed:
            raise RuntimeError(
                f"Entity {self.id} has been removed; cannot add_component() to a "
                f"dead entity. Removal is terminal -- use Entity.clone() to make a "
                f"fresh, re-addable entity instead."
            )

        component_type = type(component)
        if component_type in self._components:
            raise ValueError(
                f"Entity {self.id} already has component {component_type.__name__}"
            )

        self._components[component_type] = component
        component.on_attach(self)
        self._property_cache[self._get_snake_name(component_type)] = component

        if self._on_component_added:
            self._on_component_added(self.id, component_type)

        return component

    def get_component(self, component_type: type[C]) -> C:
        """Retrieve an attached component by its exact type.

        This is the fastest and most type-safe access path; prefer it over
        attribute access in hot loops.

        Args:
            component_type: The component class to look up.

        Returns:
            The attached component instance.

        Raises:
            KeyError: If no component of that type is attached.
        """
        try:
            return cast(C, self._components[component_type])
        except KeyError:
            raise KeyError(
                f"Entity {self.id} has no component {component_type.__name__}"
            ) from None

    def has_component(self, component_type: type[Component]) -> bool:
        """Report whether a component of the given type is attached.

        Args:
            component_type: The component class to test for.

        Returns:
            True if the component is attached.
        """
        return component_type in self._components

    def get_all_components(self) -> tuple[Component, ...]:
        """Return every component attached to this entity, in insertion order.

        The supported way to enumerate an entity's components from outside --
        inspectors, serialisers and editor tools should iterate this rather
        than reaching into `_components`. The result is a snapshot tuple, so
        the caller may add or remove components while iterating it.

        Returns:
            All attached components. Get each one's registered name with
            `type(component).__name__`.
        """
        return tuple(self._components.values())

    def remove_component(self, component_type: type[Component]) -> None:
        """Detach a component by type, keeping manager indexes consistent.

        Detaching a type that is not attached is a no-op.

        Args:
            component_type: The component class to detach.

        Raises:
            RuntimeError: If this entity has been removed (soft-dead).
        """
        if self._is_removed:
            raise RuntimeError(
                f"Entity {self.id} has been removed; cannot remove_component() "
                f"from a dead entity."
            )

        component = self._components.pop(component_type, None)
        if component is None:
            return

        component.on_detach()
        self._property_cache.pop(self._get_snake_name(component_type), None)

        if self._on_component_removed:
            self._on_component_removed(self.id, component_type)

    def clone(self, new_id: str | None = None) -> Entity:
        """Create a detached, unregistered copy of this entity's data.

        Each component is deep-copied, except fields whose name starts with `_`
        (system-injected handles such as `RigidBody._body_handle`), which are
        reset to their dataclass default: a clone has not been registered with
        any manager or physics/audio backend, so it cannot inherit a live handle.

        The clone starts with its component-change hooks unset. Call
        `EntityManager.add_entity(clone)` to bring it into a world.

        Args:
            new_id: Explicit id for the clone. Defaults to a fresh UUID4 string.

        Returns:
            The new, unregistered entity.
        """
        clone = Entity(new_id)
        clone.tags = set(self.tags)

        # on_attach() gives each component a live `.entity` back-reference to
        # self. Seeding the memo maps that reference to a placeholder instead of
        # letting deepcopy walk into it (which would hit __deepcopy__ and raise);
        # add_component() below overwrites it with `clone` anyway.
        memo: dict[int, Any] = {id(self): None}

        for component in self._components.values():
            cloned_component = copy.deepcopy(component, memo)
            try:
                component_fields = dataclasses.fields(cast(Any, cloned_component))
            except TypeError:
                component_fields = ()  # Not a dataclass; nothing to reset.

            for field in component_fields:
                if not field.name.startswith("_"):
                    continue
                if field.default is not dataclasses.MISSING:
                    default = field.default
                elif field.default_factory is not dataclasses.MISSING:
                    default = field.default_factory()
                else:
                    default = None
                setattr(cloned_component, field.name, default)

            clone.add_component(cloned_component)

        return clone

    def __getattr__(self, name: str) -> Any:
        """Resolve `entity.some_component` against the attribute cache.

        Only reached when normal attribute lookup fails, so components attached
        via `add_component()` resolve without entering this method.

        Reads `_property_cache` via `__dict__` rather than
        `self._property_cache`: on a blank instance built by `cls.__new__(cls)`
        (e.g. during copy/pickle reconstruction, before `__init__` has run)
        `_property_cache` does not exist yet, and attribute access would
        re-enter `__getattr__` for that name too, recursing infinitely. A
        `__dict__` lookup never triggers `__getattr__`, so this is safe either
        way.

        Args:
            name: The snake_case name of a component type.

        Returns:
            The matching component instance.

        Raises:
            AttributeError: If no attribute or component matches `name`.
        """
        cache = self.__dict__.get("_property_cache")
        if cache is not None and name in cache:
            return cache[name]

        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute or component '{name}'"
        )

    def __deepcopy__(self, memo: dict[int, Any]) -> Entity:
        """Reject `copy.deepcopy()`; use `clone()` instead.

        Args:
            memo: Deepcopy memo dictionary (unused).

        Raises:
            TypeError: Always.
        """
        raise TypeError(
            "Entity does not support copy.deepcopy() — it would alias the live "
            "EntityManager callbacks and physics/audio handles of the original. "
            "Use Entity.clone() instead."
        )

    def __copy__(self) -> Entity:
        """Reject `copy.copy()`; use `clone()` instead.

        Raises:
            TypeError: Always.
        """
        raise TypeError(
            "Entity does not support copy.copy() — use Entity.clone() instead."
        )

    def __reduce__(self) -> Any:
        """Reject pickling; use `SceneSerializer` for save/load.

        Raises:
            TypeError: Always.
        """
        raise TypeError(
            "Entity does not support pickling — use SceneSerializer for save/load."
        )

    @classmethod
    def _get_snake_name(cls, component_type: type[Component]) -> str:
        """Convert a component class name to snake_case, memoised per type.

        Args:
            component_type: The component class to name.

        Returns:
            The snake_case attribute name, e.g. `RigidBody` -> `rigid_body`.
        """
        cached = cls._NAME_CACHE.get(component_type)
        if cached is not None:
            return cached

        type_name = component_type.__name__

        # Single-word names ("Transform") are the overwhelming majority; skip
        # the regex for them.
        if type_name.isalpha() and type_name[0].isupper() and type_name[1:].islower():
            snake_name = type_name.lower()
        else:
            boundaries = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", type_name)
            snake_name = re.sub("([a-z0-9])([A-Z])", r"\1_\2", boundaries).lower()

        cls._NAME_CACHE[component_type] = snake_name
        return snake_name

    def __repr__(self) -> str:
        """Return a debug representation listing attached component types."""
        components = ", ".join(c.__name__ for c in self._components)
        return f"Entity(id={self.id}, components=[{components}])"
