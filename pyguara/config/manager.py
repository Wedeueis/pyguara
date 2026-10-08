"""Loading, saving and mutating the game configuration."""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Mapping
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

        # The un-layered truth: section -> setting -> value, as established
        # by the defaults, then the file, then the environment. Every
        # profile is applied *over* this, and peeling one off re-applies it,
        # so the base has to be recorded rather than recovered by inverting
        # whatever the layers did.
        self._base: dict[str, dict[str, Any]] = {}
        self._stack: list[tuple[str, dict[str, dict[str, Any]]]] = []
        self._snapshot_base()

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
                f"every section before loading -- under bootstrap, through "
                f"create_application(register_sections=...)."
            )
        self._registry.register(name, section_type)
        self._config.custom.setdefault(name, section_type())
        self._base.setdefault(name, _values_of(self._config.custom[name]))

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
            self._stack.clear()
            self.save(target_path)
            # After the write, not before: the file is meant to hold the
            # engine's defaults for the game to edit, while an environment
            # override is a property of *this* launch. Applying them first
            # baked `PYGUARA_BACKEND` permanently into a first-run config.
            self._apply_env_overrides()
            self._snapshot_base()
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
        # A load re-establishes the base truth, so whatever was layered over
        # the previous one is gone: keeping a stack whose values referred to
        # a config that no longer exists would re-apply them over unrelated
        # settings on the next pop.
        self._stack.clear()
        self._apply_env_overrides()
        self._snapshot_base()
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

        pinned_by = self._pinned_by(section, setting)
        if pinned_by is not None:
            self._log(
                ValidationSeverity.WARNING,
                f"Rejected '{section}.{setting}': the active profile "
                f"{pinned_by!r} sets it. Pop the profile first, or accept that "
                f"it owns this setting -- a run modifier the options menu can "
                f"switch off is not a modifier.",
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
        self._base.setdefault(section, {})[setting] = value

        blocking = [
            issue
            for issue in self._validator.validate_section(self._config, section)
            if issue.severity in _BLOCKING_SEVERITIES and issue.setting == setting
        ]
        if blocking:
            setattr(section_obj, setting, old_value)
            self._base[section][setting] = old_value
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

    # -- Layered profiles --

    @property
    def available_profiles(self) -> tuple[str, ...]:
        """Names that `push_profile()` can resolve without being given a layer.

        Profiles authored in the config file, plus any added with
        `define_profile()`.
        """
        return tuple(self._config.profiles)

    @property
    def active_profiles(self) -> tuple[str, ...]:
        """Names of the layers currently applied, in the order they were pushed.

        Later layers win where two set the same setting.
        """
        return tuple(name for name, _ in self._stack)

    def define_profile(self, name: str, overrides: dict[str, dict[str, Any]]) -> None:
        """Register a named override layer in code.

        The same thing a `"profiles"` block in the config file declares, for
        a layer a game computes rather than authors -- a daily modifier set,
        or an accessibility profile derived from a platform query.

        Defining does not apply anything: nothing changes until
        `push_profile()`.

        Args:
            name: Profile name, for `push_profile()`.
            overrides: `section -> setting -> value`, naming only real
                settings.

        Raises:
            ValueError: If any section, setting or value is wrong. A
                definition written in code is a programmer error, unlike one
                read from a file, which is reported and refused at push
                time.
        """
        problems = self._structural_problems(overrides)
        if problems:
            raise ValueError(
                f"Profile {name!r} cannot be defined: " + "; ".join(problems)
            )
        self._config.profiles[name] = overrides

    def push_profile(
        self, name: str, overrides: dict[str, dict[str, Any]] | None = None
    ) -> bool:
        """Layer a named set of overrides over the current configuration.

        A profile is a batch of `update_setting()` calls applied atomically
        and reversibly: the same type checks, the same validator veto, and
        `pop_profile()` restores exactly what was underneath -- which plain
        assignment cannot, since the previous value is gone the moment it is
        overwritten.

        That reversibility is the whole point. A difficulty preset, an
        accessibility profile and a roguelike's run modifiers are all the
        same shape: a set of values that applies for a while and then stops.

        Args:
            name: Profile name. Must not already be active.
            overrides: `section -> setting -> value`. Omit to resolve the
                name from the config file's `"profiles"` block or a previous
                `define_profile()`.

        Returns:
            True if the layer was applied. False leaves the configuration
            exactly as it was -- the push is all-or-nothing, since a
            difficulty preset that applied two of its three settings would
            be worse than one that applied none.
        """
        if name in self.active_profiles:
            self._log(
                ValidationSeverity.WARNING,
                f"Profile {name!r} is already active; nothing was changed.",
            )
            return False

        layer = overrides if overrides is not None else self._config.profiles.get(name)
        if layer is None:
            known = ", ".join(self.available_profiles) or "none"
            self._log(
                ValidationSeverity.ERROR,
                f"No profile named {name!r}. Defined profiles: {known}. Pass "
                f"the overrides directly, or declare it in the config file's "
                f"'profiles' block.",
            )
            return False

        problems = self._structural_problems(layer)
        if problems:
            self._log(
                ValidationSeverity.ERROR,
                f"Profile {name!r} was not applied: " + "; ".join(problems),
            )
            return False

        # Blocking issues the configuration already had are not this
        # profile's fault, and refusing every push because the loaded file
        # is unsound would be a cascade with no way out.
        pre_existing = self._blocking_keys()
        before = self._current_values()
        candidate = [*self._stack, (name, layer)]
        self._apply(candidate)

        introduced = [
            issue
            for issue in self.validate()
            if issue.severity in _BLOCKING_SEVERITIES
            and (issue.section, issue.setting) not in pre_existing
        ]
        if introduced:
            self._apply(self._stack)
            self._log(
                ValidationSeverity.ERROR,
                f"Profile {name!r} was not applied: "
                f"{introduced[0].section}.{introduced[0].setting} -- "
                f"{introduced[0].message}",
            )
            return False

        self._stack = candidate
        self._dispatch_diff(before, name)
        return True

    def pop_profile(self, name: str | None = None) -> bool:
        """Peel one layer back off, restoring what was underneath it.

        Removing a layer from the middle of the stack is legal and
        deliberate: run modifiers are independent, so dropping one must not
        require dropping the ones pushed after it.

        Args:
            name: Profile to remove. Omit to remove the most recent, which is
                a no-op on an empty stack. A *named* profile that is not
                active is reported either way: asking for one by name says
                the caller believed it was applied.

        Returns:
            True if a layer was removed.
        """
        if name is None:
            if not self._stack:
                return False
            index = len(self._stack) - 1
        else:
            index = next(
                (i for i, (pushed, _) in enumerate(self._stack) if pushed == name), -1
            )
            if index < 0:
                self._log(
                    ValidationSeverity.WARNING,
                    f"Profile {name!r} is not active; active profiles: "
                    f"{', '.join(self.active_profiles) or 'none'}.",
                )
                return False

        removed = self._stack[index][0]
        before = self._current_values()
        self._stack.pop(index)
        self._apply(self._stack)
        self._dispatch_diff(before, removed)
        return True

    def clear_profiles(self) -> bool:
        """Drop every active layer, leaving the base configuration.

        Returns:
            True if anything was active.
        """
        if not self._stack:
            return False
        before = self._current_values()
        self._stack.clear()
        self._apply(self._stack)
        self._dispatch_diff(before, None)
        return True

    def _structural_problems(self, layer: Mapping[str, Any]) -> list[str]:
        """Check a layer names real settings with usable values.

        Typed loosely on purpose: a profile read from the config file is
        unvalidated JSON, so `overrides` may be any shape at all, and this
        is the one place that finds out.

        Rejecting rather than skipping the bad keys is deliberate: a
        difficulty profile that silently fails to apply one of its three
        settings is a bug someone chases for an hour, and a profile is small
        and deliberate enough that a typo in it is always a mistake.

        Args:
            layer: `section -> setting -> value`.

        Returns:
            One message per problem, empty when the layer is sound.
        """
        problems: list[str] = []
        for section_name, overrides in layer.items():
            section_obj = self._config.get_section(section_name)
            if section_obj is None:
                problems.append(
                    f"no section {section_name!r} (known: "
                    f"{', '.join(self._config.section_names())})"
                )
                continue
            if not isinstance(overrides, dict):
                problems.append(
                    f"'{section_name}' should map settings to values, got "
                    f"{type(overrides).__name__}"
                )
                continue
            for setting, value in overrides.items():
                if not hasattr(section_obj, setting):
                    problems.append(f"no setting '{section_name}.{setting}'")
                    continue
                if not _is_assignable(getattr(section_obj, setting), value):
                    problems.append(
                        f"'{section_name}.{setting}' expects "
                        f"{type(getattr(section_obj, setting)).__name__}, got "
                        f"{type(value).__name__} ({value!r})"
                    )
        return problems

    def _pinned_by(self, section: str, setting: str) -> str | None:
        """Return the name of the active profile that sets a field, if any.

        Args:
            section: Section name.
            setting: Field name.

        Returns:
            The topmost profile setting that field, or None.
        """
        for name, layer in reversed(self._stack):
            if setting in layer.get(section, {}):
                return name
        return None

    def _blocking_keys(self) -> set[tuple[str, str]]:
        """Return `(section, setting)` for every current blocking issue."""
        return {
            (issue.section, issue.setting)
            for issue in self.validate()
            if issue.severity in _BLOCKING_SEVERITIES
        }

    def _snapshot_base(self) -> None:
        """Record the current values as the un-layered base.

        Called where the base genuinely changes: construction, a load, and a
        section registration. Not after a push -- that would absorb the
        layer into the base and make it unpoppable.
        """
        self._base = {
            name: _values_of(section) for name, section in self._config.sections()
        }

    def _current_values(self) -> dict[str, dict[str, Any]]:
        """Return every section's live values, for diffing against later."""
        return {
            name: {f.name: getattr(section, f.name) for f in fields(section)}
            for name, section in self._config.sections()
        }

    def _apply(self, layers: list[tuple[str, dict[str, dict[str, Any]]]]) -> None:
        """Rebuild the live configuration as base, then each layer in order.

        Rebuilt rather than undone: a pop would otherwise have to know what
        each layer overwrote, and two layers touching one setting make that
        bookkeeping ambiguous.

        The `GameConfig` and its section instances are mutated in place, so
        every holder of `manager.config` -- and the engine caches it widely
        -- sees the result without re-resolving anything.

        Args:
            layers: The stack to apply over the base.
        """
        for section_name, values in self._base.items():
            section_obj = self._config.get_section(section_name)
            if section_obj is None:
                continue
            for setting, value in values.items():
                setattr(section_obj, setting, copy.deepcopy(value))

        for _, layer in layers:
            for section_name, overrides in layer.items():
                section_obj = self._config.get_section(section_name)
                if section_obj is None:
                    continue
                for setting, value in overrides.items():
                    setattr(section_obj, setting, copy.deepcopy(value))

    def _dispatch_diff(
        self, before: dict[str, dict[str, Any]], profile: str | None
    ) -> None:
        """Publish one `OnConfigurationChanged` per setting that moved.

        Per setting, not one event per profile: a settings screen or an
        eventual live-re-application pass reacts to fields, and cannot be
        asked to diff the config itself to find out which ones.

        Args:
            before: Values captured before the layers were re-applied.
            profile: Profile responsible, carried on the event so a listener
                can tell a layer from a user edit. None for a clear.
        """
        if self._dispatcher is None:
            return
        after = self._current_values()
        for section_name, values in after.items():
            previous = before.get(section_name, {})
            for setting, value in values.items():
                if setting in previous and previous[setting] != value:
                    self._dispatcher.dispatch(
                        OnConfigurationChanged(
                            section=section_name,
                            setting=setting,
                            old_value=previous[setting],
                            new_value=value,
                            profile=profile,
                            source=self,
                        )
                    )

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


def _values_of(section: Any) -> dict[str, Any]:
    """Snapshot one section's fields, deep-copied.

    Deep rather than shallow because a mutable field value -- a `Color` --
    would otherwise be shared between the base snapshot and the live
    section, so mutating it in place would silently rewrite the base a pop
    is supposed to restore.

    Args:
        section: A config section instance.

    Returns:
        Field name to value.
    """
    return {f.name: copy.deepcopy(getattr(section, f.name)) for f in fields(section)}


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
