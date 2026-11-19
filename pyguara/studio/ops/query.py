"""Operations that read the open scene, from counts up to one entity in full."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyguara.studio.ops._args import (
    COMPONENT_NAME,
    ENTITY_ID,
    resolve_component_type,
    resolve_entity_id,
    schema,
)
from pyguara.studio.ops.registry import Operation, OperationError, RiskClass

if TYPE_CHECKING:
    from pyguara.studio.session import StudioSession


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
    entity_id = resolve_entity_id(session, arguments)
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
        resolve_component_type(session, arguments, key="component")

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


OPERATIONS: tuple[Operation, ...] = (
    Operation(
        name="scene_summary",
        summary="Entity and component counts for the open scene.",
        detail="The cheap first look; 'scene_tree' is the full read.",
        risk=RiskClass.READ,
        parameters=schema({}),
        handler=_scene_summary,
    ),
    Operation(
        name="scene_tree",
        summary="The open scene's entities and hierarchy.",
        risk=RiskClass.READ,
        parameters=schema(
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
        parameters=schema({"entity_id": ENTITY_ID}, ["entity_id"]),
        handler=_get_entity,
    ),
    Operation(
        name="find_entities",
        summary="Find entity ids by tag, component or id substring.",
        risk=RiskClass.READ,
        parameters=schema(
            {
                "tag": {"type": "string", "description": "An exact tag."},
                "component": COMPONENT_NAME,
                "id_contains": {
                    "type": "string",
                    "description": "A substring of the id.",
                },
            }
        ),
        handler=_find_entities,
    ),
)
