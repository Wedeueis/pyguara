"""`pyguara new` writes a project that runs."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

import pyguara
from pyguara.cli import main
from pyguara.cli.new import package_name, scaffold

pytestmark = pytest.mark.cli

RUN_THE_SCENE = """
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

from pyguara.application.bootstrap import create_headless_application
from pyguara.common.components import Transform

from first_game.__main__ import configure, main
from first_game.scenes import MainScene

assert callable(main) and callable(configure)
app = create_headless_application()
scene = MainScene()
app.begin(scene)
for _ in range(30):
    app.step()
(box,) = scene.entity_manager.get_entities_with(Transform)
print(box.get_component(Transform).position.x > 0)
app.shutdown()
"""


class TestTheName:
    @pytest.mark.parametrize(
        ("name", "package"),
        [("demo", "demo"), ("My-Game", "my_game"), ("space_2", "space_2")],
    )
    def test_a_usable_name_becomes_its_package(self, name: str, package: str) -> None:
        assert package_name(name) == package

    @pytest.mark.parametrize(
        "name", ["2fast", "has space", "", "class", "pyguara", "json", "a/b", "é"]
    )
    def test_a_name_that_could_not_be_imported_is_refused(self, name: str) -> None:
        with pytest.raises(click.BadParameter):
            package_name(name)


class TestTheProject:
    def test_it_declares_its_package_script_and_engine(self, tmp_path: Path) -> None:
        scaffold(tmp_path / "first-game", "first-game")

        project = tomllib.loads(
            (tmp_path / "first-game" / "pyproject.toml").read_text(encoding="utf-8")
        )

        assert project["project"]["name"] == "first-game"
        assert project["project"]["dependencies"] == [f"pyguara>={pyguara.__version__}"]
        assert project["project"]["scripts"] == {
            "first-game": "first_game.__main__:main"
        }
        assert (tmp_path / "first-game" / "assets").is_dir()

    def test_no_file_edits_the_import_path(self, tmp_path: Path) -> None:
        written = scaffold(tmp_path / "first-game", "first-game")

        sources = [path for path in written if path.suffix == ".py"]
        assert len(sources) == 3
        assert all("sys.path" not in path.read_text("utf-8") for path in sources)

    def test_a_directory_with_something_in_it_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "kept.txt").write_text("mine", encoding="utf-8")

        with pytest.raises(click.ClickException, match="not empty"):
            scaffold(tmp_path, "first-game")

        assert [path.name for path in tmp_path.iterdir()] == ["kept.txt"]

    def test_its_scene_runs_and_the_box_moves(self, tmp_path: Path) -> None:
        project = tmp_path / "first-game"
        scaffold(project, "first-game")

        completed = subprocess.run(
            [sys.executable, "-c", RUN_THE_SCENE],
            capture_output=True,
            text=True,
            cwd=project,
            timeout=120,
            check=False,
        )

        assert completed.returncode == 0, completed.stderr
        assert "True" in completed.stdout.splitlines(), completed.stdout


class TestTheCommand:
    def test_it_creates_the_project_and_its_agent_instructions(
        self, tmp_path: Path
    ) -> None:
        result = CliRunner().invoke(
            main, ["new", "first-game", "--directory", str(tmp_path / "out")]
        )

        assert result.exit_code == 0, result.output
        assert (tmp_path / "out" / "first_game" / "__main__.py").is_file()
        assert "PyGuara" in (tmp_path / "out" / "AGENTS.md").read_text("utf-8")
        assert "python -m first_game" in result.output

    def test_the_instructions_can_be_left_out(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(
            main,
            [
                "new",
                "first-game",
                "--directory",
                str(tmp_path / "out"),
                "--no-instructions",
            ],
        )

        assert result.exit_code == 0, result.output
        assert not (tmp_path / "out" / "AGENTS.md").exists()

    def test_a_bad_name_writes_nothing(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(
            main, ["new", "class", "--directory", str(tmp_path / "out")]
        )

        assert result.exit_code != 0
        assert "keyword" in result.output
        assert not (tmp_path / "out").exists()
