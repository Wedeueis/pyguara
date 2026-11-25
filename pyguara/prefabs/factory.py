"""Prefab factory for entity instantiation.

Handles creating entities from prefab data, including inheritance
resolution and component hydration.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from pyguara.common.components import Transform, set_parent
from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.log import get_logger
from pyguara.prefabs.spawn_table import SpawnTable
from pyguara.prefabs.types import PrefabChild, PrefabData, PrefabInstance

if TYPE_CHECKING:
    from pyguara.ecs.entity import Entity
    from pyguara.ecs.manager import EntityManager
    from pyguara.prefabs.registry import ComponentRegistry

logger = get_logger(__name__)


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
        prefab_resolver: Callable[[str], PrefabData | None] | None = None,
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

    def set_prefab_resolver(self, resolver: Callable[[str], PrefabData | None]) -> None:
        """Set the prefab resolver callback.

        Args:
            resolver: Function that takes a prefab path and returns PrefabData.
        """
        self._prefab_resolver = resolver

    def create(
        self,
        prefab: PrefabData,
        entity_id: str | None = None,
        overrides: dict[str, dict[str, Any]] | None = None,
        source_path: str | None = None,
    ) -> Entity:
        """Create an entity from a prefab.

        Args:
            prefab: The prefab data to instantiate.
            entity_id: Optional custom entity ID.
            overrides: Optional component data overrides.
            source_path: Path the prefab was loaded from. Recorded on the
                entity's `PrefabInstance` so an instance can be traced back
                to (and reloaded from) its source. Falls back to `prefab.name`
                when the prefab was built in memory.

        Returns:
            The created entity with all components.

        Raises:
            ValueError: If the prefab's `extends` chain contains a cycle, a
                child prefab does not resolve or contains its own ancestor,
                or a component's serialized data cannot be converted to its
                type. Nothing is left behind: an entity built before the
                error is destroyed with everything it owns.
            KeyError: If a custom deserializer references an unregistered type.
        """
        self._check_tree(prefab, entity_id, source_path)
        built: list[Entity] = []
        try:
            return self._build(prefab, entity_id, overrides, source_path, built)
        except BaseException:
            # Every entity, not just the root: a child is linked to its
            # parent only once it is built, so a half-built subtree is not
            # reached by the cascade.
            for entity in reversed(built):
                self._entity_manager.remove_entity(entity.id)
            raise

    def _build(
        self,
        prefab: PrefabData,
        entity_id: str | None,
        overrides: dict[str, dict[str, Any]] | None,
        source_path: str | None,
        built: list[Entity],
    ) -> Entity:
        """Create one entity and its children, recording each in `built`."""
        # Resolve inheritance
        resolved_components = self._resolve_inheritance(prefab)

        # Apply overrides
        if overrides:
            resolved_components = self._apply_overrides(resolved_components, overrides)

        # Create entity
        entity = self._entity_manager.create_entity(entity_id)
        built.append(entity)

        # Add prefab metadata component
        entity.add_component(
            PrefabInstance(
                prefab_path=source_path or prefab.name,
                instance_overrides=overrides or {},
            )
        )

        # Create and add components. A component whose data cannot be
        # instantiated is an authoring error: let it raise rather than
        # returning a half-built entity that fails mysteriously at runtime.
        for component in self._components(
            resolved_components, source_path or prefab.name
        ):
            entity.add_component(component)

        # Create children, owned by this entity and parented to its Transform.
        self._create_children(prefab.children, entity, built)

        logger.debug(f"Created entity from prefab '{prefab.name}': {entity.id}")
        return entity

    def _components(self, data: dict[str, dict[str, Any]], prefab: str) -> list[Any]:
        """Build every registered component in `data`.

        Raises:
            ValueError: If one cannot be built, including a resource it
                names that does not load. Names the prefab and component.
        """
        components = []
        for name, fields in data.items():
            if not self._registry.has(name):
                logger.warning(f"Component '{name}' not registered, skipping")
                continue
            try:
                components.append(self._registry.create(name, fields))
            except Exception as error:
                raise ValueError(
                    f"prefab {prefab!r}, component {name}: "
                    f"{type(error).__name__}: {error}"
                ) from error
        return components

    def check(self, prefab: PrefabData, source_path: str | None = None) -> None:
        """Raise if `create` would, without creating anything.

        Builds every component of the prefab and of its children, so each
        resource they name is loaded, as `create` would. Run it as a game
        loads its prefabs, to fail on a missing texture then, not mid-level.

        Raises:
            ValueError: For anything `create` raises for, before it would
                create an entity. Names the prefab.
        """
        self._check_tree(prefab, None, source_path)
        self._check_components(prefab, source_path)

    def _check_components(self, prefab: PrefabData, source_path: str | None) -> None:
        """Build, and discard, the components of a prefab and its children."""
        self._components(self._resolve_inheritance(prefab), source_path or prefab.name)
        for child in prefab.children:
            assert self._prefab_resolver is not None  # checked above
            data = self._prefab_resolver(child.prefab)
            assert data is not None  # checked above
            components = self._resolve_inheritance(data)
            if child.overrides:
                components = self._apply_overrides(components, child.overrides)
            self.check(
                PrefabData(
                    name=data.name, components=components, children=data.children
                ),
                child.prefab,
            )

    def check_path(self, prefab_path: str) -> None:
        """Raise if `create_from_path(prefab_path)` would.

        Raises:
            ValueError: If the prefab does not load, or as `check` does.
        """
        if self._prefab_resolver is None:
            raise ValueError("checking a prefab by path needs a prefab resolver")
        prefab = self._prefab_resolver(prefab_path)
        if prefab is None:
            raise ValueError(f"prefab {prefab_path!r} did not load")
        self.check(prefab, prefab_path)

    def _check_tree(
        self, prefab: PrefabData, entity_id: str | None, source_path: str | None
    ) -> None:
        """Raise unless the prefab's children resolve and its ids are free.

        Raises:
            ValueError: As `_check_children`, or if an explicit entity id in
                the tree is already in use or appears twice.
        """
        ids = [entity_id] if entity_id else []
        self._check_children(prefab, [source_path or prefab.name], ids)
        taken = [i for i in ids if self._entity_manager.get_entity(i) is not None]
        repeated = sorted({i for i in ids if ids.count(i) > 1})
        if taken or repeated:
            raise ValueError(
                f"prefab {prefab.name!r} would create entities with ids already "
                f"in use {taken} or used twice {repeated}"
            )

    def _check_children(
        self, prefab: PrefabData, chain: list[str], ids: list[str]
    ) -> None:
        """Raise unless every child, at every depth, resolves and ends.

        Run before anything is created, so a prefab with a missing child
        fails without spawning its parent first. Appends every child's
        explicit entity id to `ids`.

        Raises:
            ValueError: If a child does not resolve, a child contains its
                own ancestor, or there are children and no resolver.
        """
        if not prefab.children:
            return
        if self._prefab_resolver is None:
            raise ValueError(
                f"prefab {prefab.name!r} has children, and the factory has no "
                f"prefab resolver to load them"
            )
        for child in prefab.children:
            if child.prefab in chain:
                cycle = " -> ".join([*chain, child.prefab])
                raise ValueError(f"prefab child cycle: {cycle}")
            data = self._prefab_resolver(child.prefab)
            if data is None:
                raise ValueError(
                    f"prefab {prefab.name!r} has child {child.prefab!r}, "
                    f"which did not load"
                )
            if child.name:
                ids.append(child.name)
            self._check_children(data, [*chain, child.prefab], ids)

    def create_from_path(
        self,
        prefab_path: str,
        entity_id: str | None = None,
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> Entity | None:
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

        return self.create(prefab, entity_id, overrides, source_path=prefab_path)

    def spawn(
        self,
        table: SpawnTable,
        rng: RandomStream,
        count: int = 1,
        positions: Sequence[Vector2] | None = None,
    ) -> list[Entity]:
        """Instantiate `count` prefabs picked from `table`.

        Each pick is independent and weighted; the same seed picks the same
        prefabs. A choice's overrides apply, and then, when `positions` is
        given, each entity's `Transform.position` is set from it in order.

        Args:
            table: What to pick from.
            rng: The seeded stream to roll on.
            count: How many to spawn.
            positions: One world position per spawn, or None to leave each
                prefab where it says.

        Returns:
            The entities, in the order they were picked.

        Raises:
            ValueError: If `positions` is not `count` long, or a picked
                prefab cannot be resolved. Nothing is spawned in either case.
        """
        if positions is not None and len(positions) != count:
            raise ValueError(f"got {len(positions)} positions for {count} spawns")
        if self._prefab_resolver is None:
            raise ValueError("spawning from a table needs a prefab resolver")
        picked = table.pick_many(rng, count)
        resolved = {}
        for choice in picked:
            if choice.prefab not in resolved:
                prefab = self._prefab_resolver(choice.prefab)
                if prefab is None:
                    raise ValueError(
                        f"spawn table names {choice.prefab!r}, which did not load"
                    )
                resolved[choice.prefab] = prefab
        entities = []
        for index, choice in enumerate(picked):
            overrides = {name: dict(data) for name, data in choice.overrides.items()}
            if positions is not None:
                point = positions[index]
                overrides.setdefault("Transform", {})["position"] = {
                    "x": point.x,
                    "y": point.y,
                }
            entities.append(
                self.create(
                    resolved[choice.prefab],
                    overrides=overrides or None,
                    source_path=choice.prefab,
                )
            )
        return entities

    def resolve_components(self, prefab: PrefabData) -> dict[str, dict[str, Any]]:
        """Return a prefab's component data with its `extends` chain applied.

        For a caller deciding what to override, which has to see what the
        prefab inherits as well as what it states.

        Args:
            prefab: The prefab to resolve.

        Returns:
            A copy of the merged component data, by component name.

        Raises:
            ValueError: If the `extends` chain contains a cycle.
        """
        return self._resolve_inheritance(prefab)

    def knows_component(self, name: str) -> bool:
        """Return whether `create` could build a component of this name.

        Args:
            name: The registered component name.

        Returns:
            True if it is registered. `create` skips one that is not.
        """
        return self._registry.has(name)

    def _resolve_inheritance(
        self,
        prefab: PrefabData,
        _chain: list[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Resolve prefab inheritance chain.

        Merges component data from parent prefabs, with child overriding parent.

        Args:
            prefab: The prefab to resolve.
            _chain: Internal. The `extends` paths already followed on this
                branch, used to detect a cycle.

        Returns:
            Merged component data dictionary.

        Raises:
            ValueError: If the `extends` chain refers back to a prefab already
                being resolved (a cycle would otherwise recurse until the
                stack ran out).
        """
        if not prefab.extends or not self._prefab_resolver:
            return copy.deepcopy(prefab.components)

        chain = _chain or []
        if prefab.extends in chain:
            cycle = " -> ".join([*chain, prefab.extends])
            raise ValueError(f"Prefab inheritance cycle detected: {cycle}")

        # Load parent prefab
        parent_prefab = self._prefab_resolver(prefab.extends)
        if not parent_prefab:
            logger.warning(f"Parent prefab not found: {prefab.extends}")
            return copy.deepcopy(prefab.components)

        # Recursively resolve parent inheritance
        parent_components = self._resolve_inheritance(
            parent_prefab, [*chain, prefab.extends]
        )

        # Deep merge: child overrides parent
        merged = self._deep_merge(parent_components, prefab.components)
        return merged

    def _apply_overrides(
        self,
        components: dict[str, dict[str, Any]],
        overrides: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
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
        base: dict[str, Any],
        override: dict[str, Any],
    ) -> dict[str, Any]:
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
        children: list[PrefabChild],
        parent_entity: Entity,
        built: list[Entity],
    ) -> list[Entity]:
        """Create child entities, owned by `parent_entity`.

        Each child is linked with `EntityManager.set_parent`, so destroying
        the parent destroys it. Its Transform, if both have one, is attached
        to the parent's with `keep_world_transform=False`: the child's
        authored position, plus `PrefabChild.offset`, is local to the parent.

        Args:
            children: List of child prefab references.
            parent_entity: The parent entity.
            built: Every entity created so far, appended to.

        Returns:
            List of created child entities.

        Raises:
            ValueError: If a child prefab does not resolve.
        """
        if not children:
            return []

        parent_transform = (
            parent_entity.get_component(Transform)
            if parent_entity.has_component(Transform)
            else None
        )

        created: list[Entity] = []

        for child in children:
            child_prefab = (
                self._prefab_resolver(child.prefab) if self._prefab_resolver else None
            )
            if child_prefab is None:
                raise ValueError(f"child prefab {child.prefab!r} did not load")

            child_entity = self._build(
                child_prefab, child.name, child.overrides, child.prefab, built
            )
            self._entity_manager.set_parent(child_entity.id, parent_entity.id)

            child_transform = (
                child_entity.get_component(Transform)
                if child_entity.has_component(Transform)
                else None
            )

            if child.offset:
                if child_transform is not None:
                    child_transform.position = Vector2(
                        child_transform.position.x + child.offset.get("x", 0.0),
                        child_transform.position.y + child.offset.get("y", 0.0),
                    )
                else:
                    logger.warning(
                        f"Child prefab '{child.prefab}' has an offset but no "
                        f"Transform component; offset ignored"
                    )

            if parent_transform is not None and child_transform is not None:
                set_parent(
                    child_transform, parent_transform, keep_world_transform=False
                )

            created.append(child_entity)

        return created
