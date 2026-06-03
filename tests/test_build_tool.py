"""Tests for the standalone game compiler tool."""

import sys
from click.testing import CliRunner

from pyguara.cli.build import (
    _find_assets_folder,
    _build_pyinstaller_args,
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

    assert "pyinstaller" in args
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
    assert "pyinstaller" in result.output
    assert "CLI_Test_Game" in result.output
    assert "--onefile" in result.output
