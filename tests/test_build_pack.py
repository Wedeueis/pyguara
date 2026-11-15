"""`pyguara build --pack`: assets baked into one file, mounted when frozen."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from pyguara import assets
from pyguara.cli.build import build
from pyguara.cli.pack import bake_pack


@pytest.fixture(autouse=True)
def _clean():
    yield
    assets.unmount_all()
    assets._reset_bundled_for_tests()


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    (root / "assets" / "sprites").mkdir(parents=True)
    (root / "assets" / "sprites" / "hero.png").write_bytes(b"\x89PNG fake")
    (root / "assets" / "sprites" / "hero.png.meta").write_text("{}", encoding="utf-8")
    (root / "assets" / "levels.json").write_text('{"a": 1}' * 100, encoding="utf-8")
    (root / "assets" / "__pycache__").mkdir()
    (root / "assets" / "__pycache__" / "x.pyc").write_bytes(b"junk")
    (root / "assets" / ".DS_Store").write_bytes(b"junk")
    (root / "main.py").write_text("print('hi')\n", encoding="utf-8")
    return root


def test_the_pack_holds_the_folder_under_its_own_name(
    project: Path, tmp_path: Path
) -> None:
    pack = tmp_path / "Game.pak"
    report = bake_pack([project / "assets"], pack)

    with zipfile.ZipFile(pack) as archive:
        names = archive.namelist()
        assert sorted(names) == [
            "assets/levels.json",
            "assets/sprites/hero.png",
            "assets/sprites/hero.png.meta",
        ]
        # Already compressed: stored. Text: deflated.
        assert (
            archive.getinfo("assets/sprites/hero.png").compress_type
            == zipfile.ZIP_STORED
        )
        assert (
            archive.getinfo("assets/levels.json").compress_type == zipfile.ZIP_DEFLATED
        )
    assert report.files == 3


def test_the_pack_is_reproducible(project: Path, tmp_path: Path) -> None:
    first = bake_pack([project / "assets"], tmp_path / "a.pak")
    second = bake_pack([project / "assets"], tmp_path / "b.pak")
    assert (tmp_path / "a.pak").read_bytes() == (tmp_path / "b.pak").read_bytes()
    assert first.files == second.files


def test_two_folders_with_one_name_are_refused(tmp_path: Path) -> None:
    (tmp_path / "x" / "assets").mkdir(parents=True)
    (tmp_path / "y" / "assets").mkdir(parents=True)
    with pytest.raises(ValueError, match="assets"):
        bake_pack(
            [tmp_path / "x" / "assets", tmp_path / "y" / "assets"], tmp_path / "p.pak"
        )


def test_build_with_pack_bundles_the_pack_not_the_folder(
    project: Path, tmp_path: Path
) -> None:
    result = CliRunner().invoke(
        build,
        [
            str(project / "main.py"),
            "--output",
            str(tmp_path / "dist"),
            "--pack",
            "--dry-run",
            "--name",
            "Game",
        ],
    )
    assert result.exit_code == 0, result.output
    pack = tmp_path / "dist" / "build" / "Game.pak"
    assert pack.is_file(), "the pack is baked even on a dry run, to be inspected"
    separator = ";" if sys.platform == "win32" else ":"
    assert f"{pack}{separator}." in result.output
    assert f"{project / 'assets'}{separator}assets" not in result.output


def test_without_pack_the_folder_is_bundled_as_before(
    project: Path, tmp_path: Path
) -> None:
    result = CliRunner().invoke(
        build,
        [str(project / "main.py"), "--output", str(tmp_path / "dist"), "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    separator = ";" if sys.platform == "win32" else ":"
    assert f"{project / 'assets'}{separator}assets" in result.output
    assert ".pak" not in result.output


def test_a_frozen_game_mounts_the_packs_in_its_bundle(
    project: Path, tmp_path: Path, monkeypatch
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    bake_pack([project / "assets"], bundle / "Game.pak")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.chdir(tmp_path)  # not the bundle: paths come from code

    data = assets.read_text(bundle / "assets" / "levels.json")

    assert data.startswith('{"a": 1}')
    assert assets.mounted_packs() == (bundle / "Game.pak",)


def test_an_unfrozen_game_mounts_nothing(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    assets.read_text(tmp_path / "f.txt")
    assert assets.mounted_packs() == ()
