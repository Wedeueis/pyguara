"""String tables: keys in code, text per locale, plurals by each language's rule."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pyguara.i18n import (
    LocaleTable,
    MissingStringError,
    Translator,
    UnsafePlaceholderError,
    plural_category,
    required_plural_forms,
)

# --------------------------------------------------------------------------- #
# Plural rules (CLDR, integers)                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", {0: "other", 1: "one", 2: "other", 11: "other", 21: "other"}),
        ("de", {0: "other", 1: "one", 2: "other"}),
        ("tr", {0: "other", 1: "one", 5: "other"}),
        ("es", {0: "other", 1: "one", 2: "other", 1_000_000: "many"}),
        ("fr", {0: "one", 1: "one", 2: "other", 2_000_000: "many"}),
        ("pt-BR", {0: "one", 1: "one", 2: "other", 1_000_000: "many"}),
        (
            "ru",
            {
                0: "many",
                1: "one",
                2: "few",
                4: "few",
                5: "many",
                11: "many",
                12: "many",
                14: "many",
                21: "one",
                22: "few",
                25: "many",
                101: "one",
                111: "many",
                112: "many",
                122: "few",
            },
        ),  # fmt: skip
        ("zh-Hans", {0: "other", 1: "other", 2: "other"}),
        ("ja", {1: "other", 100: "other"}),
        ("ko", {1: "other"}),
    ],
)
def test_each_language_picks_its_plural_form(locale: str, expected: dict) -> None:
    for count, category in expected.items():
        assert plural_category(locale, count) == category, (locale, count)


def test_negative_counts_follow_their_magnitude() -> None:
    assert plural_category("en", -1) == "one"
    assert plural_category("ru", -3) == "few"


def test_a_language_without_rules_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="no plural rules for 'xx'"):
        plural_category("xx", 1)


def test_the_forms_a_translation_must_give() -> None:
    assert required_plural_forms("en") == {"one", "other"}
    assert required_plural_forms("ru") == {"one", "few", "many", "other"}
    assert required_plural_forms("ja") == {"other"}
    # `many` in Spanish, French and Portuguese is for exact millions;
    # without it they fall back to `other`, which reads correctly.
    assert required_plural_forms("fr") == {"one", "other"}


# --------------------------------------------------------------------------- #
# Lookup                                                                       #
# --------------------------------------------------------------------------- #


def _tables(**locales: dict) -> dict[str, LocaleTable]:
    return {
        code: LocaleTable.from_mapping(code, data) for code, data in locales.items()
    }


EN = {
    "title": "Reclaimer",
    "room.waiting": "Waiting for {player}...",
    "hud.salvage": {"one": "{count} scrap", "other": "{count} scraps"},
    "only.english": "Only in English",
}
RU = {
    "_meta": {"reviewed": False},
    "title": "Рекламатор",
    "room.waiting": "Ожидание {player}...",
    "hud.salvage": {
        "one": "{count} обломок",
        "few": "{count} обломка",
        "many": "{count} обломков",
        "other": "{count} обломка",
    },
}


def test_a_key_reads_in_the_current_locale() -> None:
    tr = Translator(_tables(en=EN, ru=RU), locale="ru")
    assert tr("title") == "Рекламатор"
    tr.locale = "en"
    assert tr("title") == "Reclaimer"


def test_placeholders_are_filled_by_name() -> None:
    tr = Translator(_tables(en=EN, ru=RU), locale="ru")
    assert tr("room.waiting", player="Ana") == "Ожидание Ana..."


@pytest.mark.parametrize(
    ("count", "text"),
    [(1, "1 обломок"), (3, "3 обломка"), (5, "5 обломков"), (21, "21 обломок")],
)
def test_count_picks_the_plural_form(count: int, text: str) -> None:
    tr = Translator(_tables(en=EN, ru=RU), locale="ru")
    assert tr("hud.salvage", count=count) == text


def test_a_plural_entry_needs_a_count() -> None:
    tr = Translator(_tables(en=EN), locale="en")
    with pytest.raises(TypeError, match="count"):
        tr("hud.salvage")


def test_a_missing_placeholder_value_raises() -> None:
    tr = Translator(_tables(en=EN), locale="en")
    with pytest.raises(KeyError, match="player"):
        tr("room.waiting")


def test_a_key_missing_from_a_translation_falls_back_to_english(caplog) -> None:
    tr = Translator(_tables(en=EN, ru=RU), locale="ru")
    assert tr("only.english") == "Only in English"
    assert tr("only.english") == "Only in English"
    warnings = [r for r in caplog.records if "only.english" in r.getMessage()]
    assert len(warnings) == 1, "warned once per key, not once per frame"


def test_a_key_missing_from_english_is_a_bug_in_the_game() -> None:
    tr = Translator(_tables(en=EN, ru=RU), locale="ru")
    with pytest.raises(MissingStringError, match="'no.such.key'"):
        tr("no.such.key")


def test_a_missing_plural_form_uses_other() -> None:
    fr = {"hud.salvage": {"one": "{count} débris", "other": "{count} débris"}}
    tr = Translator(_tables(en=EN, fr=fr), locale="fr")
    assert tr("hud.salvage", count=3_000_000) == "3000000 débris"


def test_a_plain_string_serves_every_plural_form() -> None:
    ja = {"hud.salvage": "スクラップ {count} 個"}
    tr = Translator(_tables(en=EN, ja=ja), locale="ja")
    assert tr("hud.salvage", count=7) == "スクラップ 7 個"


def test_switching_to_an_unknown_locale_is_refused() -> None:
    tr = Translator(_tables(en=EN), locale="en")
    with pytest.raises(ValueError, match="'de'.*available: en"):
        tr.locale = "de"


def test_listeners_hear_a_locale_change() -> None:
    tr = Translator(_tables(en=EN, ru=RU), locale="en")
    heard: list[str] = []
    tr.on_change(heard.append)
    tr.locale = "ru"
    tr.locale = "ru"  # unchanged: not announced again
    assert heard == ["ru"]


# --------------------------------------------------------------------------- #
# Untrusted text                                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text",
    ["{player.__class__}", "{player[0]}", "{0}", "{}", "{count!r}", "{count:>{w}}"],
)
def test_a_placeholder_may_only_be_a_plain_name(text: str) -> None:
    """A translation file is data from outside the code; `str.format` on it
    could walk attributes of whatever is passed in."""
    with pytest.raises(UnsafePlaceholderError):
        LocaleTable.from_mapping("en", {"k": text})


def test_a_format_spec_on_a_plain_name_is_allowed() -> None:
    table = LocaleTable.from_mapping("en", {"k": "{ratio:.0%}"})
    assert Translator({"en": table}, locale="en")("k", ratio=0.5) == "50%"


def test_literal_braces_survive() -> None:
    table = LocaleTable.from_mapping("en", {"k": "{{not a field}} {name}"})
    assert Translator({"en": table}, locale="en")("k", name="x") == "{not a field} x"


def test_an_entry_must_be_text_or_plural_forms() -> None:
    with pytest.raises(ValueError, match="'k'"):
        LocaleTable.from_mapping("en", {"k": 3})
    with pytest.raises(ValueError, match="'lots'"):
        LocaleTable.from_mapping("en", {"k": {"lots": "x", "other": "y"}})
    with pytest.raises(ValueError, match="other"):
        LocaleTable.from_mapping("en", {"k": {"one": "x"}})


# --------------------------------------------------------------------------- #
# Files                                                                        #
# --------------------------------------------------------------------------- #


def _write(directory: Path, code: str, data: dict) -> None:
    (directory / f"{code}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def test_a_directory_of_json_files_is_one_table_per_locale(tmp_path: Path) -> None:
    _write(tmp_path, "en", EN)
    _write(tmp_path, "ru", RU)
    _write(tmp_path, "pt-BR", {"title": "Recuperador"})

    tr = Translator.from_directory(tmp_path, locale="pt-BR")

    assert tr.available == ("en", "pt-BR", "ru")
    assert tr("title") == "Recuperador"
    assert tr.tables["ru"].reviewed is False
    assert tr.tables["en"].reviewed is True


def test_the_source_locale_must_be_present(tmp_path: Path) -> None:
    _write(tmp_path, "ru", RU)
    with pytest.raises(FileNotFoundError, match="en.json"):
        Translator.from_directory(tmp_path, locale="ru")


def test_a_broken_file_names_itself(tmp_path: Path) -> None:
    _write(tmp_path, "en", EN)
    (tmp_path / "de.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="de.json"):
        Translator.from_directory(tmp_path, locale="en")


def test_a_file_name_must_be_a_locale_with_plural_rules(tmp_path: Path) -> None:
    _write(tmp_path, "en", EN)
    _write(tmp_path, "xx", {"title": "?"})
    with pytest.raises(ValueError, match="xx.json"):
        Translator.from_directory(tmp_path, locale="en")


# --------------------------------------------------------------------------- #
# Choosing a locale                                                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("wanted", "chosen"),
    [
        ("pt-BR", "pt-BR"),
        ("pt_PT", "pt-BR"),  # same language, the closest we have
        ("de_DE.UTF-8", "de"),
        ("zh-CN", "zh-Hans"),
        ("ZH_hans", "zh-Hans"),
        ("ja_JP", "ja"),
        ("fi_FI", "en"),  # nothing close: the source
        ("", "en"),
    ],
)
def test_the_best_available_locale_is_chosen(wanted: str, chosen: str) -> None:
    from pyguara.i18n import best_locale

    available = ("de", "en", "ja", "pt-BR", "zh-Hans")
    assert best_locale(wanted, available, source="en") == chosen


@pytest.mark.parametrize(
    ("steam", "locale"),
    [
        ("english", "en"),
        ("schinese", "zh-Hans"),
        ("russian", "ru"),
        ("spanish", "es"),
        ("latam", "es"),
        ("brazilian", "pt-BR"),
        ("german", "de"),
        ("japanese", "ja"),
        ("koreana", "ko"),
        ("french", "fr"),
        ("turkish", "tr"),
    ],
)
def test_steam_language_names_map_to_locales(steam: str, locale: str) -> None:
    from pyguara.i18n import locale_from_steam

    assert locale_from_steam(steam) == locale


def test_an_unknown_steam_language_is_none() -> None:
    from pyguara.i18n import locale_from_steam

    assert locale_from_steam("klingon") is None


def test_choose_narrows_to_the_closest_locale_and_switches() -> None:
    """For a locale from Steam or a settings menu, as startup chooses."""
    tr = Translator(_tables(en=EN, ru=RU), locale="en")
    heard: list[str] = []
    tr.on_change(heard.append)

    assert tr.choose("ru_RU") == "ru"
    assert tr.locale == "ru"
    assert heard == ["ru"]
    assert tr.choose("klingon") == "en"
