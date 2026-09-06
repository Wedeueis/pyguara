"""Loading, saving and mutating the game configuration."""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Any

from pyguara.config.events import (
    OnConfigurationChanged,
    OnConfigurationLoaded,
    OnConfigurationSaved,
)
from pyguara.config.types import GameConfig, RenderingBackend
from pyguara.config.validation import (
    ConfigValidator,
    ValidationIssue,
    ValidationSeverity,
)
from pyguara.events.dispatcher import EventDispatcher
from pyguara.log.logger import EngineLogger
from pyguara.log.types import LogLevel

DEFAULT_CONFIG_PATH = Path("config/game_config.json")

# Severities that mean the engine cannot honour the value, as opposed to merely
# disliking it. update_setting() refuses a change that introduces one.
_BLOCKING_SEVERITIES = frozenset(
    {ValidationSeverity.ERROR, ValidationSeverity.CRITICAL}
)


class ConfigManager:
    """Owns the live `GameConfig` and its persistence.

    Reading is direct (`manager.config.display.fps_target`). Writing should go
    through `update_setting()`, which type-checks the value, rejects changes
    the validator considers unusable, and dispatches
    `OnConfigurationChanged`.
    """

    def __init__(
        self,
        event_dispatcher: EventDispatcher | None = None,
        logger: EngineLogger | None = None,
        file_path: str | Path | None = None,
    ) -> None:
        """Initialise the manager with default settings.

        Args:
            event_dispatcher: If given, config events are dispatched here.
            logger: Where load, save and validation problems are reported.
            file_path: Default path for `load()` and `save()`.
        """
        self._config = GameConfig()
        self._file_path = Path(file_path) if file_path else DEFAULT_CONFIG_PATH
        self._dispatcher = event_dispatcher
        self._logger = logger
        self._validator = ConfigValidator()

    @property
    def config(self) -> GameConfig:
        """The live configuration object."""
        return self._config

    @property
    def file_path(self) -> Path:
        """Path used by `load()` and `save()` when none is given."""
        return self._file_path

    def load(self, file_path: str | Path | None = None) -> bool:
        """Read configuration from a JSON file, then apply env overrides.

        A missing file is not an error: defaults are written to that path so
        the game has something to edit, and the call succeeds.

        Args:
            file_path: File to read. Defaults to `file_path` from the
                constructor.

        Returns:
            True if the configuration was established, False if the file
            existed but could not be read or parsed. Note this reports whether
            the file was *readable*, not whether its contents are sane -- call
            `validate()` for that.
        """
        target_path = Path(file_path) if file_path else self._file_path

        if not target_path.exists():
            self._log(
                ValidationSeverity.WARNING,
                f"Config file not found: {target_path}. Writing defaults.",
            )
            self.save(target_path)
            return True

        try:
            with open(target_path, encoding="utf-8") as handle:
                data = json.load(handle)
            self._config = GameConfig.from_dict(data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            if self._logger:
                self._logger.error(f"Failed to load config from {target_path}: {error}")
            return False

        self._apply_env_overrides()
        self._report(self.validate())

        if self._dispatcher:
            self._dispatcher.dispatch(
                OnConfigurationLoaded(config_file=str(target_path), success=True)
            )
        return True

    def save(self, file_path: str | Path | None = None) -> bool:
        """Write the current configuration to a JSON file.

        Args:
            file_path: File to write. Defaults to `file_path` from the
                constructor. Parent directories are created.

        Returns:
            True if the file was written.
        """
        target_path = Path(file_path) if file_path else self._file_path

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as handle:
                json.dump(self._config.to_dict(), handle, indent=4)
        except (OSError, TypeError) as error:
            if self._logger:
                self._logger.error(f"Failed to save config to {target_path}: {error}")
            return False

        if self._dispatcher:
            self._dispatcher.dispatch(
                OnConfigurationSaved(config_file=str(target_path), success=True)
            )
        return True

    def validate(self) -> list[ValidationIssue]:
        """Check the current configuration against the engine's limits.

        Returns:
            Every issue found, empty when the configuration is sound.
        """
        return self._validator.validate(self._config)

    def update_setting(self, section: str, setting: str, value: Any) -> bool:
        """Change one setting, if the new value is usable.

        The change is rejected, and nothing is mutated, when the section or
        setting is unknown, the value is the wrong type, or the validator
        considers the result unusable. Rejection is logged.

        Args:
            section: Config section name, e.g. `"display"`.
            setting: Field name within that section.
            value: The new value.

        Returns:
            True if the setting was changed.
        """
        section_obj = getattr(self._config, section, None)
        if section_obj is None or not hasattr(section_obj, setting):
            self._log(
                ValidationSeverity.WARNING,
                f"Unknown config setting '{section}.{setting}'.",
            )
            return False

        old_value = getattr(section_obj, setting)
        if not _is_assignable(old_value, value):
            self._log(
                ValidationSeverity.ERROR,
                f"Rejected '{section}.{setting}': expected "
                f"{type(old_value).__name__}, got {type(value).__name__} "
                f"({value!r}).",
            )
            return False

        setattr(section_obj, setting, value)

        blocking = [
            issue
            for issue in self._validator.validate_section(self._config, section)
            if issue.severity in _BLOCKING_SEVERITIES and issue.setting == setting
        ]
        if blocking:
            setattr(section_obj, setting, old_value)
            self._log(
                ValidationSeverity.ERROR,
                f"Rejected '{section}.{setting}' = {value!r}: {blocking[0].message}",
            )
            return False

        if self._dispatcher:
            self._dispatcher.dispatch(
                OnConfigurationChanged(
                    section=section,
                    setting=setting,
                    old_value=old_value,
                    new_value=value,
                )
            )
        return True

    def _apply_env_overrides(self) -> None:
        """Let `PYGUARA_*` environment variables override loaded settings.

        An unparseable value is reported and skipped rather than silently
        ignored, since a typo in a launch script is otherwise invisible.
        """
        self._override_enum(
            "PYGUARA_LOG_LEVEL", self._config.debug, "log_level", LogLevel
        )
        self._override_enum(
            "PYGUARA_BACKEND", self._config.display, "backend", RenderingBackend
        )
        self._override_int("PYGUARA_WINDOW_WIDTH", self._config.display, "screen_width")
        self._override_int(
            "PYGUARA_WINDOW_HEIGHT", self._config.display, "screen_height"
        )

    def _override_enum(
        self, variable: str, section: Any, setting: str, enum_type: type[Enum]
    ) -> None:
        """Apply an enum-valued environment override.

        Args:
            variable: Environment variable name.
            section: Config section object to write to.
            setting: Field name within that section.
            enum_type: Enum to resolve the value against, by name or by value.
        """
        raw = os.getenv(variable)
        if not raw:
            return
        try:
            setattr(section, setting, enum_type[raw.upper()])
            return
        except KeyError:
            pass
        try:
            setattr(section, setting, enum_type(raw.lower()))
        except ValueError:
            valid = ", ".join(member.name for member in enum_type)
            self._log(
                ValidationSeverity.WARNING,
                f"Ignoring {variable}={raw!r}: not a valid {enum_type.__name__}. "
                f"Expected one of {valid}.",
            )

    def _override_int(self, variable: str, section: Any, setting: str) -> None:
        """Apply an integer-valued environment override.

        Args:
            variable: Environment variable name.
            section: Config section object to write to.
            setting: Field name within that section.
        """
        raw = os.getenv(variable)
        if not raw:
            return
        try:
            setattr(section, setting, int(raw))
        except ValueError:
            self._log(
                ValidationSeverity.WARNING,
                f"Ignoring {variable}={raw!r}: not an integer.",
            )

    def _report(self, issues: list[ValidationIssue]) -> None:
        """Log validation issues, each at its own severity.

        Args:
            issues: Issues to report.
        """
        for issue in issues:
            detail = f" {issue.suggestion}" if issue.suggestion else ""
            self._log(
                issue.severity,
                f"Config {issue.section}.{issue.setting}: {issue.message}{detail}",
            )

    def _log(self, severity: ValidationSeverity, message: str) -> None:
        """Emit a message at the level matching a validation severity.

        Everything used to be logged as a warning, which hid ERROR and
        CRITICAL problems among the merely suboptimal ones.

        Args:
            severity: Severity to map to a log level.
            message: Text to log.
        """
        if self._logger is None:
            return
        if severity is ValidationSeverity.CRITICAL:
            self._logger.critical(message)
        elif severity is ValidationSeverity.ERROR:
            self._logger.error(message)
        elif severity is ValidationSeverity.WARNING:
            self._logger.warning(message)
        else:
            self._logger.info(message)


def _is_assignable(old_value: Any, new_value: Any) -> bool:
    """Report whether a new value may replace an existing setting.

    Stricter than `isinstance`, which treats `bool` as an `int` and so let
    `fps_target = True` through, and looser about ints where a float is
    declared, which is the one widening JSON and Python both expect.

    Args:
        old_value: The current value, whose type defines what is acceptable.
        new_value: The candidate value.

    Returns:
        True if the assignment is type-compatible.
    """
    if old_value is None:
        return True
    if isinstance(old_value, bool):
        return isinstance(new_value, bool)
    if isinstance(old_value, int):
        return isinstance(new_value, int) and not isinstance(new_value, bool)
    if isinstance(old_value, float):
        return isinstance(new_value, (int, float)) and not isinstance(new_value, bool)
    return isinstance(new_value, type(old_value))
