"""`pyguara build` gives a Windows `.exe` its file details.

The file is checked by PyInstaller's own parser, not by a stand-in. Off
Windows that module imports two things only Windows has, `pefile`'s
resource table and `win32api`, neither of which parsing or serialising
touches, so they are stubbed. Its binary encoding assumes Windows' 32-bit
`long`, so writing the resource into a real executable and reading it back
is tested on Windows only.
"""

from __future__ import annotations

import importlib
import shutil
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from pyguara.cli import version_resource
from pyguara.cli.build import build
from pyguara.cli.version_resource import VersionInfo

pytest.importorskip("PyInstaller")

MODULE = "PyInstaller.utils.win32.versioninfo"


@pytest.fixture
def versioninfo(monkeypatch: pytest.MonkeyPatch) -> Any:
    """PyInstaller's version-info module, importable on any platform."""
    if sys.platform != "win32":
        import PyInstaller.compat

        monkeypatch.setitem(sys.modules, "pefile", types.ModuleType("pefile"))
        monkeypatch.setattr(PyInstaller.compat, "win32api", object(), raising=False)
    monkeypatch.delitem(sys.modules, MODULE, raising=False)
    module = importlib.import_module(MODULE)
    yield module
    sys.modules.pop(MODULE, None)


def _strings(info: Any) -> dict[str, str]:
    [table] = info.kids[0].kids
    return {entry.name: entry.val for entry in table.kids}


def _load(versioninfo: Any, text: str, tmp_path: Path) -> Any:
    path = tmp_path / "version_info.txt"
    path.write_text(text, encoding="utf-8")
    return versioninfo.load_version_info_from_text_file(str(path))


FULL = VersionInfo("Reclaimer", "1.4.0rc2", "Guara Studio", "(c) 2026 Guara Studio")


def test_pyinstaller_reads_every_field_back(versioninfo: Any, tmp_path: Path) -> None:
    info = _load(versioninfo, version_resource.render(FULL), tmp_path)

    assert _strings(info) == {
        "CompanyName": "Guara Studio",
        "FileDescription": "Reclaimer",
        "FileVersion": "1.4.0rc2",
        "InternalName": "Reclaimer",
        "LegalCopyright": "(c) 2026 Guara Studio",
        "OriginalFilename": "Reclaimer.exe",
        "ProductName": "Reclaimer",
        "ProductVersion": "1.4.0rc2",
    }
    assert info.ffi.fileVersionMS == (1 << 16) | 4
    assert info.ffi.fileVersionLS == 0


def test_a_name_that_looks_like_code_stays_a_string(
    versioninfo: Any, tmp_path: Path
) -> None:
    """PyInstaller `eval`s the file, so every value must be a literal."""
    hostile = "x', 'y'), __import__('os').system('exit 1'), ('"
    info = _load(
        versioninfo,
        version_resource.render(VersionInfo(hostile, "1.0", copyright=hostile)),
        tmp_path,
    )

    assert _strings(info)["ProductName"] == hostile
    assert _strings(info)["LegalCopyright"] == hostile


def test_fields_not_given_are_left_out(versioninfo: Any, tmp_path: Path) -> None:
    info = _load(
        versioninfo, version_resource.render(VersionInfo("Game", "2.0")), tmp_path
    )
    assert "CompanyName" not in _strings(info)
    assert "LegalCopyright" not in _strings(info)


@pytest.mark.parametrize(
    ("version", "numbers"),
    [
        ("1", (1, 0, 0, 0)),
        ("0.8.0", (0, 8, 0, 0)),
        ("1.2.3.4", (1, 2, 3, 4)),
        ("v2.10.1", (2, 10, 1, 0)),
        ("1.4.0rc2", (1, 4, 0, 0)),
        ("3.0.0.dev7+abc", (3, 0, 0, 0)),
    ],
)
def test_the_numbers_windows_stores(
    version: str, numbers: tuple[int, int, int, int]
) -> None:
    assert version_resource.numeric_version(version) == numbers


@pytest.mark.parametrize("version", ["", "beta", "1.70000"])
def test_a_version_windows_cannot_store_is_refused(version: str) -> None:
    with pytest.raises(ValueError, match="version"):
        version_resource.numeric_version(version)


def _game(tmp_path: Path, pyproject: str | None) -> Path:
    game = tmp_path / "game"
    (game / "src").mkdir(parents=True)
    if pyproject is not None:
        (game / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    entry = game / "src" / "main.py"
    entry.write_text("print('hi')\n", encoding="utf-8")
    return entry


def _dry_run(entry: Path, tmp_path: Path, *extra: str) -> Any:
    return CliRunner().invoke(
        build, [str(entry), "-o", str(tmp_path / "dist"), "--dry-run", *extra]
    )


def test_the_version_comes_from_the_games_pyproject(tmp_path: Path) -> None:
    entry = _game(tmp_path, '[project]\nname = "game"\nversion = "0.3.1"\n')

    result = _dry_run(entry, tmp_path, "--name", "Game")

    assert result.exit_code == 0, result.output
    written = tmp_path / "dist" / "build" / "version_info.txt"
    assert f"--version-file {written}" in result.output
    assert "'0.3.1'" in written.read_text(encoding="utf-8")
    assert "'Game.exe'" in written.read_text(encoding="utf-8")


def test_the_flag_overrides_the_pyproject(tmp_path: Path) -> None:
    entry = _game(tmp_path, '[project]\nname = "game"\nversion = "0.3.1"\n')

    result = _dry_run(entry, tmp_path, "--game-version", "1.0.0")

    assert result.exit_code == 0, result.output
    text = (tmp_path / "dist" / "build" / "version_info.txt").read_text("utf-8")
    assert "'1.0.0'" in text
    assert "0.3.1" not in text


def test_with_no_version_there_is_no_resource_and_it_says_so(
    tmp_path: Path,
) -> None:
    entry = _game(tmp_path, '[project]\nname = "game"\ndynamic = ["version"]\n')

    result = _dry_run(entry, tmp_path)

    assert result.exit_code == 0, result.output
    assert "--version-file" not in result.output
    assert "no file details" in result.output


def test_a_company_with_no_version_to_carry_it_is_refused(tmp_path: Path) -> None:
    """Rather than dropped without a word."""
    entry = _game(tmp_path, None)

    result = _dry_run(entry, tmp_path, "--company", "Guara Studio")

    assert result.exit_code == 2
    assert "need a version" in result.output


def test_a_bad_version_is_a_usage_error(tmp_path: Path) -> None:
    entry = _game(tmp_path, None)

    result = _dry_run(entry, tmp_path, "--game-version", "beta")

    assert result.exit_code == 2
    assert "--game-version" in result.output


@pytest.mark.skipif(sys.platform != "win32", reason="writes a Windows resource")
def test_a_real_executable_carries_the_details(
    versioninfo: Any, tmp_path: Path
) -> None:
    """As PyInstaller stamps the built `.exe`, then as Explorer reads it."""
    exe = tmp_path / "game.exe"
    shutil.copy(sys.executable, exe)
    info = _load(versioninfo, version_resource.render(FULL), tmp_path)

    versioninfo.write_version_info_to_executable(str(exe), info)
    back = versioninfo.read_version_info_from_executable(str(exe))

    assert back is not None
    assert _strings(back)["ProductName"] == "Reclaimer"
    assert _strings(back)["FileVersion"] == "1.4.0rc2"
    assert back.ffi.fileVersionMS == (1 << 16) | 4
