"""A readable, comparable picture of a scene at one instant.

Serves two callers with the same structure, which is why it is one module:

- **An inspector** needs to know what an entity holds right now.
- **An agent** needs that *and* the ability to compare two instants. Its
  loop is edit, run, check -- and "check" is almost always "what changed,
  and was it only what I meant to change?". A snapshot it can diff answers
  that without re-reading the world and reasoning about it in prose.

Everything is encoded through `studio.model.values`, so the shape matches
what the scene serializer writes to disk and what an agent passes back in
to set a field. One vocabulary rather than three.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any

from pyguara.ecs.component import Component
from pyguara.ecs.manager import EntityManager
from pyguara.studio.model.schema import ComponentSchema, describe_component
from pyguara.studio.model.values import encode


@functools.lru_cache(maxsize=256)
def _cached_schema(component_type: type[Component]) -> ComponentSchema:
    """Return `component_type`'s schema, reflecting it at most once.

    `describe_component` calls `typing.get_type_hints`, which is far too
    slow to run per component per entity -- a snapshot of a thousand-entity
    scene would reflect the same dozen types a thousand times each.
    Schemas are frozen and component types are stable, so caching is safe.

    Args:
        component_type: The component class to describe.

    Returns:
        Its schema.
    """
    return describe_component(component_type)


def read_component(component: Component) -> dict[str, Any]:
    """Read one component's readable fields into encoded values.

    Args:
        component: The component to read.

    Derived fields are skipped -- `Transform.rotation_degrees` and
    `world_rotation` restate `rotation`, and recording them would make one
    edit read as three changes in a diff. `previous_position` is skipped
    for a sharper reason: `SceneManager.fixed_update()` rewrites it every
    tick, so including it would make every snapshot taken across a frame
    differ. An inspector still shows them; see
    `ComponentSchema.stateful_fields`.

    Returns:
        Field name to encoded value. A field whose value has no JSON form
        is reported as an unencodable marker rather than silently dropped,
        so the reader knows it is there.
    """
    schema = _cached_schema(type(component))
    values: dict[str, Any] = {}
    for field_schema in schema.stateful_fields:
        try:
            values[field_schema.name] = encode(getattr(component, field_schema.name))
        except Exception as exc:
            # A property whose getter raises -- a derived value that needs
            # state this component does not have yet. Reporting the failure
            # beats omitting the field, which would read as "not present".
            values[field_schema.name] = {"__error__": str(exc)}
    return values


@dataclass(frozen=True)
class EntityView:
    """One entity, as read.

    Attributes:
        entity_id: Its id.
        tags: Its tags, sorted so two reads of the same state compare
            equal -- `entity.tags` is a set and its iteration order is not
            stable across processes.
        enabled: Whether it is enabled.
        parent_id: Its `ChildOf` parent, or None.
        children: Its children's ids, sorted.
        components: Component name to its encoded fields.
    """

    entity_id: str
    tags: tuple[str, ...] = ()
    enabled: bool = True
    parent_id: str | None = None
    children: tuple[str, ...] = ()
    components: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def component_names(self) -> tuple[str, ...]:
        """The attached components' names, sorted."""
        return tuple(sorted(self.components))

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form.

        Empty collections are omitted: a scene snapshot is something an
        agent reads in full, and `"tags": []` on nine hundred entities is
        pure cost.

        Returns:
            The view as a plain dict.
        """
        data: dict[str, Any] = {"id": self.entity_id}
        if self.tags:
            data["tags"] = list(self.tags)
        if not self.enabled:
            data["enabled"] = False
        if self.parent_id is not None:
            data["parent"] = self.parent_id
        if self.children:
            data["children"] = list(self.children)
        if self.components:
            data["components"] = self.components
        return data


@dataclass(frozen=True)
class SceneSnapshot:
    """Every entity in a world at one instant.

    Attributes:
        scene_name: The scene the world belonged to, when known.
        entities: Views by entity id.
    """

    scene_name: str | None = None
    entities: dict[str, EntityView] = field(default_factory=dict)

    @property
    def entity_ids(self) -> tuple[str, ...]:
        """Every entity id, sorted."""
        return tuple(sorted(self.entities))

    @property
    def roots(self) -> tuple[str, ...]:
        """The ids with no parent, sorted."""
        return tuple(
            sorted(
                entity_id
                for entity_id, view in self.entities.items()
                if view.parent_id is None
            )
        )

    def __len__(self) -> int:
        """How many entities the snapshot holds.

        Returns:
            The entity count.
        """
        return len(self.entities)

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form, entities in id order.

        Returns:
            The snapshot as a plain dict.
        """
        return {
            "scene": self.scene_name,
            "entity_count": len(self.entities),
            "entities": [
                self.entities[entity_id].to_dict() for entity_id in self.entity_ids
            ],
        }

    def summary(self) -> dict[str, Any]:
        """Return counts only, with no per-entity detail.

        What to read before deciding whether the full snapshot is worth
        asking for -- the token-cheap first look at an unfamiliar scene.

        Returns:
            Entity and root counts, and how many entities carry each
            component type.
        """
        by_component: dict[str, int] = {}
        for view in self.entities.values():
            for name in view.components:
                by_component[name] = by_component.get(name, 0) + 1

        return {
            "scene": self.scene_name,
            "entity_count": len(self.entities),
            "root_count": len(self.roots),
            "components": dict(sorted(by_component.items())),
        }


def snapshot_scene(
    world: EntityManager,
    *,
    scene_name: str | None = None,
    include_components: bool = True,
) -> SceneSnapshot:
    """Read `world` into a snapshot.

    Args:
        world: The world to read.
        scene_name: The owning scene's name, recorded on the snapshot.
        include_components: Read component fields too. False gives
            structure only -- ids, hierarchy, tags, enabled state -- which
            is much cheaper and is all a diff of *structural* changes
            needs.

    Returns:
        The snapshot.
    """
    entities: dict[str, EntityView] = {}
    for entity in world.get_all_entities():
        components: dict[str, dict[str, Any]] = {}
        if include_components:
            for component in entity.get_all_components():
                components[type(component).__name__] = read_component(component)
        else:
            for component in entity.get_all_components():
                components[type(component).__name__] = {}

        entities[entity.id] = EntityView(
            entity_id=entity.id,
            tags=tuple(sorted(entity.tags)),
            enabled=world.is_entity_enabled(entity.id),
            parent_id=world.parent_of(entity.id),
            children=tuple(sorted(world.children_of(entity.id))),
            components=components,
        )

    return SceneSnapshot(scene_name=scene_name, entities=entities)


@dataclass(frozen=True)
class FieldChange:
    """One field that differs between two snapshots.

    Attributes:
        entity_id: The owning entity.
        component: The component's name.
        field_name: The field that differs.
        before: Its encoded value in the earlier snapshot.
        after: Its encoded value in the later one.
    """

    entity_id: str
    component: str
    field_name: str
    before: Any
    after: Any

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form.

        Returns:
            The change as a plain dict.
        """
        return {
            "entity": self.entity_id,
            "component": self.component,
            "field": self.field_name,
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True)
class SceneDiff:
    """What changed between two snapshots.

    Attributes:
        added: Entity ids present only in the later snapshot.
        removed: Entity ids present only in the earlier one.
        components_added: `(entity_id, component_name)` pairs attached.
        components_removed: Pairs detached.
        fields: Field-level changes.
        tags_changed: Entity ids whose tag set differs.
        enabled_changed: Entity ids whose enabled state differs.
        reparented: Entity ids whose parent differs.
    """

    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    components_added: tuple[tuple[str, str], ...] = ()
    components_removed: tuple[tuple[str, str], ...] = ()
    fields: tuple[FieldChange, ...] = ()
    tags_changed: tuple[str, ...] = ()
    enabled_changed: tuple[str, ...] = ()
    reparented: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """Whether the two snapshots are indistinguishable.

        The assertion an agent wants after an undo, and the one a test
        wants after apply-then-revert.
        """
        return not any(
            (
                self.added,
                self.removed,
                self.components_added,
                self.components_removed,
                self.fields,
                self.tags_changed,
                self.enabled_changed,
                self.reparented,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form, empty sections omitted.

        Returns:
            The diff as a plain dict. `{"changed": false}` when nothing
            differs, so a reader never has to interpret an empty object.
        """
        if self.is_empty:
            return {"changed": False}

        data: dict[str, Any] = {"changed": True}
        if self.added:
            data["added"] = list(self.added)
        if self.removed:
            data["removed"] = list(self.removed)
        if self.components_added:
            data["components_added"] = [
                {"entity": entity_id, "component": name}
                for entity_id, name in self.components_added
            ]
        if self.components_removed:
            data["components_removed"] = [
                {"entity": entity_id, "component": name}
                for entity_id, name in self.components_removed
            ]
        if self.fields:
            data["fields"] = [change.to_dict() for change in self.fields]
        if self.tags_changed:
            data["tags_changed"] = list(self.tags_changed)
        if self.enabled_changed:
            data["enabled_changed"] = list(self.enabled_changed)
        if self.reparented:
            data["reparented"] = list(self.reparented)
        return data


def diff_snapshots(before: SceneSnapshot, after: SceneSnapshot) -> SceneDiff:
    """Compare two snapshots.

    Field comparison is limited to entities and components present in
    both: a field "changing" because its whole entity was created is
    already reported as an addition, and repeating it per field would bury
    the actual edits.

    Args:
        before: The earlier snapshot.
        after: The later snapshot.

    Returns:
        The difference, with every list sorted so the result is stable.
    """
    before_ids = set(before.entities)
    after_ids = set(after.entities)

    components_added: list[tuple[str, str]] = []
    components_removed: list[tuple[str, str]] = []
    field_changes: list[FieldChange] = []
    tags_changed: list[str] = []
    enabled_changed: list[str] = []
    reparented: list[str] = []

    for entity_id in sorted(before_ids & after_ids):
        old = before.entities[entity_id]
        new = after.entities[entity_id]

        if old.tags != new.tags:
            tags_changed.append(entity_id)
        if old.enabled != new.enabled:
            enabled_changed.append(entity_id)
        if old.parent_id != new.parent_id:
            reparented.append(entity_id)

        old_components = set(old.components)
        new_components = set(new.components)
        components_added.extend(
            (entity_id, name) for name in sorted(new_components - old_components)
        )
        components_removed.extend(
            (entity_id, name) for name in sorted(old_components - new_components)
        )

        for name in sorted(old_components & new_components):
            old_fields = old.components[name]
            new_fields = new.components[name]
            for field_name in sorted(set(old_fields) | set(new_fields)):
                old_value = old_fields.get(field_name)
                new_value = new_fields.get(field_name)
                if old_value != new_value:
                    field_changes.append(
                        FieldChange(
                            entity_id=entity_id,
                            component=name,
                            field_name=field_name,
                            before=old_value,
                            after=new_value,
                        )
                    )

    return SceneDiff(
        added=tuple(sorted(after_ids - before_ids)),
        removed=tuple(sorted(before_ids - after_ids)),
        components_added=tuple(components_added),
        components_removed=tuple(components_removed),
        fields=tuple(field_changes),
        tags_changed=tuple(tags_changed),
        enabled_changed=tuple(enabled_changed),
        reparented=tuple(reparented),
    )
