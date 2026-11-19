"""Argument helpers and schema fragments shared by the built-in operations.

Each resolver raises an `OperationError` that names the closest valid
alternative, so a typo costs one round trip rather than a listing.
"""

from __future__ import annotations

import dataclasses
import difflib
from typing import TYPE_CHECKING, Any

from pyguara.ecs.component import Component
from pyguara.studio.ops.registry import OperationError

if TYPE_CHECKING:
    from pyguara.studio.session import StudioSession

# Reused schema fragments. Written once so an argument called `entity_id`
# is described identically everywhere it appears -- an agent that learns
# the shape from one operation should not have to relearn it for the next.
ENTITY_ID = {
    "type": "string",
    "description": "The entity's id, as `scene_tree` or `find_entities` reports it.",
}
COMPONENT_NAME = {
    "type": "string",
    "description": (
        "The component's registered name, which is its class name, e.g. "
        "'Transform'. `list_components` reports every valid name."
    ),
}


def schema(
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


def require(arguments: dict[str, Any], name: str) -> Any:
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


def resolve_entity_id(session: StudioSession, arguments: dict[str, Any]) -> str:
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
    entity_id = str(require(arguments, "entity_id"))
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


def resolve_component_type(
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
    name = str(require(arguments, key))
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


def build_component(
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
        missing = _fields_without_defaults(session, name) - set(fields)
        if missing:
            # Python's own message is "__init__() missing 1 required
            # positional argument", which names the argument and not the
            # component, and says nothing about how to supply it. A
            # `Sprite` cannot be attached without a texture, and a menu
            # that offers it with no fields will fail every time -- so the
            # reply has to be the one that tells you what to send.
            raise OperationError(
                f"A {name} cannot be built without "
                f"{', '.join(sorted(missing))}: {exc}. Pass it in 'fields'; "
                f"`component_schema` gives the type and, for an enum, the "
                f"valid members."
            ) from exc
        raise OperationError(
            f"Could not build a {name} from {fields!r}: {exc}"
        ) from exc


def _fields_without_defaults(session: StudioSession, name: str) -> set[str]:
    """Return the component's fields that have to be supplied.

    Args:
        session: The session, for its registry.
        name: The component's registered name.

    Returns:
        Field names with neither a default nor a default factory, or an
        empty set when the component cannot be reflected over -- in which
        case the caller falls back to the plain message.
    """
    # Widened to `object` first: `is_dataclass` is a TypeGuard, and
    # narrowing a component type through it leaves mypy with an empty
    # intersection, so it calls everything after unreachable.
    component_type: object = session.registry.get(name)
    if component_type is None or not dataclasses.is_dataclass(component_type):
        return set()
    return {
        field.name
        for field in dataclasses.fields(component_type)
        if field.default is dataclasses.MISSING
        and field.default_factory is dataclasses.MISSING
        and not field.name.startswith("_")
    }
