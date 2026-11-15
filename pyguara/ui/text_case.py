"""Upper and lower case that are right in Turkish.

`str.upper()` follows Unicode's default mapping, which is wrong in Turkish
and Azerbaijani: there, `i` capitalises to `İ` (dotted) and `ı` (dotless)
to `I`, so `"iptal".upper()` must be `"İPTAL"`, not `"IPTAL"` -- a different
word to a Turkish reader. Everything else is `str.upper()` unchanged.

The language is set engine-wide, from the game's locale, and the UI's own
case changes (a design-system button's `uppercase`) go through here.
"""

from __future__ import annotations

__all__ = ["case_language", "lower", "set_case_language", "upper"]

_DOTTED_I_LANGUAGES = frozenset({"tr", "az"})
_language = "en"


def set_case_language(locale: str) -> None:
    """Set the language case changes follow, from a tag such as `"tr-TR"`."""
    global _language
    _language = locale.replace("_", "-").split("-", 1)[0].lower() or "en"


def case_language() -> str:
    """Return the language subtag case changes follow."""
    return _language


def upper(text: str) -> str:
    """Upper-case `text` as the current case language does."""
    if _language in _DOTTED_I_LANGUAGES:
        text = text.replace("i", "İ").replace("ı", "I")
    return text.upper()


def lower(text: str) -> str:
    """Lower-case `text` as the current case language does."""
    if _language in _DOTTED_I_LANGUAGES:
        text = text.replace("I", "ı").replace("İ", "i")
    return text.lower()
