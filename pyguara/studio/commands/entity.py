"""The concrete edits: entities, components, fields, hierarchy, tags.

Each command here knows two things the engine does not expose: how to make
its change *through* the `EntityManager`'s own API, and what to put back.
The first matters because mutating a component behind the manager's back
leaves everything mirroring it -- physics bodies, render batches, the
spatial index -- holding stale data; every field write ends with
`notify_component_changed()`.

The awkward one is `DestroyEntity`. `EntityManager.remove_entity` cascades
depth-first through `ChildOf`, and removal is terminal -- a removed entity
raises on further mutation and cannot be re-added. So destroying one
entity can delete a whole subtree, and undoing it means rebuilding that
subtree: every entity, its components, its tags, its enabled state and its
parent link. The command snapshots all of it before it removes anything.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from pyguara.ecs.component import Component
from pyguara.ecs.manager import EntityManager
from pyguara.ecs.relations import ChildOf
from pyguara.studio.commands.base import EditCommand, EditError


def _require_entity(world: EntityManager, entity_id: str) -> Any:
    """Return the entity, or raise `EditError` naming what was missing.

    Args:
        world: The world to look in.
        entity_id: The entity to find.

    Returns:
        The entity.

    Raises:
        EditError: If no such entity exists.
    """
    entity = world.get_entity(entity_id)
    if entity is None:
        raise EditError(f"No entity '{entity_id}' in this scene.")
    return entity


def _get_component(entity: Any, component_type: type[Component]) -> Component | None:
    """Return the attached component of that type, or None.

    `Entity.get_component` raises `KeyError` for a missing type, and these
    commands want to turn "not attached" into an `EditError` with a message
    rather than let a `KeyError` escape.

    Args:
        entity: The entity to read.
        component_type: The component class to look up.

    Returns:
        The component, or None when it is not attached.
    """
    if not entity.has_component(component_type):
        return None
    component: Component = entity.get_component(component_type)
    return component


def _capture(value: Any) -> Any:
    """Return a value safe to hold as an undo target.

    `Color` is a mutable dataclass and a list field is a mutable list, so
    holding the live object would let a later edit change what the undo
    restores. A shallow copy is enough: the editable field types are flat.
    `Vector2` is immutable and copies to itself.

    Args:
        value: The value being replaced.

    Returns:
        A copy, or the original when it cannot be copied.
    """
    try:
        return copy.copy(value)
    except Exception:  # pragma: no cover - exotic field types
        return value


@dataclass
class EntitySnapshot:
    """Everything needed to rebuild one entity exactly as it was.

    Attributes:
        entity_id: Its id, which is its identity -- restored, not minted.
        components: The component instances, reattached as-is. Reused
            rather than copied: the entity they came from is unreachable
            once removed, and `add_component` resets each one's `entity`
            back-reference on the way in.
        tags: Its tag set.
        enabled: Whether it was enabled.
        parent_id: Its `ChildOf` parent, or None.
    """

    entity_id: str
    components: list[Component] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)
    enabled: bool = True
    parent_id: str | None = None


def snapshot_subtree(world: EntityManager, entity_id: str) -> list[EntitySnapshot]:
    """Capture `entity_id` and everything that would cascade with it.

    Ordered parents-first, so restoring in order never names a parent that
    does not exist yet.

    Args:
        world: The world to read.
        entity_id: The root of the subtree.

    Returns:
        One snapshot per entity, the root first.

    Raises:
        EditError: If no such entity exists.
    """
    root = _require_entity(world, entity_id)
    snapshots: list[EntitySnapshot] = []
    # Breadth-first, which is parents-before-children for a tree. Depth
    # would do as well; what matters is that no child precedes its parent.
    frontier = [root]
    seen = {entity_id}
    while frontier:
        entity = frontier.pop(0)
        snapshots.append(
            EntitySnapshot(
                entity_id=entity.id,
                # `ChildOf` is excluded: the parent link is restored through
                # `set_parent`, which is what maintains the manager's
                # parent -> children index. Re-attaching the component by
                # hand would set the field and leave the index empty.
                components=[
                    component
                    for component in entity.get_all_components()
                    if not isinstance(component, ChildOf)
                ],
                tags=set(entity.tags),
                enabled=world.is_entity_enabled(entity.id),
                parent_id=world.parent_of(entity.id),
            )
        )
        for child_id in sorted(world.children_of(entity.id)):
            if child_id in seen:
                continue
            seen.add(child_id)
            child = world.get_entity(child_id)
            if child is not None:
                frontier.append(child)
    return snapshots


def restore_subtree(world: EntityManager, snapshots: list[EntitySnapshot]) -> None:
    """Rebuild the entities `snapshot_subtree` captured.

    Args:
        world: The world to rebuild into.
        snapshots: Snapshots in parents-first order.
    """
    for snapshot in snapshots:
        entity = world.create_entity(snapshot.entity_id)
        entity.tags.update(snapshot.tags)
        for component in snapshot.components:
            entity.add_component(component)

    # Parents and enabled state in a second pass, for the same reason the
    # scene serializer needs one: a parent may be outside the captured
    # subtree, and `set_parent` raises for an id it cannot find.
    for snapshot in snapshots:
        if snapshot.parent_id is not None:
            world.set_parent(snapshot.entity_id, snapshot.parent_id)
        if not snapshot.enabled:
            world.set_entity_enabled(snapshot.entity_id, False)


class CreateEntity(EditCommand):
    """Add a new entity, optionally with components, tags and a parent."""

    def __init__(
        self,
        entity_id: str,
        *,
        components: list[Component] | None = None,
        tags: set[str] | None = None,
        parent_id: str | None = None,
    ) -> None:
        """Describe the entity to create.

        Args:
            entity_id: The id to give it. Explicit rather than generated,
                so an undo/redo cycle produces the same id and anything
                referring to it -- a selection, a parent link, an agent's
                next call -- still resolves.
            components: Components to attach.
            tags: Tags to set.
            parent_id: An existing entity to parent it to.
        """
        super().__init__()
        self._entity_id = entity_id
        self._components = list(components or [])
        self._tags = set(tags or ())
        self._parent_id = parent_id

    @property
    def label(self) -> str:
        """What the history shows."""
        return f"Create {self._entity_id}"

    @property
    def entity_id(self) -> str:
        """The id of the entity this command creates."""
        return self._entity_id

    def _apply(self, world: EntityManager) -> None:
        """Create the entity.

        Args:
            world: The world to change.

        Raises:
            EditError: If the id is taken, or the parent does not exist.
                Checked first: `add_entity` overwrites a colliding id
                without complaint, so creating onto one would silently
                replace an entity the undo could not bring back.
        """
        if world.get_entity(self._entity_id) is not None:
            raise EditError(
                f"An entity '{self._entity_id}' already exists in this scene."
            )
        if self._parent_id is not None and world.get_entity(self._parent_id) is None:
            raise EditError(f"No parent entity '{self._parent_id}' in this scene.")

        entity = world.create_entity(self._entity_id)
        entity.tags.update(self._tags)
        for component in self._components:
            entity.add_component(component)
        if self._parent_id is not None:
            world.set_parent(self._entity_id, self._parent_id)

    def _revert(self, world: EntityManager) -> None:
        """Remove the entity again.

        Args:
            world: The world to restore.
        """
        world.remove_entity(self._entity_id)
        world.flush_pending_removals()

    def describe(self) -> dict[str, Any]:
        """Describe what was created.

        Returns:
            A JSON-serializable description.
        """
        description = super().describe()
        description.update(
            {
                "entity_id": self._entity_id,
                "components": sorted(
                    type(component).__name__ for component in self._components
                ),
                "tags": sorted(self._tags),
                "parent_id": self._parent_id,
            }
        )
        return description


class DestroyEntity(EditCommand):
    """Remove an entity, and whatever cascades with it."""

    def __init__(self, entity_id: str) -> None:
        """Describe the entity to remove.

        Args:
            entity_id: The root of the subtree to remove.
        """
        super().__init__()
        self._entity_id = entity_id
        self._snapshots: list[EntitySnapshot] = []

    @property
    def label(self) -> str:
        """What the history shows."""
        count = len(self._snapshots)
        if count > 1:
            return f"Destroy {self._entity_id} (+{count - 1})"
        return f"Destroy {self._entity_id}"

    def _apply(self, world: EntityManager) -> None:
        """Snapshot the subtree, then remove it.

        Args:
            world: The world to change.

        Raises:
            EditError: If the entity does not exist.
        """
        self._snapshots = snapshot_subtree(world, self._entity_id)
        world.remove_entity(self._entity_id)
        # Flushed here rather than left to the frame boundary: the undo may
        # recreate these ids before the next frame, and a pending index
        # cleanup keyed on the same id would then discard the new entity's
        # index entries.
        world.flush_pending_removals()

    def _revert(self, world: EntityManager) -> None:
        """Rebuild the whole captured subtree.

        Args:
            world: The world to restore.
        """
        restore_subtree(world, self._snapshots)

    def describe(self) -> dict[str, Any]:
        """Describe what was destroyed.

        Returns:
            A JSON-serializable description.
        """
        description = super().describe()
        description.update(
            {
                "entity_id": self._entity_id,
                "cascaded": [snapshot.entity_id for snapshot in self._snapshots[1:]],
            }
        )
        return description


class AddComponent(EditCommand):
    """Attach a component to an existing entity."""

    def __init__(self, entity_id: str, component: Component) -> None:
        """Describe the component to attach.

        Args:
            entity_id: The entity to attach to.
            component: The component instance. Built by the caller, so the
                agent-facing operation can route a name and a dict through
                `ComponentRegistry` and get its validation for free.
        """
        super().__init__()
        self._entity_id = entity_id
        self._component = component

    @property
    def label(self) -> str:
        """What the history shows."""
        return f"Add {type(self._component).__name__} to {self._entity_id}"

    def _apply(self, world: EntityManager) -> None:
        """Attach the component.

        Args:
            world: The world to change.

        Raises:
            EditError: If the entity is missing, or already has a component
                of this type -- `Entity.add_component` allows one per type,
                so replacing one is a remove followed by an add.
        """
        entity = _require_entity(world, self._entity_id)
        component_type = type(self._component)
        if entity.has_component(component_type):
            raise EditError(
                f"Entity '{self._entity_id}' already has a "
                f"{component_type.__name__}. Remove it first: an entity "
                f"holds at most one component of each type."
            )
        entity.add_component(self._component)

    def _revert(self, world: EntityManager) -> None:
        """Detach the component again.

        Args:
            world: The world to restore.
        """
        entity = world.get_entity(self._entity_id)
        if entity is not None:
            entity.remove_component(type(self._component))

    def describe(self) -> dict[str, Any]:
        """Describe what was attached.

        Returns:
            A JSON-serializable description.
        """
        description = super().describe()
        description.update(
            {
                "entity_id": self._entity_id,
                "component": type(self._component).__name__,
            }
        )
        return description


class RemoveComponent(EditCommand):
    """Detach a component from an entity, keeping it for the undo."""

    def __init__(self, entity_id: str, component_type: type[Component]) -> None:
        """Describe the component to detach.

        Args:
            entity_id: The entity to detach from.
            component_type: Which component to remove.
        """
        super().__init__()
        self._entity_id = entity_id
        self._component_type = component_type
        self._removed: Component | None = None

    @property
    def label(self) -> str:
        """What the history shows."""
        return f"Remove {self._component_type.__name__} from {self._entity_id}"

    def _apply(self, world: EntityManager) -> None:
        """Detach the component, holding the instance for the undo.

        Args:
            world: The world to change.

        Raises:
            EditError: If the entity or the component is missing.
        """
        entity = _require_entity(world, self._entity_id)
        component = _get_component(entity, self._component_type)
        if component is None:
            raise EditError(
                f"Entity '{self._entity_id}' has no {self._component_type.__name__}."
            )
        self._removed = component
        entity.remove_component(self._component_type)

    def _revert(self, world: EntityManager) -> None:
        """Reattach the instance that was removed.

        Args:
            world: The world to restore.
        """
        entity = world.get_entity(self._entity_id)
        if entity is not None and self._removed is not None:
            entity.add_component(self._removed)

    def describe(self) -> dict[str, Any]:
        """Describe what was detached.

        Returns:
            A JSON-serializable description.
        """
        description = super().describe()
        description.update(
            {
                "entity_id": self._entity_id,
                "component": self._component_type.__name__,
            }
        )
        return description


class SetField(EditCommand):
    """Write one field of one component.

    The workhorse: every Inspector edit and every gizmo drag frame is one
    of these. Drags pass `coalesce=True` to `CommandStack.do`, so a whole
    drag collapses into a single undo entry.
    """

    def __init__(
        self,
        entity_id: str,
        component_type: type[Component],
        field_name: str,
        value: Any,
    ) -> None:
        """Describe the write.

        Args:
            entity_id: The owning entity.
            component_type: Which component holds the field.
            field_name: The field to write.
            value: The new value.
        """
        super().__init__()
        self._entity_id = entity_id
        self._component_type = component_type
        self._field_name = field_name
        self._value = value
        self._previous: Any = None

    @property
    def label(self) -> str:
        """What the history shows."""
        return (
            f"Set {self._component_type.__name__}.{self._field_name} "
            f"on {self._entity_id}"
        )

    @property
    def target(self) -> tuple[str, type[Component], str]:
        """What this command writes to, for coalescing comparisons."""
        return (self._entity_id, self._component_type, self._field_name)

    def _apply(self, world: EntityManager) -> None:
        """Write the field and notify the manager.

        Args:
            world: The world to change.

        Raises:
            EditError: If the entity, component or field is missing, or the
                component is a frozen dataclass.
        """
        entity = _require_entity(world, self._entity_id)
        component = _get_component(entity, self._component_type)
        if component is None:
            raise EditError(
                f"Entity '{self._entity_id}' has no {self._component_type.__name__}."
            )
        if not hasattr(component, self._field_name):
            raise EditError(
                f"{self._component_type.__name__} has no field '{self._field_name}'."
            )

        params = getattr(self._component_type, "__dataclass_params__", None)
        if getattr(params, "frozen", False):
            raise EditError(
                f"{self._component_type.__name__} is a frozen dataclass; its "
                f"fields cannot be assigned. Replace the whole component "
                f"instead."
            )

        self._previous = _capture(getattr(component, self._field_name))
        setattr(component, self._field_name, self._value)
        # Mutating a component without this leaves physics bodies, render
        # batches and the spatial index mirroring a value that changed.
        world.notify_component_changed(self._entity_id, self._component_type)

    def _revert(self, world: EntityManager) -> None:
        """Put the previous value back.

        Args:
            world: The world to restore.
        """
        entity = world.get_entity(self._entity_id)
        if entity is None:
            return
        component = _get_component(entity, self._component_type)
        if component is None:
            return
        setattr(component, self._field_name, self._previous)
        world.notify_component_changed(self._entity_id, self._component_type)

    def coalesce_with(self, previous: EditCommand) -> EditCommand | None:
        """Fold into `previous` when both write the same field.

        The merged command keeps `previous`'s captured old value -- the one
        from the start of the gesture -- and this command's new value, so
        undoing the drag returns to where it began rather than to the
        previous frame.

        Args:
            previous: The command on top of the stack.

        Returns:
            A command spanning both writes, or None when they are unrelated.
        """
        if not isinstance(previous, SetField):
            return None
        if previous.target != self.target:
            return None

        merged = SetField(
            self._entity_id,
            self._component_type,
            self._field_name,
            self._value,
        )
        merged._previous = previous._previous
        merged._applied = True
        return merged

    def describe(self) -> dict[str, Any]:
        """Describe the write, old value included.

        Returns:
            A JSON-serializable description. Values are `repr`'d, because a
            component field may hold a texture or another component, which
            no JSON encoder would take.
        """
        description = super().describe()
        description.update(
            {
                "entity_id": self._entity_id,
                "component": self._component_type.__name__,
                "field": self._field_name,
                "from": repr(self._previous),
                "to": repr(self._value),
            }
        )
        return description


class SetParent(EditCommand):
    """Re-parent an entity, or detach it from its parent."""

    def __init__(self, child_id: str, parent_id: str | None) -> None:
        """Describe the re-parenting.

        Args:
            child_id: The entity to move.
            parent_id: Its new parent, or None to detach.
        """
        super().__init__()
        self._child_id = child_id
        self._parent_id = parent_id
        self._previous_parent_id: str | None = None

    @property
    def label(self) -> str:
        """What the history shows."""
        if self._parent_id is None:
            return f"Unparent {self._child_id}"
        return f"Parent {self._child_id} to {self._parent_id}"

    def _apply(self, world: EntityManager) -> None:
        """Set the new parent, remembering the old one.

        Args:
            world: The world to change.

        Raises:
            EditError: If an entity is missing, or the link would make a
                cycle. `EntityManager.set_parent` detects both; they are
                translated here so the caller sees one error type.
        """
        _require_entity(world, self._child_id)
        self._previous_parent_id = world.parent_of(self._child_id)
        try:
            world.set_parent(self._child_id, self._parent_id)
        except (KeyError, ValueError) as exc:
            raise EditError(str(exc)) from exc

    def _revert(self, world: EntityManager) -> None:
        """Restore the previous parent.

        Args:
            world: The world to restore.
        """
        world.set_parent(self._child_id, self._previous_parent_id)

    def describe(self) -> dict[str, Any]:
        """Describe the re-parenting.

        Returns:
            A JSON-serializable description.
        """
        description = super().describe()
        description.update(
            {
                "entity_id": self._child_id,
                "from": self._previous_parent_id,
                "to": self._parent_id,
            }
        )
        return description


class SetEnabled(EditCommand):
    """Enable or disable an entity."""

    def __init__(self, entity_id: str, enabled: bool) -> None:
        """Describe the change.

        Args:
            entity_id: The entity to change.
            enabled: The state to set.
        """
        super().__init__()
        self._entity_id = entity_id
        self._enabled = enabled
        self._previous = True

    @property
    def label(self) -> str:
        """What the history shows."""
        verb = "Enable" if self._enabled else "Disable"
        return f"{verb} {self._entity_id}"

    def _apply(self, world: EntityManager) -> None:
        """Set the enabled state, remembering the old one.

        Args:
            world: The world to change.

        Raises:
            EditError: If the entity does not exist. `set_entity_enabled`
                silently discards an unknown id, which would make this
                command undoable but ineffective.
        """
        _require_entity(world, self._entity_id)
        self._previous = world.is_entity_enabled(self._entity_id)
        world.set_entity_enabled(self._entity_id, self._enabled)

    def _revert(self, world: EntityManager) -> None:
        """Restore the previous enabled state.

        Args:
            world: The world to restore.
        """
        world.set_entity_enabled(self._entity_id, self._previous)

    def describe(self) -> dict[str, Any]:
        """Describe the change.

        Returns:
            A JSON-serializable description.
        """
        description = super().describe()
        description.update(
            {
                "entity_id": self._entity_id,
                "from": self._previous,
                "to": self._enabled,
            }
        )
        return description


class SetTags(EditCommand):
    """Replace an entity's whole tag set.

    Whole-set rather than add/remove because `entity.tags` is a plain
    mutable set with no change hook: there is nothing to subscribe to and
    no way to observe a partial edit, so the smallest honest unit is the
    set itself.
    """

    def __init__(self, entity_id: str, tags: set[str]) -> None:
        """Describe the new tag set.

        Args:
            entity_id: The entity to change.
            tags: The tags it should end up with.
        """
        super().__init__()
        self._entity_id = entity_id
        self._tags = set(tags)
        self._previous: set[str] = set()

    @property
    def label(self) -> str:
        """What the history shows."""
        return f"Set tags on {self._entity_id}"

    def _apply(self, world: EntityManager) -> None:
        """Replace the tag set, remembering the old one.

        Args:
            world: The world to change.

        Raises:
            EditError: If the entity does not exist.
        """
        entity = _require_entity(world, self._entity_id)
        self._previous = set(entity.tags)
        entity.tags.clear()
        entity.tags.update(self._tags)

    def _revert(self, world: EntityManager) -> None:
        """Restore the previous tag set.

        Args:
            world: The world to restore.
        """
        entity = world.get_entity(self._entity_id)
        if entity is None:
            return
        entity.tags.clear()
        entity.tags.update(self._previous)

    def describe(self) -> dict[str, Any]:
        """Describe the change.

        Returns:
            A JSON-serializable description.
        """
        description = super().describe()
        description.update(
            {
                "entity_id": self._entity_id,
                "from": sorted(self._previous),
                "to": sorted(self._tags),
            }
        )
        return description
