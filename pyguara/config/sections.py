"""Registration of game-defined configuration sections.

`GameConfig` is a closed dataclass -- `display`, `audio`, `input`,
`physics`, `debug`, full stop. A game that wants its own tunables (enemy HP
curves, drop-rate tables, XP thresholds) has nowhere to put them, so every
shipped game grows a second hand-rolled JSON loader beside the engine's,
with its own parsing, its own coercion and no validation at all.

A registered section gets the engine's machinery instead: it is read from
and written to the same file, coerced back to its declared types on load,
overridable from the environment, reachable through `update_setting()`, and
checked by the validator when it chooses to be (see `ValidatableSection`).

Register before `ConfigManager.load()`: a section the registry has not heard
of is a key `from_dict()` cannot build anything from, and it is dropped with
a warning naming this function.
"""

from __future__ import annotations

from dataclasses import MISSING as _MISSING
from dataclasses import fields, is_dataclass
from typing import Any, Protocol, runtime_checkable

from pyguara.config.validation import ValidationIssue

ENGINE_SECTION_NAMES = frozenset({"display", "audio", "input", "physics", "debug"})
"""Section names `GameConfig` declares as real dataclass fields."""

RESERVED_SECTION_NAMES = ENGINE_SECTION_NAMES | {"version", "custom", "profiles"}
"""Names a game may not register: engine sections, plus the document keys
`GameConfig` uses for its own bookkeeping."""


@runtime_checkable
class ValidatableSection(Protocol):
    """A config section that knows what its own valid values are.

    Optional: a registered section without a `validate()` method is loaded,
    saved and overridden exactly the same way, merely unchecked. Implement
    it when a bad value has a consequence worth naming -- the engine's own
    sections do this through `ConfigValidator`, which cannot know anything
    about a game's fields.

    `ValidationIssue.section` is **overwritten** with the registered name, so
    a section need not repeat it and cannot get it wrong.
    """

    def validate(self) -> list[ValidationIssue]:
        """Report every problem with this section's current values.

        Returns:
            The issues found, empty when the section is sound. Severity
            decides the consequence: `ERROR` and `CRITICAL` make
            `update_setting()` and `push_profile()` refuse a change, while
            `WARNING` and `INFO` are logged as advice.
        """
        ...


class SectionRegistryError(Exception):
    """Raised when a section cannot be registered as asked."""


class SectionRegistry:
    """The game-defined section types a `ConfigManager` knows about.

    Keyed both ways on purpose. The *name* is what appears in the JSON file
    and in `update_setting("balance", ...)`; the *type* is what game code
    actually has in hand when it wants the values back, and
    `manager.section(BalanceConfig)` stays type-checked where
    `config.custom["balance"]` would be `Any`.
    """

    def __init__(self) -> None:
        """Start empty."""
        self._by_name: dict[str, type[Any]] = {}

    def register(self, name: str, section_type: type[Any]) -> None:
        """Record a dataclass as the section stored under `name`.

        Args:
            name: Key for this section in the config document.
            section_type: A dataclass whose fields are the settings. It must
                be constructible with no arguments, since that is what
                produces the defaults a missing file falls back to.

        Raises:
            SectionRegistryError: If the name is reserved or already taken by
                a different type, or `section_type` is not a no-argument
                dataclass.
        """
        if name in RESERVED_SECTION_NAMES:
            raise SectionRegistryError(
                f"Config section name {name!r} is reserved by the engine. "
                f"Reserved names: {', '.join(sorted(RESERVED_SECTION_NAMES))}."
            )
        if not name or not name.isidentifier():
            raise SectionRegistryError(
                f"Config section name {name!r} must be a valid identifier: it "
                f"becomes a key in the config file and in update_setting()."
            )
        if not isinstance(section_type, type) or not is_dataclass(section_type):
            raise SectionRegistryError(
                f"Config section {name!r} must be a dataclass type, got "
                f"{section_type!r}."
            )

        existing = self._by_name.get(name)
        if existing is not None and existing is not section_type:
            raise SectionRegistryError(
                f"Config section {name!r} is already registered as "
                f"{existing.__name__}; it cannot also be "
                f"{section_type.__name__}."
            )

        missing = [
            f.name
            for f in fields(section_type)
            if f.default is _MISSING and f.default_factory is _MISSING
        ]
        if missing:
            raise SectionRegistryError(
                f"Config section {section_type.__name__} must be constructible "
                f"with no arguments -- those values are the defaults used when "
                f"the file is missing a key. Give a default to: "
                f"{', '.join(missing)}."
            )

        self._by_name[name] = section_type

    def type_for(self, name: str) -> type[Any] | None:
        """Return the type registered under `name`, or None.

        Args:
            name: Section name.

        Returns:
            The dataclass, or None if nothing is registered under that name.
        """
        return self._by_name.get(name)

    def names(self) -> frozenset[str]:
        """Return every registered section name."""
        return frozenset(self._by_name)

    def build_defaults(self) -> dict[str, Any]:
        """Instantiate every registered section at its declared defaults.

        Returns:
            A fresh mapping of name to a new section instance. Fresh matters:
            two `ConfigManager`s sharing section instances would share edits.
        """
        return {name: section_type() for name, section_type in self._by_name.items()}
