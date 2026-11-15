"""`pyguara i18n check`: every locale held against the source."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from pyguara.cli import main
from pyguara.i18n.check import check_directory


def _write(directory: Path, code: str, data: dict) -> None:
    (directory / f"{code}.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


EN = {
    "title": "Reclaimer",
    "room.waiting": "Waiting for {player}...",
    "hud.salvage": {"one": "{count} scrap", "other": "{count} scraps"},
}


def test_a_complete_translation_has_nothing_to_report(tmp_path: Path) -> None:
    _write(tmp_path, "en", EN)
    _write(
        tmp_path,
        "de",
        {
            "title": "Reclaimer",
            "room.waiting": "Warte auf {player} ...",
            "hud.salvage": {"one": "{count} Schrott", "other": "{count} Schrott"},
        },
    )
    report = check_directory(tmp_path)
    assert report.errors == []
    assert report.warnings == []


def test_every_kind_of_problem_is_named_with_its_locale_and_key(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "en", EN)
    _write(
        tmp_path,
        "ru",
        {
            "_meta": {"reviewed": False},
            "room.waiting": "Ожидание {name}...",  # wrong placeholder
            "hud.salvage": {"one": "{count} обломок", "other": "{count}"},
            "stray": "not in English",
        },
    )
    report = check_directory(tmp_path)

    assert "ru: 'title' is missing" in report.errors
    assert any(
        "ru: 'room.waiting'" in e and "{name}" in e and "{player}" in e
        for e in report.errors
    )
    assert any(
        "ru: 'hud.salvage'" in e and "few" in e and "many" in e for e in report.errors
    )
    assert "ru: 'stray' is not in the source locale" in report.errors
    assert "ru: not reviewed by a native speaker" in report.warnings


def test_a_plain_string_where_the_source_has_plural_forms_is_fine_without_plurals(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "en", EN)
    _write(
        tmp_path,
        "ja",
        {
            "title": "R",
            "room.waiting": "{player} を待機中",
            "hud.salvage": "{count} 個",
        },
    )
    assert check_directory(tmp_path).errors == []


def test_a_plain_string_for_a_language_with_plurals_is_an_error(tmp_path: Path) -> None:
    _write(tmp_path, "en", EN)
    _write(
        tmp_path,
        "ru",
        {"title": "R", "room.waiting": "{player}", "hud.salvage": "{count} обломков"},
    )
    errors = check_directory(tmp_path).errors
    assert any("ru: 'hud.salvage'" in e and "plural" in e for e in errors)


def test_a_file_that_does_not_load_is_an_error_not_a_crash(tmp_path: Path) -> None:
    _write(tmp_path, "en", EN)
    (tmp_path / "fr.json").write_text("{", encoding="utf-8")
    _write(tmp_path, "xx", {"title": "?"})
    errors = check_directory(tmp_path).errors
    assert any(e.startswith("fr.json:") for e in errors)
    assert any(e.startswith("xx.json:") and "plural rules" in e for e in errors)


def test_the_command_fails_on_errors_and_optionally_on_unreviewed(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "en", EN)
    _write(
        tmp_path,
        "de",
        {
            "_meta": {"reviewed": False},
            "title": "R",
            "room.waiting": "{player}",
            "hud.salvage": {"one": "{count}", "other": "{count}"},
        },
    )
    runner = CliRunner()

    ok = runner.invoke(main, ["i18n", "check", str(tmp_path)])
    assert ok.exit_code == 0, ok.output
    assert "de: not reviewed" in ok.output
    assert "2 locales" in ok.output

    strict = runner.invoke(main, ["i18n", "check", str(tmp_path), "--require-reviewed"])
    assert strict.exit_code == 1

    (tmp_path / "de.json").unlink()
    _write(tmp_path, "de", {"title": "R"})
    broken = runner.invoke(main, ["i18n", "check", str(tmp_path)])
    assert broken.exit_code == 1
    assert "de: 'room.waiting' is missing" in broken.output
