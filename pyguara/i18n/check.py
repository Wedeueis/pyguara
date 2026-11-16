"""Hold every locale's strings against the source's.

What `pyguara i18n check` runs. It reports, per locale:

- a key the source has and the locale lacks (it would show English);
- a key the locale has and the source lacks (a typo, or a removed string);
- placeholders that differ from the source's, form by form;
- plural forms the locale's language needs and the entry lacks;
- a file that will not load, or names a language with no plural rules;

and, as a warning, a file not yet reviewed by a native speaker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pyguara.i18n.plurals import required_plural_forms
from pyguara.i18n.table import Entry, LocaleTable, locale_files, placeholders

__all__ = ["CheckReport", "check_directory"]


@dataclass
class CheckReport:
    """What a check found.

    Attributes:
        locales: The locales that loaded, source included.
        errors: Problems a release must not ship with.
        warnings: Things to know: an unreviewed translation.
    """

    locales: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_directory(directory: str | Path, *, source: str = "en") -> CheckReport:
    """Check every `<locale>.json` in `directory` against `source`'s.

    Args:
        directory: The folder of locale files.
        source: The locale the game is written in.

    Returns:
        The report. Loading problems are errors in it, not exceptions.
    """
    directory = Path(directory)
    report = CheckReport()
    tables: dict[str, LocaleTable] = {}
    for path in locale_files(directory):
        try:
            tables[path.stem] = LocaleTable.from_file(path)
        except (OSError, ValueError) as error:
            message = str(error)
            if not message.startswith(path.name):
                message = f"{path.name}: {message}"
            report.errors.append(message)
    report.locales = sorted(tables)

    if source not in tables:
        report.errors.append(f"{source}.json: the source locale is missing")
        return report

    reference = tables[source].entries
    for locale, table in sorted(tables.items()):
        if locale == source:
            continue
        if not table.reviewed:
            report.warnings.append(f"{locale}: not reviewed by a native speaker")
        for key in reference:
            if key not in table.entries:
                report.errors.append(f"{locale}: {key!r} is missing")
                continue
            report.errors.extend(
                _compare(locale, key, reference[key], table.entries[key])
            )
        for key in table.entries:
            if key not in reference:
                report.errors.append(f"{locale}: {key!r} is not in the source locale")
    return report


def _names(entry: Entry) -> set[str]:
    texts = entry.values() if isinstance(entry, dict) else [entry]
    found: set[str] = set()
    for text in texts:
        found |= placeholders(text)
    return found


def _compare(locale: str, key: str, source: Entry, entry: Entry) -> list[str]:
    errors: list[str] = []
    expected = _names(source)
    texts = entry.items() if isinstance(entry, dict) else [("", entry)]
    for form, text in texts:
        got = placeholders(text)
        if got != expected:
            where = f"[{form!r}]" if form else ""
            errors.append(
                f"{locale}: {key!r}{where} has placeholders "
                f"{_braced(got)}, the source has {_braced(expected)}"
            )
    needed = required_plural_forms(locale)
    if isinstance(source, dict) and not isinstance(entry, dict):
        if needed != {"other"}:
            errors.append(
                f"{locale}: {key!r} is plural in the source and needs the "
                f"plural forms {', '.join(sorted(needed))}"
            )
    elif isinstance(entry, dict):
        missing = needed - set(entry)
        if missing:
            errors.append(
                f"{locale}: {key!r} lacks the plural forms {', '.join(sorted(missing))}"
            )
    return errors


def _braced(names: set[str]) -> str:
    return ", ".join(f"{{{name}}}" for name in sorted(names)) or "none"
