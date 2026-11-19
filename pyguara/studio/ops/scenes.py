"""The `scene` operation: save, open, empty or list the scenes in storage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyguara.studio.commands.entity import DestroyEntity
from pyguara.studio.ops._args import (
    require,
    schema,
)
from pyguara.studio.ops.registry import Operation, OperationError, RiskClass

if TYPE_CHECKING:
    from pyguara.studio.session import StudioSession


def _scene_io(session: StudioSession) -> Any:
    """Return the session's scene access, or raise saying what is missing.

    Args:
        session: The session.

    Returns:
        Its `SceneIO`.

    Raises:
        OperationError: If the session cannot reach the serializer. A
            session built by hand has no container behind it, which is
            every test that does not boot an application.
    """
    scene_io = session.scene_io
    if scene_io is None:
        raise OperationError(
            "This session cannot reach the scene serializer, so it cannot "
            "save or open. A session opened by `attach_studio` can; one "
            "built by hand has no container behind it."
        )
    return scene_io


def _scene(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Dispatch one of the whole-scene verbs.

    Grouped under one operation rather than offered as four, for the
    reason `history` is: the flat surface is budgeted, and a client's tool
    limit is spent on the verbs used every minute. Saving and opening are
    not those.

    Args:
        session: The session to act on.
        arguments: Carries `operation`, and `name` where it applies.

    Returns:
        The verb's payload.

    Raises:
        OperationError: If the verb is not one of the four.
    """
    operation = str(require(arguments, "operation"))
    handlers = {
        "save": _save_scene,
        "open": _open_scene,
        "new": _new_scene,
        "list": _list_scenes,
    }
    handler = handlers.get(operation)
    if handler is None:
        raise OperationError(
            f"Unknown scene operation '{operation}'. "
            f"Valid: {', '.join(sorted(handlers))}."
        )
    return handler(session, arguments)


def _save_scene(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Write the open scene to storage."""
    scene_io = _scene_io(session)
    name = str(arguments.get("name") or session.scene_name or "")
    if not name:
        raise OperationError(
            "No name to save under, and the session does not know the "
            "scene's either. Pass 'name'."
        )
    if not scene_io.save(name):
        raise OperationError(
            f"Saving '{name}' failed. Either no scene is open or the "
            f"storage backend refused the write."
        )
    # Saving is the point at which the history stops being useful: undoing
    # past it would leave the file and the world disagreeing with no sign
    # of it.
    session.stack.clear()
    return {"saved": name, "entities": sum(1 for _ in session.world.get_all_entities())}


def _open_scene(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Replace the open scene's contents with a save."""
    scene_io = _scene_io(session)
    name = str(require(arguments, "name"))
    if not scene_io.exists(name):
        known = ", ".join(scene_io.saves()) or "none"
        raise OperationError(f"No save named '{name}'. Available: {known}.")
    if not scene_io.load(name):
        raise OperationError(f"Opening '{name}' failed; no scene is open.")
    # Not undoable, and the history has to go: every command on it
    # describes a world that no longer exists, so reverting one would
    # apply its inverse to entities it never touched.
    session.stack.clear()
    return {
        "opened": name,
        "entities": sum(1 for _ in session.world.get_all_entities()),
    }


def _list_scenes(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """List every scene the storage backend holds."""
    return {"scenes": _scene_io(session).saves()}


def _new_scene(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Empty the open scene.

    Expressed as a destroy of every root, inside one transaction, so it
    lands on the history as a single entry and undoes as one. An
    `EntityManager.clear()` would be shorter and would not be reversible.
    """
    world = session.world
    roots = [
        entity.id
        for entity in world.get_all_entities()
        if world.parent_of(entity.id) is None
    ]
    if not roots:
        return {"cleared": 0}
    with session.stack.transaction("New scene"):
        for entity_id in roots:
            session.apply(DestroyEntity(entity_id), action="new_scene")
    return {"cleared": len(roots)}


OPERATIONS: tuple[Operation, ...] = (
    Operation(
        name="scene",
        summary="Save, open, empty or list scenes.",
        detail=(
            "operation: 'save' writes the open scene (defaulting to its "
            "own name) and clears the history, because undoing past a "
            "save leaves the file and the world disagreeing. 'open' "
            "replaces the open scene's contents with a saved one -- not "
            "undoable, and it clears the history too, since every command "
            "on it describes a world that no longer exists. 'new' empties "
            "the scene, which *is* one undoable entry. 'list' reports the "
            "names 'open' accepts."
        ),
        risk=RiskClass.WRITE_DISK,
        parameters=schema(
            {
                "operation": {
                    "type": "string",
                    "enum": ["save", "open", "new", "list"],
                    "description": "Which of the four to do.",
                },
                "name": {
                    "type": "string",
                    "description": (
                        "The save's name. Required by 'open'; 'save' "
                        "defaults to the open scene's own name."
                    ),
                },
            },
            ["operation"],
        ),
        handler=_scene,
    ),
)
