"""Which plural form a count takes, per language: CLDR's rules, for integers.

A game counts things -- scrap, players, seconds -- so only integer counts
are handled. Each rule is transcribed from the Unicode CLDR plural rules
(https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html)
for the languages the engine has been asked to support; a language with no
rule here is refused rather than given English's, which would be a plausible
wrong answer.
"""

from __future__ import annotations

from collections.abc import Callable

__all__ = [
    "PLURAL_FORMS",
    "language_of",
    "plural_category",
    "required_plural_forms",
    "supported_languages",
]

PLURAL_FORMS = ("zero", "one", "two", "few", "many", "other")
"""Every CLDR plural category, in CLDR's order."""


def _one_other(n: int) -> str:
    return "one" if n == 1 else "other"


def _millions(n: int) -> bool:
    # CLDR's `e = 0 and i != 0 and i % 1000000 = 0 and v = 0`: "1 millón de".
    return n != 0 and n % 1_000_000 == 0


def _spanish(n: int) -> str:
    if n == 1:
        return "one"
    return "many" if _millions(n) else "other"


def _zero_one_singular(n: int) -> str:
    # French and Portuguese: 0 and 1 are both singular ("0 point").
    if n in (0, 1):
        return "one"
    return "many" if _millions(n) else "other"


def _russian(n: int) -> str:
    last, last_two = n % 10, n % 100
    if last == 1 and last_two != 11:
        return "one"
    if 2 <= last <= 4 and not 12 <= last_two <= 14:
        return "few"
    return "many"


def _no_plural(n: int) -> str:
    return "other"


# language subtag -> (rule, the forms a translation must give)
_RULES: dict[str, tuple[Callable[[int], str], frozenset[str]]] = {
    "en": (_one_other, frozenset({"one", "other"})),
    "de": (_one_other, frozenset({"one", "other"})),
    "tr": (_one_other, frozenset({"one", "other"})),
    "it": (_spanish, frozenset({"one", "other"})),
    "es": (_spanish, frozenset({"one", "other"})),
    "fr": (_zero_one_singular, frozenset({"one", "other"})),
    "pt": (_zero_one_singular, frozenset({"one", "other"})),
    "ru": (_russian, frozenset({"one", "few", "many", "other"})),
    "zh": (_no_plural, frozenset({"other"})),
    "ja": (_no_plural, frozenset({"other"})),
    "ko": (_no_plural, frozenset({"other"})),
}
# `many` for exact millions in es/fr/pt/it is optional: without it a lookup
# uses `other`, which reads correctly ("1000000 de puntos").


def language_of(locale: str) -> str:
    """Return a locale's language subtag, lower case: `"pt-BR"` -> `"pt"`."""
    return locale.replace("_", "-").split("-", 1)[0].lower()


def supported_languages() -> tuple[str, ...]:
    """Return the language subtags that have plural rules, sorted."""
    return tuple(sorted(_RULES))


def _rule(locale: str) -> tuple[Callable[[int], str], frozenset[str]]:
    language = language_of(locale)
    try:
        return _RULES[language]
    except KeyError:
        raise ValueError(
            f"no plural rules for {language!r} (from locale {locale!r}); "
            f"supported: {', '.join(supported_languages())}"
        ) from None


def plural_category(locale: str, count: int) -> str:
    """Return the CLDR plural category `count` takes in `locale`.

    Args:
        locale: A BCP 47 tag such as `"ru"` or `"pt-BR"`.
        count: The number being counted. Negative counts follow their
            magnitude.

    Returns:
        One of `PLURAL_FORMS`.

    Raises:
        ValueError: If the language has no rules here.
        TypeError: If `count` is not an integer.
    """
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError(f"a plural count must be an int, not {count!r}")
    rule, _ = _rule(locale)
    return rule(abs(count))


def required_plural_forms(locale: str) -> set[str]:
    """Return the plural forms a translation into `locale` must provide.

    Raises:
        ValueError: If the language has no rules here.
    """
    _, required = _rule(locale)
    return set(required)
