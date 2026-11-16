"""One locale's strings: keys to text, or to plural forms of text.

A file is a flat JSON object, one per locale, named for it (`ru.json`):

```json
{
  "_meta": {"reviewed": false, "translator": "machine draft"},
  "room.waiting": "Waiting for {player}...",
  "hud.salvage": {"one": "{count} scrap", "other": "{count} scraps"}
}
```

Placeholders are `{name}`, optionally with a format spec (`{ratio:.0%}`).
Nothing else: a translation file is data from outside the code, and
`str.format` on arbitrary text could walk the attributes of whatever is
passed in (`{player.__class__}`), so anything but a plain name is refused
when the file is loaded.
"""

from __future__ import annotations

import json
import re
import string
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyguara import assets
from pyguara.i18n.plurals import PLURAL_FORMS, required_plural_forms

__all__ = ["META_KEY", "Entry", "LocaleTable", "UnsafePlaceholderError", "placeholders"]

META_KEY = "_meta"
"""The reserved key holding a file's metadata rather than a string."""

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")

Entry = str | dict[str, str]
"""A string, or plural forms keyed by CLDR category."""


class UnsafePlaceholderError(ValueError):
    """A placeholder that is not a plain `{name}`."""


def placeholders(text: str, *, key: str = "") -> set[str]:
    """Return the names of `text`'s placeholders, refusing anything else.

    Args:
        text: The template.
        key: The entry's key, for the error message.

    Returns:
        The placeholder names.

    Raises:
        UnsafePlaceholderError: On a positional, attribute, index,
            conversion or nested placeholder, or on malformed braces.
    """
    names: set[str] = set()
    try:
        parsed = list(string.Formatter().parse(text))
    except ValueError as error:
        raise UnsafePlaceholderError(f"{key!r}: {error} in {text!r}") from None
    for _, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if not _NAME.match(field_name):
            raise UnsafePlaceholderError(
                f"{key!r}: placeholder {{{field_name}}} must be a plain name, "
                f"like {{count}}, in {text!r}"
            )
        if conversion is not None or (format_spec and "{" in format_spec):
            raise UnsafePlaceholderError(
                f"{key!r}: placeholder {{{field_name}}} may not use a "
                f"conversion or a nested field, in {text!r}"
            )
        names.add(field_name)
    return names


@dataclass
class LocaleTable:
    """The strings of one locale, checked when loaded.

    Attributes:
        locale: The locale's tag, as its file is named.
        entries: Key to text, or key to plural forms.
        meta: The file's `_meta` object.
    """

    locale: str
    entries: dict[str, Entry]
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def reviewed(self) -> bool:
        """False until a native speaker has signed the translation off.

        A file without `_meta.reviewed` counts as reviewed: it is the
        developer's own text, as the source language's file is.
        """
        return bool(self.meta.get("reviewed", True))

    @classmethod
    def from_mapping(cls, locale: str, data: Mapping[str, Any]) -> LocaleTable:
        """Check and build a table from a parsed file.

        Raises:
            ValueError: If an entry is neither text nor plural forms, a
                plural entry lacks `other` or names an unknown form, the
                metadata is not an object, or the locale has no plural
                rules.
            UnsafePlaceholderError: On a placeholder that is not a name.
        """
        required_plural_forms(locale)  # refuses a language with no rules
        meta = data.get(META_KEY, {})
        if not isinstance(meta, dict):
            raise ValueError(f"{META_KEY!r} must be an object")
        entries: dict[str, Entry] = {}
        for key, value in data.items():
            if key == META_KEY:
                continue
            if isinstance(value, str):
                placeholders(value, key=key)
                entries[key] = value
            elif isinstance(value, dict):
                entries[key] = _plural_entry(key, value)
            else:
                raise ValueError(
                    f"{key!r} must be text or an object of plural forms, "
                    f"not {type(value).__name__}"
                )
        return cls(locale=locale, entries=entries, meta=dict(meta))

    @classmethod
    def from_file(cls, path: Path) -> LocaleTable:
        """Read `<locale>.json`, UTF-8, through `pyguara.assets`.

        Raises:
            ValueError: If it is not valid JSON or not a valid table; the
                message names the file.
        """
        try:
            data = json.loads(assets.read_text(path))
            if not isinstance(data, dict):
                raise ValueError("the top level must be an object")
            return cls.from_mapping(path.stem, data)
        except UnsafePlaceholderError as error:
            raise UnsafePlaceholderError(f"{path.name}: {error}") from error
        except ValueError as error:  # JSONDecodeError included
            raise ValueError(f"{path.name}: {error}") from error


def locale_files(directory: Path) -> list[Path]:
    """Return the `<locale>.json` files in a folder, packed or loose, sorted."""
    return [
        Path(name)
        for name in assets.files_under(directory, recursive=False)
        if name.endswith(".json")
    ]


def _plural_entry(key: str, forms: dict[str, Any]) -> dict[str, str]:
    unknown = sorted(set(forms) - set(PLURAL_FORMS))
    if unknown:
        raise ValueError(
            f"{key!r}: {', '.join(repr(u) for u in unknown)} is not a plural "
            f"form; the forms are {', '.join(PLURAL_FORMS)}"
        )
    if "other" not in forms:
        raise ValueError(f"{key!r}: a plural entry needs an 'other' form")
    checked: dict[str, str] = {}
    for form, text in forms.items():
        if not isinstance(text, str):
            raise ValueError(f"{key!r}[{form!r}] must be text")
        placeholders(text, key=key)
        checked[form] = text
    return checked
