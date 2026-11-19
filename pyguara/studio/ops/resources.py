"""The `resources` operation: browse, preview, spawn from and reload assets.

Four verbs behind one operation. `list` reports what the resource
manager has indexed and what it has loaded; `preview` shows one
resource; `spawn` builds an entity from a data file, as an undoable
edit; `reload` re-reads a loaded resource from disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pyguara.common.components import ResourceLink
from pyguara.ecs.component import Component
from pyguara.resources.data import DataResource
from pyguara.resources.loaders.data_loader import JsonLoader
from pyguara.resources.manager import ResourceManager
from pyguara.studio.commands.entity import CreateEntity
from pyguara.studio.model.values import encode
from pyguara.studio.ops._args import schema
from pyguara.studio.ops.registry import Operation, OperationError, RiskClass

if TYPE_CHECKING:
    from pyguara.studio.session import StudioSession

VERBS = ("list", "preview", "spawn", "reload")
"""The values the operation's `operation` argument accepts."""

DEFAULT_LIMIT = 200
"""How many indexed files `list` returns when not told otherwise."""

DATA_EXTENSIONS = frozenset(JsonLoader().supported_extensions)
"""The file suffixes that load as a `DataResource`."""


def resources_operation(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Dispatch one of the resource verbs.

    Args:
        session: The session to act on.
        arguments: Carries `operation`, and what that verb needs.

    Returns:
        The verb's payload.

    Raises:
        OperationError: If the verb is unknown, the session has no
            resource manager, or the verb's own arguments are wrong.
    """
    verb = str(_argument(arguments, "operation"))
    manager = _manager(session)
    if verb == "list":
        return list_resources(
            manager,
            needle=str(arguments.get("filter") or ""),
            limit=int(arguments.get("limit") or DEFAULT_LIMIT),
        )
    if verb == "preview":
        return preview_resource(manager, str(_argument(arguments, "name")))
    if verb == "spawn":
        return _spawn(session, manager, arguments)
    if verb == "reload":
        return _reload(manager, str(_argument(arguments, "name")))
    raise OperationError(
        f"Unknown resources operation '{verb}'. Valid: {', '.join(VERBS)}."
    )


def list_resources(
    manager: ResourceManager, *, needle: str = "", limit: int = DEFAULT_LIMIT
) -> dict[str, Any]:
    """Report the indexed files and the loaded resources.

    Args:
        manager: The resource manager to read.
        needle: Keep only entries whose path or a name contains this,
            ignoring case. Empty keeps everything.
        limit: The most indexed files to return.

    Returns:
        `indexed`, one entry per file with its path and the names that
        load it, sorted by path and cut to `limit`; `indexed_total`, the
        count before the cut; and `loaded`, one entry per cached
        resource with its type, size and reference count.
    """
    lowered = needle.lower()
    names_by_path: dict[str, list[str]] = {}
    for name, path in manager.iter_indexed():
        names_by_path.setdefault(path, []).append(name)

    indexed = [
        {"path": path, "names": sorted(names)}
        for path, names in sorted(names_by_path.items())
        if not lowered
        or lowered in path.lower()
        or any(lowered in name.lower() for name in names)
    ]

    stats = manager.get_cache_stats()["resources"]
    loaded = [
        {
            "path": path,
            "type": info["type"],
            "bytes": info["size_bytes"],
            "references": info["ref_count"],
        }
        for path, info in sorted(stats.items())
        if not lowered or lowered in path.lower()
    ]
    return {
        "indexed": indexed[: max(limit, 0)],
        "indexed_total": len(indexed),
        "loaded": loaded,
    }


def preview_resource(manager: ResourceManager, name: str) -> dict[str, Any]:
    """Describe one resource, with its contents when it is a data file.

    A data file that is not loaded yet is loaded to be read. Anything
    else is described from the cache when it is there and by path alone
    when it is not, so previewing never decodes a texture or a sound.

    Args:
        manager: The resource manager to read.
        name: An indexed name or a path.

    Returns:
        The resolved path, whether it is loaded, its type and size when
        it is, and `data` for a data file.

    Raises:
        OperationError: If a data file cannot be read.
    """
    path = resolve_path(manager, name)
    cached = dict(manager.iter_cached()).get(path)

    if cached is None and Path(path).suffix.lower() in DATA_EXTENSIONS:
        cached = _load_data(manager, path)

    preview: dict[str, Any] = {"path": path, "loaded": cached is not None}
    if cached is None:
        return preview
    preview["type"] = type(cached).__name__
    preview["bytes"] = cached.size_bytes
    if isinstance(cached, DataResource):
        preview["data"] = encode(cached.native_handle)
    return preview


def resolve_path(manager: ResourceManager, name: str) -> str:
    """Turn an indexed name into its path; a path is returned as given.

    Args:
        manager: The resource manager whose index to read.
        name: An indexed name or a path.

    Returns:
        The path the manager would load.
    """
    return dict(manager.iter_indexed()).get(name, name)


def _spawn(
    session: StudioSession, manager: ResourceManager, arguments: dict[str, Any]
) -> Any:
    """Create an entity from a data file's components.

    Each top-level key naming a registered component, with an object for
    its fields, becomes that component. The entity also gets a
    `ResourceLink` recording the file it came from.

    Args:
        session: The session whose history takes the edit.
        manager: The resource manager to load the file with.
        arguments: Carries `name`, and optionally `entity_id`.

    Returns:
        The edit's outcome, the new entity's id, and the top-level keys
        that were not components.

    Raises:
        OperationError: If the file is not a data file, holds no
            component, or one of its components cannot be built.
    """
    path = resolve_path(manager, str(_argument(arguments, "name")))
    data = _load_data(manager, path).native_handle
    if not isinstance(data, dict):
        raise OperationError(
            f"'{path}' holds a {type(data).__name__}, not an object of "
            f"components keyed by name."
        )

    registry = session.registry
    components: list[Component] = [ResourceLink(path)]
    skipped: list[str] = []
    for key, fields in data.items():
        if not (registry.has(key) and isinstance(fields, dict)):
            skipped.append(str(key))
            continue
        try:
            components.append(registry.create(key, fields))
        except Exception as exc:
            raise OperationError(
                f"'{path}': could not build a {key} from {fields!r}: {exc}"
            ) from exc

    if len(components) == 1:
        raise OperationError(
            f"'{path}' names no registered component, so there is nothing "
            f"to spawn. Expected top-level keys like "
            f'{{"Transform": {{...}}}}; found: {", ".join(skipped) or "none"}.'
        )

    entity_id = arguments.get("entity_id")
    entity_id = (
        str(entity_id) if entity_id else _free_id(session, Path(path).stem or "entity")
    )
    outcome = session.apply(
        CreateEntity(entity_id, components=components), action="resources"
    ).to_dict()
    outcome["entity_id"] = entity_id
    outcome["skipped"] = skipped
    return outcome


def _reload(manager: ResourceManager, name: str) -> dict[str, Any]:
    """Re-read a loaded resource from disk.

    Args:
        manager: The resource manager holding it.
        name: An indexed name or a path.

    Returns:
        The path reloaded, and the resource's type and size afterwards.

    Raises:
        OperationError: If it is not loaded, or the file no longer loads.
    """
    path = resolve_path(manager, name)
    try:
        resource = manager.reload(path)
    except KeyError as exc:
        raise OperationError(
            f"'{path}' is not loaded, so there is nothing to reload. "
            f"'list' reports what is."
        ) from exc
    except (OSError, ValueError, TypeError) as exc:
        raise OperationError(f"Reloading '{path}' failed: {exc}") from exc
    return {
        "reloaded": path,
        "type": type(resource).__name__,
        "bytes": resource.size_bytes,
    }


def _load_data(manager: ResourceManager, path: str) -> DataResource:
    """Load a file as a `DataResource`, or raise saying why it is not one.

    Args:
        manager: The resource manager to load with.
        path: The file's path.

    Returns:
        The data resource.

    Raises:
        OperationError: If the suffix is not a data file's, or the file
            is missing or does not parse.
    """
    suffix = Path(path).suffix.lower()
    if suffix not in DATA_EXTENSIONS:
        raise OperationError(
            f"'{path}' is not a data file. Data files end in "
            f"{', '.join(sorted(DATA_EXTENSIONS))}."
        )
    try:
        return manager.load(path, DataResource)
    except (OSError, ValueError, TypeError) as exc:
        raise OperationError(f"Could not read '{path}': {exc}") from exc


def _free_id(session: StudioSession, stem: str) -> str:
    """Return `stem`, or `stem_2`, `stem_3`... when it is taken.

    Args:
        session: The session whose world is checked.
        stem: The id to start from.

    Returns:
        An id no entity in the world has.
    """
    world = session.world
    if world.get_entity(stem) is None:
        return stem
    number = 2
    while world.get_entity(f"{stem}_{number}") is not None:
        number += 1
    return f"{stem}_{number}"


def _manager(session: StudioSession) -> ResourceManager:
    """Return the session's resource manager, or raise saying what is missing.

    Args:
        session: The session.

    Returns:
        Its `ResourceManager`.

    Raises:
        OperationError: If the session was built without one.
    """
    manager = session.resource_manager
    if manager is None:
        raise OperationError(
            "This session cannot reach the resource manager. A session "
            "opened by `attach_studio` can; one built by hand has to be "
            "given a `resource_manager`."
        )
    return manager


def _argument(arguments: dict[str, Any], name: str) -> Any:
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


OPERATIONS: tuple[Operation, ...] = (
    Operation(
        name="resources",
        summary="Browse, preview, spawn from or reload the project's assets.",
        detail=(
            "operation: 'list' reports the files the resource manager has "
            "indexed, each with the names that load it, and the resources "
            "currently loaded. 'preview' describes one, with its contents "
            "when it is a data file. 'spawn' creates an entity from a data "
            "file whose top-level keys are component names -- one undoable "
            "entry -- and reports the keys that were not components. "
            "'reload' re-reads a loaded resource from disk; not undoable."
        ),
        risk=RiskClass.EDIT,
        parameters=schema(
            {
                "operation": {
                    "type": "string",
                    "enum": list(VERBS),
                    "description": "Which of the four to do.",
                },
                "name": {
                    "type": "string",
                    "description": (
                        "An indexed name ('hero', 'hero.json') or a path. "
                        "Required by 'preview', 'spawn' and 'reload'."
                    ),
                },
                "entity_id": {
                    "type": "string",
                    "description": (
                        "The id 'spawn' gives the entity. Defaults to the "
                        "file's stem, numbered if that is taken."
                    ),
                },
                "filter": {
                    "type": "string",
                    "description": "'list' keeps entries containing this text.",
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "The most indexed files 'list' returns. "
                        "'indexed_total' says how many there were."
                    ),
                },
            },
            ["operation"],
        ),
        handler=resources_operation,
    ),
)
