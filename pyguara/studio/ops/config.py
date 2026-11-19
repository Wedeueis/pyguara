"""The `config` operation: read, change and save the engine configuration.

Three verbs behind one operation. `get` reports every section with each
setting's type, value and default; `set` changes one setting as an
undoable edit; `save` writes the configuration file.
"""

from __future__ import annotations

import difflib
import types
import typing
from typing import TYPE_CHECKING, Any, Union

from pyguara.config.manager import ConfigManager
from pyguara.studio.commands.config import SetConfigSetting
from pyguara.studio.model.schema import describe_fields
from pyguara.studio.model.values import decode, encode
from pyguara.studio.ops._args import schema
from pyguara.studio.ops.registry import Operation, OperationError, RiskClass

if TYPE_CHECKING:
    from pyguara.studio.session import StudioSession

VERBS = ("get", "set", "save")
"""The values the operation's `operation` argument accepts."""


def config_operation(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Dispatch one of the configuration verbs.

    Args:
        session: The session to act on.
        arguments: Carries `operation`, and what that verb needs.

    Returns:
        The verb's payload.

    Raises:
        OperationError: If the verb is unknown, the session has no
            configuration, or the verb's own arguments are wrong.
    """
    verb = str(_argument(arguments, "operation"))
    manager = _manager(session)
    if verb == "get":
        return describe_config(manager, arguments.get("section"))
    if verb == "set":
        return _set(session, manager, arguments)
    if verb == "save":
        return _save(manager)
    raise OperationError(
        f"Unknown config operation '{verb}'. Valid: {', '.join(VERBS)}."
    )


def describe_config(manager: ConfigManager, section: Any = None) -> dict[str, Any]:
    """Report the configuration's sections and settings.

    Args:
        manager: The configuration to read.
        section: One section's name, or None for all of them.

    Returns:
        The file the configuration saves to, the active profiles, and
        each section's settings by name. A setting carries its type,
        value and default, an enum's accepted values, and the profile
        that pins it when one does.

    Raises:
        OperationError: If `section` names no section.
    """
    config = manager.config
    if section is None:
        names = config.section_names()
    else:
        _section(manager, str(section))
        names = [str(section)]

    sections: dict[str, Any] = {}
    for name in names:
        instance = config.get_section(name)
        settings: dict[str, Any] = {}
        for field in describe_fields(type(instance)):
            entry = field.to_dict()
            del entry["name"]
            entry["value"] = encode(getattr(instance, field.name))
            pinned_by = manager.pinned_by(name, field.name)
            if pinned_by is not None:
                entry["pinned_by"] = pinned_by
            settings[field.name] = entry
        sections[name] = settings

    return {
        "file": str(manager.file_path),
        "active_profiles": list(manager.active_profiles),
        "sections": sections,
    }


def _set(
    session: StudioSession, manager: ConfigManager, arguments: dict[str, Any]
) -> Any:
    """Change one setting through the session's history.

    Args:
        session: The session whose history takes the edit.
        manager: The configuration to write to.
        arguments: Carries `section`, `setting` and `value`.

    Returns:
        The edit's outcome, plus the setting's value afterwards.

    Raises:
        OperationError: If the section or setting is unknown, or the
            value does not decode to the setting's type.
    """
    section_name = str(_argument(arguments, "section"))
    setting = str(_argument(arguments, "setting"))
    section = _section(manager, section_name)

    hints = typing.get_type_hints(type(section))
    if setting not in hints or not hasattr(section, setting):
        known = sorted(field.name for field in describe_fields(type(section)))
        close = difflib.get_close_matches(setting, known, n=3)
        hint = f" Did you mean {', '.join(close)}?" if close else ""
        raise OperationError(
            f"No setting '{section_name}.{setting}'.{hint} "
            f"Settings of '{section_name}': {', '.join(known)}."
        )

    raw = _argument(arguments, "value")
    try:
        value = _decode_setting(raw, hints[setting])
    except ValueError as exc:
        raise OperationError(f"{section_name}.{setting}: {exc}") from exc

    outcome = session.apply(
        SetConfigSetting(manager, section_name, setting, value),
        action="config",
        coalesce=bool(arguments.get("coalesce", False)),
    ).to_dict()
    outcome["value"] = encode(getattr(section, setting))
    return outcome


def _save(manager: ConfigManager) -> dict[str, Any]:
    """Write the configuration file.

    Args:
        manager: The configuration to save.

    Returns:
        The path written.

    Raises:
        OperationError: If the write failed.
    """
    if not manager.save():
        raise OperationError(
            f"Saving to '{manager.file_path}' failed; the engine log says why."
        )
    return {"saved": str(manager.file_path)}


def _manager(session: StudioSession) -> ConfigManager:
    """Return the session's configuration, or raise saying what is missing.

    Args:
        session: The session.

    Returns:
        Its `ConfigManager`.

    Raises:
        OperationError: If the session was built without one.
    """
    manager = session.config_manager
    if manager is None:
        raise OperationError(
            "This session cannot reach the engine configuration. A session "
            "opened by `attach_studio` can; one built by hand has to be "
            "given a `config_manager`."
        )
    return manager


def _section(manager: ConfigManager, name: str) -> Any:
    """Return a section by name, or raise naming the ones that exist.

    Args:
        manager: The configuration to read.
        name: The section's name.

    Returns:
        The live section instance.

    Raises:
        OperationError: If there is no such section.
    """
    section = manager.config.get_section(name)
    if section is None:
        known = manager.config.section_names()
        raise OperationError(
            f"No config section '{name}'. Sections: {', '.join(known)}."
        )
    return section


def _decode_setting(raw: Any, declared: Any) -> Any:
    """Decode an argument into a setting's declared type.

    Args:
        raw: The value as it arrived.
        declared: The setting's resolved annotation.

    Returns:
        The decoded value. None passes through for an optional setting.

    Raises:
        ValueError: If the value does not fit the type.
    """
    if typing.get_origin(declared) in (Union, types.UnionType):
        members = [m for m in typing.get_args(declared) if m is not type(None)]
        if raw is None and len(members) < len(typing.get_args(declared)):
            return None
        if len(members) == 1:
            declared = members[0]
    if raw is None:
        raise ValueError("Expected a value, got null.")
    return decode(raw, declared)


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
        name="config",
        summary="Read, change or save the engine configuration.",
        detail=(
            "operation: 'get' reports every section, or one, with each "
            "setting's type, value, default and an enum's valid names. "
            "'set' changes one setting as an undoable edit; it is refused "
            "with the reason when the value is the wrong type, fails "
            "validation, or the setting is pinned by an active profile. A "
            "subsystem that read the setting at startup does not notice "
            "the change. 'save' writes the configuration file; a setting "
            "an active profile overrides is written with the value under it."
        ),
        risk=RiskClass.WRITE_DISK,
        parameters=schema(
            {
                "operation": {
                    "type": "string",
                    "enum": list(VERBS),
                    "description": "Which of the three to do.",
                },
                "section": {
                    "type": "string",
                    "description": (
                        "The section's name, e.g. 'physics'. Required by "
                        "'set'; narrows 'get' to one section."
                    ),
                },
                "setting": {
                    "type": "string",
                    "description": "The setting within the section, for 'set'.",
                },
                "value": {
                    "description": (
                        "The new value, for 'set'. An enum takes a member "
                        "name; a colour takes {r, g, b, a}."
                    ),
                },
                "coalesce": {
                    "type": "boolean",
                    "description": (
                        "Fold this 'set' into the previous one when both "
                        "write the same setting, so a dragged control is "
                        "one history entry."
                    ),
                },
            },
            ["operation"],
        ),
        handler=config_operation,
    ),
)
