"""Looking a key up in the current locale, with English behind it."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from pyguara import assets
from pyguara.i18n.plurals import plural_category
from pyguara.i18n.table import LocaleTable, locale_files
from pyguara.log import get_logger

__all__ = ["MissingStringError", "Translator"]

logger = get_logger(__name__)


class MissingStringError(KeyError):
    """A key the source locale does not have.

    A bug in the game, not a gap in a translation.
    """

    def __str__(self) -> str:
        """Return the message as written; KeyError would repr it."""
        return str(self.args[0])


class Translator:
    """Turns a key and its values into text in the current locale.

    ```python
    tr = Translator.from_directory("locales", locale="ru")
    tr("room.waiting", player="Ana")
    tr("hud.salvage", count=3)       # picks Russian's "few" form
    ```

    A key a translation lacks is read from the source locale, and logged
    once per key and locale. A key the source lacks raises
    `MissingStringError`: that is code asking for text nobody wrote.
    """

    def __init__(
        self,
        tables: Mapping[str, LocaleTable],
        *,
        locale: str,
        source: str = "en",
    ) -> None:
        """Build from loaded tables.

        Args:
            tables: Locale tag to table. Must include `source`.
            locale: The locale to start in.
            source: The locale the game is written in.

        Raises:
            ValueError: If `source` or `locale` has no table.
        """
        if source not in tables:
            raise ValueError(f"no table for the source locale {source!r}")
        self._tables = dict(tables)
        self._source = source
        self._locale = source
        self._listeners: list[Callable[[str], None]] = []
        self._warned: set[tuple[str, str]] = set()
        self.locale = locale

    @classmethod
    def from_directory(
        cls, directory: str | Path, *, locale: str, source: str = "en"
    ) -> Translator:
        """Load every `<locale>.json` in a directory.

        Read through `pyguara.assets`, so the directory may be in a pack.

        Raises:
            FileNotFoundError: If the source locale's file is missing.
            ValueError: If a file is not a valid table; the message names it.
        """
        directory = Path(directory)
        source_file = directory / f"{source}.json"
        if not assets.is_file(source_file):
            raise FileNotFoundError(
                f"{source_file} is missing: the source locale's strings are "
                "what every other locale falls back to"
            )
        tables = {
            path.stem: LocaleTable.from_file(path) for path in locale_files(directory)
        }
        return cls(tables, locale=locale, source=source)

    @property
    def tables(self) -> dict[str, LocaleTable]:
        """Every loaded table, by locale."""
        return dict(self._tables)

    @property
    def available(self) -> tuple[str, ...]:
        """The locales there are tables for, sorted."""
        return tuple(sorted(self._tables))

    @property
    def source(self) -> str:
        """The locale the game is written in."""
        return self._source

    @property
    def locale(self) -> str:
        """The locale text is looked up in. Setting it notifies listeners."""
        return self._locale

    @locale.setter
    def locale(self, value: str) -> None:
        if value not in self._tables:
            raise ValueError(
                f"no strings for locale {value!r}; available: "
                f"{', '.join(self.available)}"
            )
        if value == self._locale:
            return
        self._locale = value
        for listener in list(self._listeners):
            listener(value)

    def on_change(self, listener: Callable[[str], None]) -> None:
        """Call `listener(locale)` whenever the locale changes.

        A screen built from keys rebuilds its text here.
        """
        self._listeners.append(listener)

    def has(self, key: str) -> bool:
        """Whether the source locale has `key`."""
        return key in self._tables[self._source].entries

    def __call__(self, key: str, /, **values: Any) -> str:
        """Return `key`'s text in the current locale, with `values` filled in.

        Args:
            key: The string's key.
            **values: The placeholders' values. A plural entry needs
                `count`, an int, which also picks the form.

        Returns:
            The text.

        Raises:
            MissingStringError: If the source locale has no such key.
            TypeError: If a plural entry is given no integer `count`.
            KeyError: If a placeholder has no value.
        """
        table = self._tables[self._locale]
        entry = table.entries.get(key)
        locale = self._locale
        if entry is None:
            entry = self._tables[self._source].entries.get(key)
            if entry is None:
                raise MissingStringError(
                    f"no string {key!r} in the source locale {self._source!r}"
                )
            locale = self._source
            if (self._locale, key) not in self._warned:
                self._warned.add((self._locale, key))
                logger.warning(
                    f"{key!r} has no {self._locale!r} translation; "
                    f"showing the {self._source!r} text"
                )
        if isinstance(entry, dict):
            if "count" not in values:
                raise TypeError(f"{key!r} has plural forms, so it needs count=")
            form = plural_category(locale, values["count"])
            entry = entry.get(form, entry["other"])
        return entry.format_map(values)
