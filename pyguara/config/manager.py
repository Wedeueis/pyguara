"""Loading, saving and mutating the game configuration."""

from __future__ import annotations

import json
import os
from dataclasses import fields
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar, get_type_hints

from pyguara.config.events import (
    OnConfigurationChanged,
    OnConfigurationLoaded,
    OnConfigurationSaved,
)
from pyguara.config.sections import SectionRegistry
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

ENV_PREFIX = "PYGUARA_"

_TRUE_WORDS = frozenset({"1", "true", "yes", "on"})
_FALSE_WORDS = frozenset({"0", "false", "no", "off"})


class _Unparseable:
    """Sentinel: an environment value that could not be used.

    Distinct from None, which is a legal value for an optional setting such
    as `debug.rng_seed`.
    """


_UNPARSEABLE = _Unparseable()

SectionT = TypeVar("SectionT")

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
        self._registry = SectionRegistry()
        self._loaded = False

    @property
    def config(self) -> GameConfig:
        """The live configuration object."""
        return self._config

    @property
    def file_path(self) -> Path:
        """Path used by `load()` and `save()` when none is given."""
        return self._file_path

    def register_section(self, name: str, section_type: type[Any]) -> None:
        """Add a game-defined section to the config, before loading.

        The section then gets everything the engine's own sections get: it
        is read from and written to the same file under `name`, coerced back
        to its declared types, overridable from `PYGUARA_<NAME>_<FIELD>`,
        writable through `update_setting()`, layerable by a profile, and
        checked by `validate()` if it implements
        `sections.ValidatableSection`.

        Registering installs the section at its declared defaults
        immediately, so reads work before `load()` -- and so a game whose
        config file does not exist yet still has usable values.

        Args:
            name: Key for this section in the config document.
            section_type: A no-argument-constructible dataclass.

        Raises:
            RuntimeError: If `load()` has already run. `from_dict()` can only
                build a section the registry knows about, so a late
                registration would silently discard whatever the file said
                and hand the game its defaults instead.
            SectionRegistryError: If the name is reserved or taken, or the
                type is unsuitable.

        Example:
            ```python
            @dataclass
            class BalanceConfig:
                enemy_hp_scale: float = 1.0
                drop_rate: float = 0.25

            manager.register_section("balance", BalanceConfig)
            manager.load()
            manager.section(BalanceConfig).drop_rate
            ```
        """
        if self._loaded:
            raise RuntimeError(
                f"Config section {name!r} was registered after load(); the "
                f"file's values for it have already been discarded. Register "
                f"every section before loading -- see "
                f"pyguara.application.bootstrap's `configure` hook."
            )
        self._registry.register(name, section_type)
        self._config.custom.setdefault(name, section_type())

    def section(self, section_type: type[SectionT]) -> SectionT:
        """Return a section by its type, type-checked.

        Args:
            section_type: The section's dataclass, engine or game-defined.

        Returns:
            The live instance.

        Raises:
            KeyError: If no section of that type is present.
        """
        return self._config.section(section_type)

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
            self._loaded = True
            self.save(target_path)
            # After the write, not before: the file is meant to hold the
            # engine's defaults for the game to edit, while an environment
            # override is a property of *this* launch. Applying them first
            # baked `PYGUARA_BACKEND` permanently into a first-run config.
            self._apply_env_overrides()
            return True

        try:
            with open(target_path, encoding="utf-8") as handle:
                data = json.load(handle)
            self._config = GameConfig.from_dict(data, self._registry)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            if self._logger:
                self._logger.error(f"Failed to load config from {target_path}: {error}")
            return False

        self._loaded = True
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
        section_obj = self._config.get_section(section)
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

        Two layers. The four short aliases are applied first because they
        are what every existing launch script and CI job already sets, and
        their names do not follow the general rule
        (`PYGUARA_WINDOW_WIDTH` means `display.screen_width`). Then the
        generic `PYGUARA_<SECTION>_<FIELD>` pass, which wins on the overlap:
        it names the exact field, so it is the more deliberate of the two.

        The generic form is what makes a game-defined section reachable from
        the environment at all -- without it, `register_section()` would
        hand a game the file and the validator but not the override that
        makes a headless CI run or a packaged build configurable.

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
        self._apply_generic_env_overrides()

    def _apply_generic_env_overrides(self) -> None:
        """Apply every `PYGUARA_<SECTION>_<FIELD>` variable that matches.

        Matching is driven from the section names, not by splitting the
        variable: field names contain underscores (`fps_target`), so
        `PYGUARA_DISPLAY_FPS_TARGET` has no unambiguous split of its own.
        Testing each known section as a prefix instead makes the remainder
        the field name exactly, which also means a variable whose section
        matches but whose field does not is a *typo* worth reporting, while
        one naming no section at all is left alone -- it belongs to
        something else (`PYGUARA_BACKEND`, or another tool entirely).
        """
        environment = {name: value for name, value in os.environ.items() if value}
        for section_name, section_obj in self._config.sections():
            prefix = f"{ENV_PREFIX}{section_name.upper()}_"
            known = {f.name for f in fields(section_obj)}
            hints = get_type_hints(type(section_obj))
            for variable, raw in environment.items():
                if not variable.startswith(prefix):
                    continue
                setting = variable[len(prefix) :].lower()
                if setting not in known:
                    self._log(
                        ValidationSeverity.WARNING,
                        f"Ignoring {variable}: '{section_name}' has no setting "
                        f"{setting!r}. Known settings: "
                        f"{', '.join(sorted(known))}.",
                    )
                    continue
                parsed = self._parse_env_value(hints[setting], raw, variable)
                if parsed is not _UNPARSEABLE:
                    setattr(section_obj, setting, parsed)

    def _parse_env_value(self, target_type: Any, raw: str, variable: str) -> Any:
        """Turn an environment string into a value of the declared type.

        Only the types an environment variable can honestly express are
        supported. A `Color` or a nested dataclass is refused rather than
        half-parsed from some invented syntax: the config file is the right
        place for those, and a format no one documented would be worse than
        the refusal.

        Args:
            target_type: The field's declared type.
            raw: The raw environment value.
            variable: Variable name, for messages.

        Returns:
            The parsed value, or the `_UNPARSEABLE` sentinel when the value
            or the type cannot be handled -- which is reported, never
            silent.
        """
        if isinstance(target_type, type) and issubclass(target_type, Enum):
            try:
                return target_type[raw.upper()]
            except KeyError:
                pass
            for member in target_type:
                if str(member.value).lower() == raw.lower():
                    return member
            valid = ", ".join(member.name for member in target_type)
            self._log(
                ValidationSeverity.WARNING,
                f"Ignoring {variable}={raw!r}: not a valid "
                f"{target_type.__name__}. Expected one of {valid}.",
            )
            return _UNPARSEABLE

        # bool before int: bool is an int subclass, and int("true") raises.
        if target_type is bool:
            lowered = raw.strip().lower()
            if lowered in _TRUE_WORDS:
                return True
            if lowered in _FALSE_WORDS:
                return False
            self._log(
                ValidationSeverity.WARNING,
                f"Ignoring {variable}={raw!r}: not a boolean. Expected one of "
                f"{', '.join(sorted(_TRUE_WORDS | _FALSE_WORDS))}.",
            )
            return _UNPARSEABLE

        if target_type in (int, float, str):
            try:
                return target_type(raw)
            except ValueError:
                self._log(
                    ValidationSeverity.WARNING,
                    f"Ignoring {variable}={raw!r}: not a {target_type.__name__}.",
                )
                return _UNPARSEABLE

        self._log(
            ValidationSeverity.WARNING,
            f"Ignoring {variable}: a "
            f"{getattr(target_type, '__name__', target_type)} cannot be set "
            f"from the environment. Set it in the config file instead.",
        )
        return _UNPARSEABLE

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
