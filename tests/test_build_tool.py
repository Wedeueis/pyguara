"""Tests for the standalone game compiler tool."""

import sys

import pytest
from click.testing import CliRunner
from PIL import Image

from pyguara import native
from pyguara.cli.build import (
    _build_pyinstaller_args,
    _find_assets_folder,
    _icon_for_host,
    _path_separator,
    build,
)


def test_path_separator():
    """Assert path separator returns correct separator for the active OS."""
    sep = _path_separator()
    if sys.platform == "win32":
        assert sep == ";"
    else:
        assert sep == ":"


def test_find_assets_folder(tmp_path):
    """Test auto-detection of asset folder candidates."""
    # Create temp project structure
    project_file = tmp_path / "main.py"
    project_file.touch()

    # Case 1: No asset directory exists
    assert _find_assets_folder(project_file) is None

    # Case 2: One of the candidates exists
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    found = _find_assets_folder(project_file)
    assert found == assets_dir

    # Cleanup and check another candidate
    assets_dir.rmdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    found = _find_assets_folder(project_file)
    assert found == data_dir


def test_build_pyinstaller_args(tmp_path):
    """Verify PyInstaller CLI argument builder."""
    entry_point = tmp_path / "main.py"
    output_dir = tmp_path / "dist"
    icon_path = tmp_path / "icon.png"
    icon_path.touch()

    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()

    # 1. Test basic arguments
    args = _build_pyinstaller_args(
        entry_point=entry_point,
        output_dir=output_dir,
        name="TestGame",
        onefile=True,
        windowed=True,
        icon=icon_path,
        assets_dirs=[assets_dir],
        extra_data=["extra_src:extra_dst"],
        hidden_imports=["some_hidden"],
        clean=True,
        debug=True,
    )

    # Launched through the running interpreter, not a bare `pyinstaller` script.
    assert args[:3] == [sys.executable, "-m", "PyInstaller"]
    assert str(entry_point) in args
    assert "--onefile" in args
    assert "--windowed" in args
    assert "--clean" in args
    assert "--debug=all" in args
    assert "--noconfirm" in args

    # Check paths and names
    assert "--name" in args
    assert "TestGame" in args
    assert "--distpath" in args
    assert str(output_dir) in args

    # Check assets mapping
    sep = _path_separator()
    expected_data = f"{assets_dir}{sep}assets"
    assert any(expected_data in arg for arg in args)

    # Check extra data and hidden imports
    assert any("extra_src:extra_dst" in arg for arg in args)
    assert any("some_hidden" in arg for arg in args)

    # And the native extension, which is the one hidden import that is
    # invisible to PyInstaller *and* silent when missing: a game frozen
    # without it runs the pure-Python stores and is only slower.
    assert native._MODULE_NAME in args


class TestTheHostIcon:
    """PyInstaller converts nothing, and cannot cross-compile.

    So the icon must already be in the host's format, and the host cases
    worth testing are the two this suite never runs on -- `platform=` is
    there for exactly that. Windows *fails the build* on a `.png`, which
    is the one that would otherwise be found by a Windows contributor
    rather than by CI.
    """

    @pytest.fixture
    def logo(self, tmp_path):
        path = tmp_path / "logo.png"
        Image.new("RGBA", (512, 512), (10, 120, 200, 255)).save(path)
        return path

    @pytest.mark.parametrize(
        ("platform", "suffix"),
        [("win32", ".ico"), ("darwin", ".icns"), ("linux", ".png")],
    )
    def test_a_png_becomes_what_the_host_needs(self, logo, tmp_path, platform, suffix):
        converted = _icon_for_host(logo, tmp_path / "work", platform=platform)

        assert converted.suffix == suffix
        assert converted.is_file()

    def test_an_icon_already_in_the_right_format_is_untouched(self, logo, tmp_path):
        """No copy, no conversion, and no work directory created."""
        workdir = tmp_path / "work"

        assert _icon_for_host(logo, workdir, platform="linux") == logo
        assert not workdir.exists()

    def test_the_converted_icon_lands_in_the_work_directory(self, logo, tmp_path):
        """Build scratch, not the shipped bundle."""
        workdir = tmp_path / "work"

        converted = _icon_for_host(logo, workdir, platform="win32")

        assert converted.parent == workdir


def test_the_macos_bundle_identifier_is_passed_through(tmp_path):
    """Not host-gated on purpose: PyInstaller ignores it off macOS.

    Gating it would mean a spec file generated on Linux differed from the
    one generated on macOS for the same command, which is a difference
    nobody would look for.
    """
    args = _build_pyinstaller_args(
        entry_point=tmp_path / "main.py",
        output_dir=tmp_path / "dist",
        name=None,
        onefile=False,
        windowed=True,
        icon=None,
        assets_dirs=[],
        extra_data=[],
        hidden_imports=[],
        clean=False,
        debug=False,
        bundle_id="com.studio.mygame",
    )

    assert "--osx-bundle-identifier" in args
    assert "com.studio.mygame" in args


def test_cli_build_dry_run(tmp_path):
    """Test Click build command CLI wrapper using CliRunner in dry-run mode."""
    entry_point = tmp_path / "game_main.py"
    entry_point.touch()

    runner = CliRunner()
    result = runner.invoke(
        build,
        [
            str(entry_point),
            "--output",
            str(tmp_path / "dist"),
            "--name",
            "CLI_Test_Game",
            "--onefile",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Dry run - would execute:" in result.output
    assert "-m PyInstaller" in result.output
    assert "CLI_Test_Game" in result.output
    assert "--onefile" in result.output


def test_build_pyinstaller_args_onedir(tmp_path):
    """onedir mode should pass --onedir and never --onefile."""
    args = _build_pyinstaller_args(
        entry_point=tmp_path / "main.py",
        output_dir=tmp_path / "dist",
        name=None,
        onefile=False,
        windowed=True,
        icon=None,
        assets_dirs=[],
        extra_data=[],
        hidden_imports=[],
        clean=False,
        debug=False,
    )
    assert "--onedir" in args
    assert "--onefile" not in args


def test_cli_build_reports_missing_pyinstaller(tmp_path, monkeypatch):
    """A real (non-dry-run) build with PyInstaller absent exits 1 with a hint."""
    monkeypatch.setattr("pyguara.cli.build._check_pyinstaller", lambda: False)

    entry_point = tmp_path / "game_main.py"
    entry_point.touch()

    result = CliRunner().invoke(build, [str(entry_point)])

    assert result.exit_code == 1
    assert "not installed" in result.output


def test_cli_build_dry_run_auto_detects_assets(tmp_path):
    """Without -a, an adjacent assets/ folder is auto-added as --add-data."""
    entry_point = tmp_path / "main.py"
    entry_point.touch()
    (tmp_path / "assets").mkdir()

    result = CliRunner().invoke(build, [str(entry_point), "--dry-run"])

    assert result.exit_code == 0
    assert "Auto-detected assets folder" in result.output
    assert "--add-data" in result.output
    assert str((tmp_path / "assets").resolve()) in result.output
