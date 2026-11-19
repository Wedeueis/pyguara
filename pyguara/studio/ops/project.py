"""Operations that read the project: its inventory and its component types."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyguara import native
from pyguara.studio.model.projectmap import build_project_map
from pyguara.studio.model.schema import describe_component, describe_registry
from pyguara.studio.ops._args import (
    COMPONENT_NAME,
    resolve_component_type,
    schema,
)
from pyguara.studio.ops.registry import Operation, OperationError, RiskClass

if TYPE_CHECKING:
    from pyguara.studio.session import StudioSession


def _engine_section(status: dict[str, Any]) -> str:
    """Render where the native extension came from as a Markdown section."""
    lines = [
        "## Engine",
        "",
        f"- Native extension: **{'loaded' if status['loaded'] else 'not found'}**",
    ]
    if status["source"]:
        lines.append(f"- Extension: `{status['source']}`")
    return "\n".join(lines)


def _project_overview(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Return the budgeted project inventory, and which engine is running it.

    The extension is reported here, in the handler, rather than on
    `ProjectMap`: it is a fact about *this process on this machine*, and
    `ProjectMap` is also what `pyguara studio instructions` renders into a
    committed `AGENTS.md`, where a local `target/release/*.so` path would
    churn between contributors.
    """
    if session.project_root is None:
        raise OperationError(
            "This session has no project root, so there is no project to "
            "map. Open Studio against a project directory."
        )
    budget = int(arguments.get("budget", 8000))
    project_map = build_project_map(session.project_root, registry=session.registry)
    status = native.status()
    if arguments.get("format") == "markdown":
        # Reserved out of the budget rather than appended to it, so the
        # documented character ceiling stays a ceiling. The engine
        # section goes first: it is three lines, and it is the part a
        # reader cannot find out any other way.
        section = _engine_section(status)
        remaining = budget - len(section) - 2
        if remaining <= 0:
            return {"markdown": section[:budget]}
        return {"markdown": f"{section}\n\n{project_map.to_markdown(remaining)}"}
    return {**project_map.to_dict(), "engine": status}


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
    component_type = resolve_component_type(session, arguments)
    schema = describe_component(component_type)
    return {
        "schema": schema.to_dict(),
        "json_schema": schema.to_json_schema(),
    }


OPERATIONS: tuple[Operation, ...] = (
    Operation(
        name="project_overview",
        summary="Inventory the project: scenes, prefabs, components, assets.",
        detail=(
            "Read this first in an unfamiliar project. Also reports which "
            "native store is in force, which changes simulation results."
        ),
        risk=RiskClass.READ,
        parameters=schema(
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
        parameters=schema(
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
        parameters=schema({"component": COMPONENT_NAME}, ["component"]),
        handler=_component_schema,
    ),
)
