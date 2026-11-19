"""Operations that change the open scene's entities and their components.

Each one applies a command through the session, so it is undoable and
returns the diff it produced.
"""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING, Any

from pyguara.ecs.component import Component
from pyguara.studio.commands.entity import (
    AddComponent,
    CreateEntity,
    DestroyEntity,
    DuplicateEntity,
    RemoveComponent,
    SetEnabled,
    SetField,
    SetParent,
    SetTags,
)
from pyguara.studio.model.schema import describe_component
from pyguara.studio.model.values import decode
from pyguara.studio.ops._args import (
    COMPONENT_NAME,
    ENTITY_ID,
    build_component,
    require,
    resolve_component_type,
    resolve_entity_id,
    schema,
)
from pyguara.studio.ops.registry import Operation, OperationError, RiskClass

if TYPE_CHECKING:
    from pyguara.studio.session import StudioSession


def _create_entity(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Create an entity, optionally with components, tags and a parent."""
    entity_id = str(require(arguments, "entity_id"))
    components = [
        build_component(session, name, fields or {})
        for name, fields in (arguments.get("components") or {}).items()
    ]
    parent_id = arguments.get("parent_id")
    if parent_id is not None:
        parent_id = str(parent_id)

    command = CreateEntity(
        entity_id,
        components=components,
        tags=set(arguments.get("tags") or ()),
        parent_id=parent_id,
    )
    return session.apply(command, action="create_entity").to_dict()


def _destroy_entity(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Destroy an entity and whatever cascades with it."""
    entity_id = resolve_entity_id(session, arguments)
    return session.apply(DestroyEntity(entity_id), action="destroy_entity").to_dict()


def _duplicate_entity(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Copy an entity and everything it owns, under fresh ids."""
    entity_id = resolve_entity_id(session, arguments)
    suffix = str(arguments.get("suffix") or "_copy")
    command = DuplicateEntity(entity_id, suffix=suffix)
    outcome = session.apply(command, action="duplicate_entity").to_dict()
    # The new ids, which the caller cannot work out: they depend on what
    # was already taken.
    outcome["created"] = list(command.created_ids)
    return outcome


def _add_component(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Attach a component built from a dict of field values."""
    entity_id = resolve_entity_id(session, arguments)
    name = str(require(arguments, "component"))
    resolve_component_type(session, arguments)
    component = build_component(session, name, arguments.get("fields") or {})
    return session.apply(
        AddComponent(entity_id, component),
        action="add_component",
    ).to_dict()


def _remove_component(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Detach a component."""
    entity_id = resolve_entity_id(session, arguments)
    component_type = resolve_component_type(session, arguments)
    return session.apply(
        RemoveComponent(entity_id, component_type),
        action="remove_component",
    ).to_dict()


def _set_field(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Write one field of one component."""
    entity_id = resolve_entity_id(session, arguments)
    component_type = resolve_component_type(session, arguments)
    field_name = str(require(arguments, "field"))

    schema = describe_component(component_type)
    field_schema = schema.field(field_name)
    if field_schema is None:
        raise OperationError(_unknown_field_message(component_type, schema, field_name))
    if not field_schema.editable:
        raise OperationError(
            f"{component_type.__name__}.{field_name} cannot be set this "
            f"way: it is "
            + (
                "read-only."
                if not field_schema.writable
                else f"a {field_schema.type_name}, which has no JSON form."
            )
        )

    declared = _declared_type(component_type, field_name)
    try:
        value = decode(require(arguments, "value"), declared)
    except ValueError as exc:
        raise OperationError(f"{component_type.__name__}.{field_name}: {exc}") from exc

    return session.apply(
        SetField(entity_id, component_type, field_name, value),
        action="set_field",
        coalesce=bool(arguments.get("coalesce", False)),
    ).to_dict()


def _unknown_field_message(
    component_type: type[Component], schema: Any, field_name: str
) -> str:
    """Compose the error for a field name that does not exist.

    Leads with the closest match, because a wrong field name is almost
    always a typo and a suggestion ends the exchange in one call rather
    than three. The fallback list offers *stateful* fields only: a derived
    one is settable but a poor suggestion -- `previous_position` is
    rewritten by `SceneManager` on every fixed tick, so an agent nudged
    towards it would watch its edit vanish.

    Args:
        component_type: The component the field was looked for on.
        schema: Its `ComponentSchema`.
        field_name: The name that did not resolve.

    Returns:
        The message.
    """
    editable = [field.name for field in schema.editable_fields]
    close = difflib.get_close_matches(field_name, editable, n=1, cutoff=0.6)
    if close:
        return (
            f"{component_type.__name__} has no field '{field_name}'. "
            f"Did you mean '{close[0]}'?"
        )

    stateful = [field.name for field in schema.editable_fields if not field.derived]
    valid = ", ".join(stateful or editable)
    return (
        f"{component_type.__name__} has no field '{field_name}'. "
        f"Editable fields: {valid or 'none'}."
    )


def _declared_type(component_type: type[Component], field_name: str) -> Any:
    """Return a field's runtime type, for decoding.

    Taken from a default instance where one can be made, because the
    schema records a type *name* and decoding needs the class. Falls back
    to None, which leaves `decode` to work the value out from its shape.

    Args:
        component_type: The component class.
        field_name: The field to type.

    Returns:
        The type, or None.
    """
    import dataclasses
    import typing

    try:
        hints = typing.get_type_hints(component_type)
    except Exception:  # pragma: no cover - unresolvable annotation
        hints = {}
    if field_name in hints:
        return hints[field_name]

    candidate: object = component_type
    if dataclasses.is_dataclass(candidate):
        return None

    try:
        probe = component_type()
    except Exception:  # pragma: no cover - needs constructor arguments
        return None
    current = getattr(probe, field_name, None)
    return type(current) if current is not None else None


def _set_parent(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Re-parent an entity, or detach it with a null parent."""
    entity_id = resolve_entity_id(session, arguments)
    parent_id = arguments.get("parent_id")
    return session.apply(
        SetParent(entity_id, None if parent_id is None else str(parent_id)),
        action="set_parent",
    ).to_dict()


def _set_enabled(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Enable or disable an entity."""
    entity_id = resolve_entity_id(session, arguments)
    enabled = require(arguments, "enabled")
    if not isinstance(enabled, bool):
        raise OperationError(f"'enabled' must be true or false, got {enabled!r}.")
    return session.apply(SetEnabled(entity_id, enabled), action="set_enabled").to_dict()


def _set_tags(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Replace an entity's whole tag set."""
    entity_id = resolve_entity_id(session, arguments)
    tags = require(arguments, "tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise OperationError(f"'tags' must be a list of strings, got {tags!r}.")
    return session.apply(SetTags(entity_id, set(tags)), action="set_tags").to_dict()


ENTITY_OPERATIONS: tuple[Operation, ...] = (
    Operation(
        name="create_entity",
        summary="Create an entity with optional components, tags and parent.",
        detail=(
            "The id is yours to choose and is stable across undo and redo, "
            "so later calls can refer to it."
        ),
        risk=RiskClass.EDIT,
        parameters=schema(
            {
                "entity_id": {
                    "type": "string",
                    "description": "The id to give it. Must not already exist.",
                },
                "components": {
                    "type": "object",
                    "description": (
                        "Component name to its field values, e.g. "
                        '{"Transform": {"position": {"x": 10, "y": 0}}}.'
                    ),
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to set on the entity.",
                },
                "parent_id": ENTITY_ID,
            },
            ["entity_id"],
        ),
        handler=_create_entity,
    ),
    Operation(
        name="destroy_entity",
        summary="Destroy an entity and every entity owned by it.",
        detail=(
            "Ownership cascades through ChildOf, so this may remove more "
            "than one entity; the returned diff lists them all."
        ),
        risk=RiskClass.EDIT,
        parameters=schema({"entity_id": ENTITY_ID}, ["entity_id"]),
        handler=_destroy_entity,
    ),
    Operation(
        name="duplicate_entity",
        summary="Copy an entity and everything it owns, under fresh ids.",
        detail=(
            "The copy keeps the original's parent, so a duplicated child "
            "lands beside its sibling. The new ids are in 'created', root "
            "first; they cannot be predicted, since they depend on what "
            "was already taken."
        ),
        risk=RiskClass.EDIT,
        parameters=schema(
            {
                "entity_id": ENTITY_ID,
                "suffix": {
                    "type": "string",
                    "description": (
                        "Appended to each copied id, with a number added "
                        "if that is taken. Defaults to '_copy'."
                    ),
                },
            },
            ["entity_id"],
        ),
        handler=_duplicate_entity,
    ),
)


COMPONENT_OPERATIONS: tuple[Operation, ...] = (
    Operation(
        name="add_component",
        summary="Attach a component, built from a dict of field values.",
        detail="An entity holds at most one component of each type.",
        risk=RiskClass.EDIT,
        parameters=schema(
            {
                "entity_id": ENTITY_ID,
                "component": COMPONENT_NAME,
                "fields": {
                    "type": "object",
                    "description": (
                        "Field values. Omitted fields take their defaults; "
                        "see 'component_schema'."
                    ),
                },
            },
            ["entity_id", "component"],
        ),
        handler=_add_component,
    ),
    Operation(
        name="remove_component",
        summary="Detach a component from an entity.",
        risk=RiskClass.EDIT,
        parameters=schema(
            {"entity_id": ENTITY_ID, "component": COMPONENT_NAME},
            ["entity_id", "component"],
        ),
        handler=_remove_component,
    ),
    Operation(
        name="set_field",
        summary="Write one field of one component on one entity.",
        detail=(
            "Values use the same JSON shapes the scene files do: a Vector2 "
            'is {"x": .., "y": ..}, a Color is {"r": .., "g": .., "b": .., '
            '"a": ..}, an enum is its member name.'
        ),
        risk=RiskClass.EDIT,
        parameters=schema(
            {
                "entity_id": ENTITY_ID,
                "component": COMPONENT_NAME,
                "field": {
                    "type": "string",
                    "description": "The field name, per 'component_schema'.",
                },
                "value": {"description": "The new value."},
                "coalesce": {
                    "type": "boolean",
                    "description": (
                        "Merge with the previous write to the same field, so "
                        "a run of them is one undo step. For a drag, not for "
                        "two deliberate edits."
                    ),
                },
            },
            ["entity_id", "component", "field", "value"],
        ),
        handler=_set_field,
    ),
    Operation(
        name="set_parent",
        summary="Re-parent an entity, or detach it with a null parent.",
        detail="Ownership, which cascades on destroy. A cycle is refused.",
        risk=RiskClass.EDIT,
        parameters=schema(
            {
                "entity_id": ENTITY_ID,
                "parent_id": {
                    "type": ["string", "null"],
                    "description": "The new parent's id, or null to detach.",
                },
            },
            ["entity_id"],
        ),
        handler=_set_parent,
    ),
    Operation(
        name="set_enabled",
        summary="Enable or disable an entity.",
        risk=RiskClass.EDIT,
        parameters=schema(
            {"entity_id": ENTITY_ID, "enabled": {"type": "boolean"}},
            ["entity_id", "enabled"],
        ),
        handler=_set_enabled,
    ),
    Operation(
        name="set_tags",
        summary="Replace an entity's whole tag set.",
        detail=(
            "Whole-set, not add or remove: entity tags are a plain set with "
            "no change hook, so the set is the smallest honest unit."
        ),
        risk=RiskClass.EDIT,
        parameters=schema(
            {
                "entity_id": ENTITY_ID,
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            ["entity_id", "tags"],
        ),
        handler=_set_tags,
    ),
)
