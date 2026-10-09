"""The operations Studio ships with.

Deliberately around twenty, grouped so an agent can hold the list in
mind: look at the project, look at a scene, change a scene, manage the
history, manage approvals. Rarer work goes behind `scene_file` and
`history`, which take an `operation` argument, rather than becoming
another dozen top-level entries -- a client has a limit on how many tools
it will present, and an agent's accuracy falls as the list grows.

Three conventions run through all of them:

- **An entity is named by id.** Not by index, not by a handle from an
  earlier call. Ids survive undo, redo and reload, so an agent's second
  call still means what its first one did.
- **Errors name the alternative.** "No entity 'playr'" is a dead end;
  "No entity 'playr'. Did you mean 'player'?" is a correction. The error
  text *is* the agent's recovery path.
- **Every edit returns its diff.** So the answer to "did that do what I
  meant?" is in the reply, and does not cost another call.
"""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING, Any

from pyguara.ecs.component import Component
from pyguara.studio.commands.entity import (
    AddComponent,
    CreateEntity,
    DestroyEntity,
    RemoveComponent,
    SetEnabled,
    SetField,
    SetParent,
    SetTags,
)
from pyguara.studio.model.projectmap import build_project_map
from pyguara.studio.model.schema import describe_component, describe_registry
from pyguara.studio.model.values import decode
from pyguara.studio.ops.registry import (
    Operation,
    OperationError,
    OperationRegistry,
    RiskClass,
)

if TYPE_CHECKING:
    from pyguara.studio.session import StudioSession

# Reused schema fragments. Written once so an argument called `entity_id`
# is described identically everywhere it appears -- an agent that learns
# the shape from one operation should not have to relearn it for the next.
_ENTITY_ID = {
    "type": "string",
    "description": "The entity's id, as `scene_tree` or `find_entities` reports it.",
}
_COMPONENT_NAME = {
    "type": "string",
    "description": (
        "The component's registered name, which is its class name, e.g. "
        "'Transform'. `list_components` reports every valid name."
    ),
}


def _schema(
    properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    """Build an argument schema that refuses unknown properties.

    `additionalProperties: false` throughout, so a typo'd argument name is
    an error rather than a silently ignored key -- an operation reporting
    success without doing what was asked is the most confusing failure an
    agent can get, because the reply says it worked.

    Args:
        properties: The argument schemas by name.
        required: Which arguments are mandatory.

    Returns:
        A JSON Schema object.
    """
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


# --------------------------------------------------------------------
# Argument helpers
# --------------------------------------------------------------------


def _require(arguments: dict[str, Any], name: str) -> Any:
    """Return a mandatory argument, or raise naming it.

    Args:
        arguments: The supplied arguments.
        name: The argument to read.

    Returns:
        Its value.

    Raises:
        OperationError: If it is missing.
    """
    if name not in arguments:
        raise OperationError(f"Missing required argument '{name}'.")
    return arguments[name]


def _entity_id(session: StudioSession, arguments: dict[str, Any]) -> str:
    """Return the `entity_id` argument, checking it resolves.

    Args:
        session: The session to look in.
        arguments: The supplied arguments.

    Returns:
        The id.

    Raises:
        OperationError: If the argument is missing, or no such entity
            exists -- suggesting the closest ids that do, since a wrong id
            is usually a typo or a stale reference and the suggestion
            saves a round trip.
    """
    entity_id = str(_require(arguments, "entity_id"))
    if session.world.get_entity(entity_id) is not None:
        return entity_id

    known = [entity.id for entity in session.world.get_all_entities()]
    close = difflib.get_close_matches(entity_id, known, n=3, cutoff=0.5)
    if close:
        raise OperationError(
            f"No entity '{entity_id}'. Did you mean "
            f"{', '.join(repr(name) for name in close)}?"
        )
    raise OperationError(
        f"No entity '{entity_id}'. The scene holds {len(known)} entities; "
        f"call 'scene_tree' to see them."
    )


def _component_type(
    session: StudioSession, arguments: dict[str, Any], key: str = "component"
) -> type[Component]:
    """Resolve a component name to its class.

    Args:
        session: The session, for its registry.
        arguments: The supplied arguments.
        key: Which argument holds the name.

    Returns:
        The component class.

    Raises:
        OperationError: If the argument is missing or the name is not
            registered, suggesting the closest registered names.
    """
    name = str(_require(arguments, key))
    component_type = session.registry.get(name)
    if component_type is not None:
        return component_type

    known = session.registry.list_components()
    close = difflib.get_close_matches(name, known, n=3, cutoff=0.5)
    if close:
        raise OperationError(
            f"No component named '{name}'. Did you mean "
            f"{', '.join(repr(other) for other in close)}?"
        )
    raise OperationError(
        f"No component named '{name}'. Call 'list_components' for the "
        f"{len(known)} registered names."
    )


def _build_component(
    session: StudioSession, name: str, fields: dict[str, Any]
) -> Component:
    """Construct a component from a name and a dict of fields.

    Routed through `ComponentRegistry.create`, which is the same path the
    scene serializer and the prefab factory take -- so an agent's call is
    validated exactly as a prefab file is, and its error message already
    enumerates the valid field names.

    Args:
        session: The session, for its registry.
        name: The component's registered name.
        fields: The field values, encoded.

    Returns:
        The component instance.

    Raises:
        OperationError: If the component cannot be built, carrying the
            registry's own message about which fields are valid.
    """
    try:
        return session.registry.create(name, fields)
    except Exception as exc:
        raise OperationError(
            f"Could not build a {name} from {fields!r}: {exc}"
        ) from exc


# --------------------------------------------------------------------
# Reading the project
# --------------------------------------------------------------------


def _project_overview(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Return the budgeted project inventory."""
    if session.project_root is None:
        raise OperationError(
            "This session has no project root, so there is no project to "
            "map. Open Studio against a project directory."
        )
    budget = int(arguments.get("budget", 8000))
    project_map = build_project_map(session.project_root, registry=session.registry)
    if arguments.get("format") == "markdown":
        return {"markdown": project_map.to_markdown(budget)}
    return project_map.to_dict()


def _list_components(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Return every registered component, optionally with full schemas."""
    if not arguments.get("with_schemas"):
        return {"components": list(session.registry.list_components())}
    return {
        "components": {
            name: schema.to_dict()
            for name, schema in describe_registry(session.registry).items()
        }
    }


def _component_schema(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Return one component's schema and its JSON Schema."""
    component_type = _component_type(session, arguments)
    schema = describe_component(component_type)
    return {
        "schema": schema.to_dict(),
        "json_schema": schema.to_json_schema(),
    }


# --------------------------------------------------------------------
# Reading the scene
# --------------------------------------------------------------------


def _scene_summary(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Return counts only -- the cheap first look at a scene."""
    return session.snapshot(include_components=False).summary()


def _scene_tree(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Return the entity hierarchy, with or without component fields."""
    include = bool(arguments.get("include_fields", False))
    snapshot = session.snapshot(include_components=include)
    return snapshot.to_dict()


def _get_entity(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Return one entity in full."""
    entity_id = _entity_id(session, arguments)
    snapshot = session.snapshot()
    return snapshot.entities[entity_id].to_dict()


def _find_entities(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Return the ids matching a tag, a component, or an id substring."""
    snapshot = session.snapshot(include_components=False)
    tag = arguments.get("tag")
    component = arguments.get("component")
    id_contains = arguments.get("id_contains")

    if tag is None and component is None and id_contains is None:
        raise OperationError(
            "Give at least one of 'tag', 'component' or 'id_contains'. "
            "Listing every entity is what 'scene_tree' is for."
        )

    if component is not None:
        # Validated so a misspelled component name is an error rather than
        # an empty result, which reads as "no entity has this" and sends an
        # agent looking for the wrong problem.
        _component_type(session, arguments, key="component")

    matches = []
    for entity_id, view in snapshot.entities.items():
        if tag is not None and tag not in view.tags:
            continue
        if component is not None and component not in view.components:
            continue
        if id_contains is not None and id_contains not in entity_id:
            continue
        matches.append(entity_id)

    return {"entity_ids": sorted(matches), "match_count": len(matches)}


# --------------------------------------------------------------------
# Changing the scene
# --------------------------------------------------------------------


def _create_entity(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Create an entity, optionally with components, tags and a parent."""
    entity_id = str(_require(arguments, "entity_id"))
    components = [
        _build_component(session, name, fields or {})
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
    entity_id = _entity_id(session, arguments)
    return session.apply(DestroyEntity(entity_id), action="destroy_entity").to_dict()


def _add_component(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Attach a component built from a dict of field values."""
    entity_id = _entity_id(session, arguments)
    name = str(_require(arguments, "component"))
    _component_type(session, arguments)
    component = _build_component(session, name, arguments.get("fields") or {})
    return session.apply(
        AddComponent(entity_id, component),
        action="add_component",
    ).to_dict()


def _remove_component(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Detach a component."""
    entity_id = _entity_id(session, arguments)
    component_type = _component_type(session, arguments)
    return session.apply(
        RemoveComponent(entity_id, component_type),
        action="remove_component",
    ).to_dict()


def _set_field(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Write one field of one component."""
    entity_id = _entity_id(session, arguments)
    component_type = _component_type(session, arguments)
    field_name = str(_require(arguments, "field"))

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
        value = decode(_require(arguments, "value"), declared)
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
    entity_id = _entity_id(session, arguments)
    parent_id = arguments.get("parent_id")
    return session.apply(
        SetParent(entity_id, None if parent_id is None else str(parent_id)),
        action="set_parent",
    ).to_dict()


def _set_enabled(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Enable or disable an entity."""
    entity_id = _entity_id(session, arguments)
    enabled = _require(arguments, "enabled")
    if not isinstance(enabled, bool):
        raise OperationError(f"'enabled' must be true or false, got {enabled!r}.")
    return session.apply(SetEnabled(entity_id, enabled), action="set_enabled").to_dict()


def _set_tags(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Replace an entity's whole tag set."""
    entity_id = _entity_id(session, arguments)
    tags = _require(arguments, "tags")
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise OperationError(f"'tags' must be a list of strings, got {tags!r}.")
    return session.apply(SetTags(entity_id, set(tags)), action="set_tags").to_dict()


# --------------------------------------------------------------------
# History and approvals
# --------------------------------------------------------------------


def _history(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Inspect or move the undo history."""
    operation = str(arguments.get("operation", "list"))

    if operation == "list":
        return {
            "undo": list(session.stack.undo_labels),
            "redo": list(session.stack.redo_labels),
        }
    if operation == "undo":
        outcome = session.undo()
        if outcome is None:
            return {"status": "nothing_to_undo"}
        return outcome.to_dict()
    if operation == "redo":
        outcome = session.redo()
        if outcome is None:
            return {"status": "nothing_to_redo"}
        return outcome.to_dict()
    if operation == "undo_to":
        index = arguments.get("index")
        if not isinstance(index, int):
            raise OperationError("'undo_to' needs an integer 'index'.")
        before = session.snapshot()
        reverted = session.stack.undo_to(index)
        session.journal.record(
            session.actor, "undo_to", detail={"index": index, "reverted": reverted}
        )
        from pyguara.studio.model.snapshot import diff_snapshots

        return {
            "reverted": reverted,
            "diff": diff_snapshots(before, session.snapshot()).to_dict(),
        }

    raise OperationError(
        f"Unknown history operation '{operation}'. Valid: list, undo, redo, undo_to."
    )


def _journal(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Read back what has been done this session."""
    if arguments.get("failures_only"):
        entries = session.journal.failures()
    else:
        entries = session.journal.tail(int(arguments.get("count", 20)))
    return {"entries": [entry.to_dict() for entry in entries]}


def _approvals(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """List, approve or reject edits waiting for a person."""
    operation = str(arguments.get("operation", "list"))

    if operation == "list":
        return {
            "approval_mode": session.approval_mode.value,
            "pending": [entry.to_dict() for entry in session.pending],
        }
    if operation == "approve":
        pending_id = str(_require(arguments, "pending_id"))
        return session.approve(pending_id).to_dict()
    if operation == "reject":
        pending_id = str(_require(arguments, "pending_id"))
        return session.reject(pending_id, str(arguments.get("reason", ""))).to_dict()

    raise OperationError(
        f"Unknown approvals operation '{operation}'. Valid: list, approve, reject."
    )


def _list_operations(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Return every operation, so a client can discover the surface."""
    registry = default_registry()
    return {
        "operations": [
            {
                "name": operation.name,
                "summary": operation.summary,
                "risk": operation.risk.value,
            }
            for operation in registry
        ]
    }


# --------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------


def build_registry() -> OperationRegistry:
    """Build a registry holding every built-in operation.

    Returns:
        A fresh registry.
    """
    registry = OperationRegistry()
    for operation in _OPERATIONS:
        registry.register(operation)
    return registry


_DEFAULT_REGISTRY: OperationRegistry | None = None


def default_registry() -> OperationRegistry:
    """Return the shared registry, building it once.

    Args:
        None.

    Returns:
        The process-wide registry. A caller that wants an isolated one --
        a test, or a game adding its own operations -- uses
        `build_registry()` instead.
    """
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = build_registry()
    return _DEFAULT_REGISTRY


_OPERATIONS: tuple[Operation, ...] = (
    # ---- discovery -------------------------------------------------
    Operation(
        name="list_operations",
        summary="List every Studio operation with its risk class.",
        risk=RiskClass.READ,
        parameters=_schema({}),
        handler=_list_operations,
    ),
    Operation(
        name="project_overview",
        summary="Inventory the project: scenes, prefabs, components, assets.",
        detail="Read this first in an unfamiliar project.",
        risk=RiskClass.READ,
        parameters=_schema(
            {
                "format": {
                    "type": "string",
                    "enum": ["json", "markdown"],
                    "description": "'markdown' is compact prose; 'json' is structured.",
                },
                "budget": {
                    "type": "integer",
                    "description": "Character budget for the markdown form.",
                },
            }
        ),
        handler=_project_overview,
    ),
    Operation(
        name="list_components",
        summary="List every component type that can be attached by name.",
        risk=RiskClass.READ,
        parameters=_schema(
            {
                "with_schemas": {
                    "type": "boolean",
                    "description": (
                        "Include each component's full field schema. Much "
                        "larger; prefer 'component_schema' for one type."
                    ),
                }
            }
        ),
        handler=_list_components,
    ),
    Operation(
        name="component_schema",
        summary="Describe one component's fields, types, defaults and enums.",
        detail="Call this before 'add_component' or 'set_field' on a type you have not used.",
        risk=RiskClass.READ,
        parameters=_schema({"component": _COMPONENT_NAME}, ["component"]),
        handler=_component_schema,
    ),
    # ---- reading the scene -----------------------------------------
    Operation(
        name="scene_summary",
        summary="Entity and component counts for the open scene.",
        detail="The cheap first look; 'scene_tree' is the full read.",
        risk=RiskClass.READ,
        parameters=_schema({}),
        handler=_scene_summary,
    ),
    Operation(
        name="scene_tree",
        summary="The open scene's entities and hierarchy.",
        risk=RiskClass.READ,
        parameters=_schema(
            {
                "include_fields": {
                    "type": "boolean",
                    "description": (
                        "Include every component's field values. Large on a "
                        "real scene; omit it to get structure only."
                    ),
                }
            }
        ),
        handler=_scene_tree,
    ),
    Operation(
        name="get_entity",
        summary="One entity's components, fields, tags and hierarchy.",
        risk=RiskClass.READ,
        parameters=_schema({"entity_id": _ENTITY_ID}, ["entity_id"]),
        handler=_get_entity,
    ),
    Operation(
        name="find_entities",
        summary="Find entity ids by tag, component or id substring.",
        risk=RiskClass.READ,
        parameters=_schema(
            {
                "tag": {"type": "string", "description": "An exact tag."},
                "component": _COMPONENT_NAME,
                "id_contains": {
                    "type": "string",
                    "description": "A substring of the id.",
                },
            }
        ),
        handler=_find_entities,
    ),
    # ---- changing the scene ----------------------------------------
    Operation(
        name="create_entity",
        summary="Create an entity with optional components, tags and parent.",
        detail=(
            "The id is yours to choose and is stable across undo and redo, "
            "so later calls can refer to it."
        ),
        risk=RiskClass.EDIT,
        parameters=_schema(
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
                "parent_id": _ENTITY_ID,
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
        parameters=_schema({"entity_id": _ENTITY_ID}, ["entity_id"]),
        handler=_destroy_entity,
    ),
    Operation(
        name="add_component",
        summary="Attach a component, built from a dict of field values.",
        detail="An entity holds at most one component of each type.",
        risk=RiskClass.EDIT,
        parameters=_schema(
            {
                "entity_id": _ENTITY_ID,
                "component": _COMPONENT_NAME,
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
        parameters=_schema(
            {"entity_id": _ENTITY_ID, "component": _COMPONENT_NAME},
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
        parameters=_schema(
            {
                "entity_id": _ENTITY_ID,
                "component": _COMPONENT_NAME,
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
        parameters=_schema(
            {
                "entity_id": _ENTITY_ID,
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
        parameters=_schema(
            {"entity_id": _ENTITY_ID, "enabled": {"type": "boolean"}},
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
        parameters=_schema(
            {
                "entity_id": _ENTITY_ID,
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            ["entity_id", "tags"],
        ),
        handler=_set_tags,
    ),
    # ---- history and approvals -------------------------------------
    Operation(
        name="history",
        summary="List, undo, redo or rewind the edit history.",
        detail=(
            "operation: 'list' shows the stacks, 'undo'/'redo' move one "
            "step, 'undo_to' takes an 'index' and rewinds to it."
        ),
        risk=RiskClass.EDIT,
        parameters=_schema(
            {
                "operation": {
                    "type": "string",
                    "enum": ["list", "undo", "redo", "undo_to"],
                },
                "index": {
                    "type": "integer",
                    "description": "For 'undo_to': how many edits to leave applied.",
                },
            }
        ),
        handler=_history,
    ),
    Operation(
        name="journal",
        summary="Read back the actions taken this session, newest last.",
        detail=(
            "Includes failures, and who asked for each action. The place to "
            "look when something went wrong several edits ago."
        ),
        risk=RiskClass.READ,
        parameters=_schema(
            {
                "count": {
                    "type": "integer",
                    "description": "How many recent entries to return.",
                },
                "failures_only": {
                    "type": "boolean",
                    "description": "Return only the actions that failed.",
                },
            }
        ),
        handler=_journal,
    ),
    Operation(
        name="approvals",
        summary="List, approve or reject edits waiting for a person.",
        detail=(
            "Only used when the session's approval mode is 'ask', in which "
            "case every edit is queued with the diff it would make."
        ),
        risk=RiskClass.EDIT,
        parameters=_schema(
            {
                "operation": {
                    "type": "string",
                    "enum": ["list", "approve", "reject"],
                },
                "pending_id": {
                    "type": "string",
                    "description": "The handle from the queued edit's result.",
                },
                "reason": {
                    "type": "string",
                    "description": "For 'reject': why, recorded in the journal.",
                },
            }
        ),
        handler=_approvals,
    ),
)
