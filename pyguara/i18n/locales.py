"""Choosing a locale: from what the player's system or Steam asks for."""

from __future__ import annotations

import locale as _locale
import os
from collections.abc import Sequence

from pyguara.i18n.plurals import language_of

__all__ = ["best_locale", "locale_from_steam", "system_locale"]

# Steam's API language names (ISteamApps::GetCurrentGameLanguage) -> BCP 47.
_STEAM = {
    "arabic": "ar",
    "brazilian": "pt-BR",
    "bulgarian": "bg",
    "czech": "cs",
    "danish": "da",
    "dutch": "nl",
    "english": "en",
    "finnish": "fi",
    "french": "fr",
    "german": "de",
    "greek": "el",
    "hungarian": "hu",
    "indonesian": "id",
    "italian": "it",
    "japanese": "ja",
    "koreana": "ko",
    "latam": "es",
    "norwegian": "no",
    "polish": "pl",
    "portuguese": "pt",
    "romanian": "ro",
    "russian": "ru",
    "schinese": "zh-Hans",
    "spanish": "es",
    "swedish": "sv",
    "tchinese": "zh-Hant",
    "thai": "th",
    "turkish": "tr",
    "ukrainian": "uk",
    "vietnamese": "vi",
}


def locale_from_steam(language: str) -> str | None:
    """Translate a Steam language name (`"schinese"`) into a locale tag.

    Returns:
        The BCP 47 tag, or None for a name Steam does not use.
    """
    return _STEAM.get(language.strip().lower())


def system_locale() -> str:
    """Return the operating system's locale, as `"de-DE"`, or `""`.

    Reads `LC_ALL`, `LC_MESSAGES` and `LANG` first, as POSIX does, then
    asks Python, which on Windows reads the user's display language.
    """
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(variable, "")
        if value and value not in ("C", "POSIX"):
            return _clean(value)
    found = _locale.getlocale()[0] or ""
    return _clean(found)


def _clean(tag: str) -> str:
    # "de_DE.UTF-8@euro" -> "de-DE"
    return tag.split(".", 1)[0].split("@", 1)[0].replace("_", "-")


def _script(tag: str) -> str | None:
    # Han script from a script subtag, or from the region that implies it.
    parts = [part.lower() for part in tag.split("-")[1:]]
    if "hans" in parts or any(part in ("cn", "sg", "my") for part in parts):
        return "hans"
    if "hant" in parts or any(part in ("tw", "hk", "mo") for part in parts):
        return "hant"
    return None


def best_locale(wanted: str, available: Sequence[str], *, source: str) -> str:
    """Pick the available locale closest to the one asked for.

    An exact match first (ignoring case and `_` versus `-`), then, for
    Chinese, the same script, then the same language in any region --
    `pt-PT` gets `pt-BR` rather than English -- and otherwise the source.

    Args:
        wanted: A locale as the system or a setting spells it, such as
            `"de_DE.UTF-8"` or `"zh-CN"`. Empty asks for the source.
        available: The locales there are tables for.
        source: The locale the game is written in; the last resort.

    Returns:
        One of `available`, or `source`.
    """
    tag = _clean(wanted)
    if not tag:
        return source
    by_lower = {code.lower(): code for code in available}
    if tag.lower() in by_lower:
        return by_lower[tag.lower()]

    language = language_of(tag)
    same_language = [code for code in available if language_of(code) == language]
    if language == "zh":
        script = _script(tag)
        for code in same_language:
            if script is not None and _script(code) == script:
                return code
    if same_language:
        return sorted(same_language)[0]
    return source
