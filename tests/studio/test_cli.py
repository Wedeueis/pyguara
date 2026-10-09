"""`pyguara studio`: the terminal front door.

The test that earns its keep here is the one about **stdout discipline**.
Both servers speak a line protocol on stdout, and a plain engine boot
writes five lines of prose into it: pygame prints a version banner on
import, and `EngineLogger` builds its console handler around `sys.stdout`.
A reader on the other end sees a parse error and blames the protocol. So
the first thing asserted is that the only bytes on stdout are protocol.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from pyguara.cli.studio import studio


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A minimal project tree."""
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "level_1.scene").write_text("{}", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    return tmp_path


def _ops(project: Path, *requests: dict) -> tuple[list[dict], str]:
    """Run `pyguara studio ops` in a subprocess and split the streams.

    A subprocess, not `CliRunner`, because the thing under test is what
    lands on the real file descriptors -- pygame's import banner and the
    engine's logging both write to the process's stdout, and an in-process
    runner that swaps `sys.stdout` for a buffer would hide exactly the
    problem this is checking for.

    Args:
        project: The project directory.
        requests: The request objects to send.

    Returns:
        `(responses, stderr)`.
    """
    payload = "\n".join(json.dumps(request) for request in requests) + "\n"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyguara.cli",
            "studio",
            "ops",
            "--project",
            str(project),
        ],
        input=payload,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return [json.loads(line) for line in lines], completed.stderr


@pytest.mark.integration
class TestStdoutDiscipline:
    """Nothing but protocol on stdout."""

    def test_only_protocol_reaches_stdout(self, project: Path) -> None:
        """Every line must parse as JSON. pygame's banner and the boot
        logs would each fail this."""
        responses, _ = _ops(project, {"op": "scene_summary"})
        assert len(responses) == 1
        assert responses[0]["ok"] is True

    def test_the_banner_and_logs_go_to_stderr(self, project: Path) -> None:
        """Not discarded -- a person debugging a session needs them."""
        _, stderr = _ops(project, {"op": "scene_summary"})
        assert "pyguara studio ops ready" in stderr

    def test_several_requests_give_several_clean_lines(self, project: Path) -> None:
        responses, _ = _ops(
            project,
            {"op": "scene_summary", "id": 1},
            {"op": "list_components", "id": 2},
            {"op": "list_operations", "id": 3},
        )
        assert [response["id"] for response in responses] == [1, 2, 3]


@pytest.mark.integration
class TestOpsCommand:
    """Driving a real session from the shell."""

    def test_an_edit_applies_and_is_visible_afterwards(self, project: Path) -> None:
        responses, _ = _ops(
            project,
            {
                "op": "create_entity",
                "args": {
                    "entity_id": "hero",
                    "components": {"Transform": {"position": {"x": 1, "y": 2}}},
                },
            },
            {"op": "scene_summary"},
        )
        assert responses[0]["ok"] is True
        assert responses[1]["result"]["entity_count"] == 1

    def test_the_project_overview_sees_the_project(self, project: Path) -> None:
        """`--project` is what makes `project_overview` work at all."""
        responses, _ = _ops(project, {"op": "project_overview"})
        assert responses[0]["result"]["scenes"] == ["scenes/level_1.scene"]

    def test_a_bad_request_is_answered_not_fatal(self, project: Path) -> None:
        responses, _ = _ops(project, {"op": "nonsense"}, {"op": "scene_summary"})
        assert responses[0]["ok"] is False
        assert responses[1]["ok"] is True


class TestInstructionsCommand:
    """Writing and checking the instruction files."""

    def test_check_on_a_bare_project_reports_drift(self, project: Path) -> None:
        result = CliRunner().invoke(studio, ["instructions", "--check", str(project)])
        assert result.exit_code == 1
        assert "AGENTS.md: missing" in result.output

    def test_check_names_the_command_that_fixes_it(self, project: Path) -> None:
        result = CliRunner().invoke(studio, ["instructions", "--check", str(project)])
        assert "pyguara studio instructions" in result.output

    def test_writing_then_checking_is_clean(self, project: Path) -> None:
        runner = CliRunner()
        assert runner.invoke(studio, ["instructions", str(project)]).exit_code == 0

        result = runner.invoke(studio, ["instructions", "--check", str(project)])
        assert result.exit_code == 0
        assert "up to date" in result.output

    def test_writing_produces_every_file(self, project: Path) -> None:
        CliRunner().invoke(studio, ["instructions", str(project)])
        assert (project / "AGENTS.md").exists()
        assert (project / "CLAUDE.md").exists()
        assert (project / "GEMINI.md").exists()
        assert (project / ".cursor" / "rules" / "pyguara.mdc").exists()

    def test_a_second_write_reports_nothing_to_do(self, project: Path) -> None:
        runner = CliRunner()
        runner.invoke(studio, ["instructions", str(project)])
        result = runner.invoke(studio, ["instructions", str(project)])
        assert "Already up to date" in result.output

    def test_dry_run_writes_nothing(self, project: Path) -> None:
        result = CliRunner().invoke(studio, ["instructions", "--dry-run", str(project)])
        assert result.exit_code == 0
        assert "AGENTS.md" in result.output
        assert not (project / "AGENTS.md").exists()

    def test_no_shims_writes_only_the_canonical_file(self, project: Path) -> None:
        CliRunner().invoke(studio, ["instructions", "--no-shims", str(project)])
        assert (project / "AGENTS.md").exists()
        assert not (project / "CLAUDE.md").exists()

    def test_hand_written_content_is_preserved(self, project: Path) -> None:
        """The property that makes this safe to run on a real project."""
        (project / "CLAUDE.md").write_text(
            "# game\n\nDo NOT touch the collision layers: see #412.\n",
            encoding="utf-8",
        )
        CliRunner().invoke(studio, ["instructions", str(project)])

        content = (project / "CLAUDE.md").read_text(encoding="utf-8")
        assert "see #412" in content
        assert "@AGENTS.md" in content

    def test_the_generated_file_lists_real_components(self, project: Path) -> None:
        """The component vocabulary comes from the registry, which is
        empty until the engine's own components are registered."""
        CliRunner().invoke(studio, ["instructions", str(project)])
        content = (project / "AGENTS.md").read_text(encoding="utf-8")
        assert "`Transform`" in content
        assert "`Sprite`" in content


class TestCommandGroup:
    """Discoverability."""

    def test_the_group_lists_its_subcommands(self) -> None:
        result = CliRunner().invoke(studio, ["--help"])
        for name in ("instructions", "ops", "mcp"):
            assert name in result.output

    def test_it_is_registered_on_the_main_cli(self) -> None:
        """So `pyguara studio` works, not only `pyguara.cli.studio`."""
        from pyguara.cli import main

        result = CliRunner().invoke(main, ["--help"])
        assert "studio" in result.output

    def test_the_mode_choices_come_from_the_enum(self) -> None:
        """So a new approval mode cannot be added without the CLI
        offering it."""
        from pyguara.cli.studio import APPROVAL_CHOICES
        from pyguara.studio.session import ApprovalMode

        assert set(APPROVAL_CHOICES) == {mode.value for mode in ApprovalMode}

    def test_ops_help_shows_the_request_shape(self) -> None:
        result = CliRunner().invoke(studio, ["ops", "--help"])
        assert "JSON" in result.output


@pytest.mark.integration
class TestModuleInvocation:
    """`python -m pyguara.cli` has to work.

    The `if __name__ == "__main__"` block in `pyguara/cli/__init__.py`
    could never fire -- inside a package's `__init__`, `__name__` is
    `pyguara.cli` -- so the only way in was the installed console script,
    which a test, a CI step or a fresh checkout may not have on its PATH.
    """

    def test_the_module_is_executable(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "pyguara.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        assert completed.returncode == 0
        assert "studio" in completed.stdout

    def test_the_studio_group_is_reachable_that_way(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "pyguara.cli", "studio", "--help"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        assert completed.returncode == 0
        assert "instructions" in completed.stdout


class TestInstructionsPathHandling:
    """A relative project path is the most ordinary invocation there is."""

    def test_a_relative_project_path_works(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`write_instructions` builds its paths from the project root, so
        a relative `.` produced relative paths that `relative_to` on the
        resolved root then refused -- a crash in the success path, after
        the files had already been written."""
        monkeypatch.chdir(project)
        result = CliRunner().invoke(studio, ["instructions", "."])

        assert result.exit_code == 0, result.output
        assert "wrote AGENTS.md" in result.output

    def test_the_default_project_is_the_working_directory(
        self, project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(project)
        result = CliRunner().invoke(studio, ["instructions"])

        assert result.exit_code == 0, result.output
        assert (project / "AGENTS.md").exists()


class TestSummaryOption:
    """A project saying what it is."""

    def test_the_summary_replaces_the_default(self, project: Path) -> None:
        """The default describes a game built on the engine, which is
        wrong for the engine's own repository and for a library."""
        CliRunner().invoke(
            studio,
            ["instructions", str(project), "--summary", "A tower defence."],
        )

        content = (project / "AGENTS.md").read_text(encoding="utf-8")
        assert "A tower defence." in content
        assert "is a game built on the PyGuara engine" not in content

    def test_the_rest_is_still_discovered(self, project: Path) -> None:
        """Only the prose is replaced; commands and inventory are not."""
        CliRunner().invoke(
            studio,
            ["instructions", str(project), "--summary", "A tower defence."],
        )

        content = (project / "AGENTS.md").read_text(encoding="utf-8")
        assert "scenes/level_1.scene" in content
        assert "ruff check" in content

    def test_without_it_the_default_is_used(self, project: Path) -> None:
        CliRunner().invoke(studio, ["instructions", str(project)])
        content = (project / "AGENTS.md").read_text(encoding="utf-8")
        assert "built on the PyGuara engine" in content
