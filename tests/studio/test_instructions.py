"""Generating the instruction files coding agents read.

Most of these tests are about one property: **nothing outside the
generated markers is ever touched**. An instruction file is mostly
hand-written knowledge -- why a system is the way it is, what broke last
time -- and a generator that overwrites it is a generator nobody runs
twice. Everything else here is downstream of that.

The rest pin the facts about the tool landscape that the shims depend on,
because they are the kind of thing that looks like an arbitrary choice six
months later: Claude Code reads `CLAUDE.md` and never merges it with
`AGENTS.md`, Cursor uses the `.mdc` rules directory, Gemini CLI uses its
own file, and Codex truncates at 32 KiB.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyguara.prefabs.registry import ComponentRegistry
from pyguara.studio.agent.instructions import (
    AGENTS_FILE,
    BEGIN_MARKER,
    CODEX_BUDGET,
    CURSOR_RULE_PATH,
    END_MARKER,
    ProjectFacts,
    ShimKind,
    build_instructions,
    check_instructions,
    discover_facts,
    extract_generated,
    merge_generated,
    write_instructions,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project tree with content, tests and a configured toolchain."""
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "level_1.scene").write_text("{}", encoding="utf-8")
    (tmp_path / "prefabs").mkdir()
    (tmp_path / "prefabs" / "goblin.prefab.json").write_text("{}", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "hero.png").write_bytes(b"")
    (tmp_path / "tests").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\n[tool.mypy]\n", encoding="utf-8"
    )
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    return tmp_path


class TestMergeGenerated:
    """The property everything else rests on."""

    def test_a_new_file_gets_a_header_and_the_block(self) -> None:
        merged = merge_generated(None, "body", header="# Title")
        assert merged.startswith("# Title")
        assert BEGIN_MARKER in merged
        assert "body" in merged
        assert merged.rstrip().endswith(END_MARKER)

    def test_an_existing_block_is_replaced_in_place(self) -> None:
        first = merge_generated(None, "old body", header="# Title")
        second = merge_generated(first, "new body")

        assert "new body" in second
        assert "old body" not in second
        assert second.count(BEGIN_MARKER) == 1

    def test_text_before_the_block_survives(self) -> None:
        existing = f"# Mine\n\nKeep me.\n\n{BEGIN_MARKER}\nold\n{END_MARKER}\n"
        merged = merge_generated(existing, "new")
        assert "Keep me." in merged

    def test_text_after_the_block_survives(self) -> None:
        existing = f"{BEGIN_MARKER}\nold\n{END_MARKER}\n\n## Mine\n\nKeep me too.\n"
        merged = merge_generated(existing, "new")
        assert "Keep me too." in merged
        assert "new" in merged

    def test_a_file_without_markers_is_appended_to_not_replaced(self) -> None:
        """The case that matters most: a project with a long hand-written
        CLAUDE.md that has never seen this generator."""
        existing = "# my_game\n\nDo NOT touch the collision layers: see #412.\n"
        merged = merge_generated(existing, "generated body")

        assert "Do NOT touch the collision layers: see #412." in merged
        assert "generated body" in merged
        assert merged.startswith(existing)

    def test_an_empty_file_is_treated_as_new(self) -> None:
        merged = merge_generated("   \n", "body", header="# Title")
        assert merged.startswith("# Title")

    def test_merging_is_idempotent(self) -> None:
        once = merge_generated(None, "body", header="# Title")
        twice = merge_generated(once, "body")
        assert once == twice

    def test_only_the_first_block_is_replaced(self) -> None:
        """A file that somehow has two blocks keeps the second rather than
        having them silently collapsed."""
        existing = (
            f"{BEGIN_MARKER}\nfirst\n{END_MARKER}\n"
            f"{BEGIN_MARKER}\nsecond\n{END_MARKER}\n"
        )
        merged = merge_generated(existing, "new")
        assert "new" in merged
        assert "second" in merged

    def test_a_body_containing_marker_like_text_is_not_confused(self) -> None:
        """The body is written from a project, which could contain
        anything."""
        merged = merge_generated(None, "a line mentioning BEGIN GENERATED")
        assert extract_generated(merged) == "a line mentioning BEGIN GENERATED"


class TestExtractGenerated:
    """Reading a block back."""

    def test_returns_the_block(self) -> None:
        content = merge_generated(None, "body", header="# Title")
        assert extract_generated(content) == "body"

    def test_returns_none_without_markers(self) -> None:
        assert extract_generated("# Just prose\n") is None

    def test_ignores_surrounding_text(self) -> None:
        content = f"before\n{BEGIN_MARKER}\nbody\n{END_MARKER}\nafter\n"
        assert extract_generated(content) == "body"


class TestBuildInstructions:
    """What gets produced."""

    def test_produces_the_canonical_file_and_three_shims(self, project: Path) -> None:
        instructions = build_instructions(project)
        paths = {file.path for file in instructions.files}
        assert paths == {
            AGENTS_FILE,
            "CLAUDE.md",
            "GEMINI.md",
            CURSOR_RULE_PATH,
        }

    def test_the_canonical_file_comes_first(self, project: Path) -> None:
        """So a caller writing only the first file writes the one that
        matters."""
        assert build_instructions(project).files[0].path == AGENTS_FILE

    def test_shims_are_selectable(self, project: Path) -> None:
        instructions = build_instructions(project, shims=(ShimKind.CLAUDE,))
        assert {file.path for file in instructions.files} == {
            AGENTS_FILE,
            "CLAUDE.md",
        }

    def test_no_shims_leaves_only_the_canonical_file(self, project: Path) -> None:
        instructions = build_instructions(project, shims=())
        assert len(instructions.files) == 1

    def test_a_file_is_not_a_project(self, tmp_path: Path) -> None:
        target = tmp_path / "file.txt"
        target.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="not a directory"):
            build_instructions(target)


class TestDiscoveredCommands:
    """Commands are taken from the tooling actually present."""

    def test_uv_is_used_when_there_is_a_lockfile(self, project: Path) -> None:
        """A command the project cannot run is worse than none: an agent
        will try it and spend a turn finding out."""
        facts = discover_facts(project)
        assert ("Run the tests", "uv run pytest") in facts.commands

    def test_plain_commands_without_uv(self, project: Path) -> None:
        (project / "uv.lock").unlink()
        facts = discover_facts(project)
        assert ("Run the tests", "pytest") in facts.commands

    def test_ruff_is_offered_when_configured(self, project: Path) -> None:
        assert any(
            "ruff check" in command for _, command in discover_facts(project).commands
        )

    def test_ruff_is_not_offered_when_unconfigured(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        assert not any(
            "ruff" in command for _, command in discover_facts(tmp_path).commands
        )

    def test_mypy_is_not_offered_when_unconfigured(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        assert not any(
            "mypy" in command for _, command in discover_facts(tmp_path).commands
        )

    def test_tests_are_not_offered_without_a_tests_directory(
        self, tmp_path: Path
    ) -> None:
        assert not any(
            "pytest" in command for _, command in discover_facts(tmp_path).commands
        )


class TestCanonicalContent:
    """What the generated prose says."""

    def test_names_the_commands(self, project: Path) -> None:
        body = build_instructions(project).files[0].content
        assert "uv run pytest" in body

    def test_carries_the_engine_conventions(self, project: Path) -> None:
        """Chosen by what trips a newcomer, not by what is
        architecturally interesting."""
        body = build_instructions(project).files[0].content
        assert "Components are data" in body
        assert "notify_component_changed" in body
        assert "ChildOf" in body

    def test_carries_the_project_inventory(self, project: Path) -> None:
        body = build_instructions(project).files[0].content
        assert "scenes/level_1.scene" in body
        assert "prefabs/goblin.prefab.json" in body

    def test_lists_the_registered_components(self, project: Path) -> None:
        registry = ComponentRegistry()
        from pyguara.common.components import Transform

        registry.register(Transform)
        body = build_instructions(project, registry=registry).files[0].content
        assert "`Transform`" in body

    def test_explains_both_studio_transports(self, project: Path) -> None:
        """The part an agent cannot discover: that the surface exists."""
        body = build_instructions(project).files[0].content
        assert "pyguara studio ops" in body
        assert "pyguara studio mcp" in body

    def test_states_the_working_rules(self, project: Path) -> None:
        body = build_instructions(project).files[0].content
        assert "component_schema" in body
        assert "project_overview" in body
        assert "ids survive undo" in body

    def test_a_custom_summary_replaces_the_default(self, project: Path) -> None:
        facts = ProjectFacts(name="my_game", summary="A roguelike about frogs.")
        body = build_instructions(project, facts=facts).files[0].content
        assert "A roguelike about frogs." in body

    def test_custom_conventions_are_included(self, project: Path) -> None:
        facts = ProjectFacts(
            name="my_game", conventions=("Never touch the collision layers.",)
        )
        body = build_instructions(project, facts=facts).files[0].content
        assert "Never touch the collision layers." in body


class TestShims:
    """One canonical file, thin per-tool pointers."""

    def test_the_claude_shim_imports_rather_than_copies(self, project: Path) -> None:
        """Claude Code reads `CLAUDE.md` and never merges it with
        `AGENTS.md` -- if both exist, `CLAUDE.md` wins outright. A copy
        would become a second source of truth that rots while appearing
        authoritative."""
        instructions = build_instructions(project)
        shim = instructions.file("CLAUDE.md")
        assert shim is not None
        assert "@AGENTS.md" in shim.content
        assert "Engine conventions" not in shim.content

    def test_the_claude_shim_explains_why_it_is_a_shim(self, project: Path) -> None:
        shim = build_instructions(project).file("CLAUDE.md")
        assert shim is not None
        assert "does not" in shim.content and "merge" in shim.content

    def test_the_gemini_shim_names_gemini(self, project: Path) -> None:
        shim = build_instructions(project).file("GEMINI.md")
        assert shim is not None
        assert "Gemini CLI" in shim.content
        assert "@AGENTS.md" in shim.content

    def test_the_cursor_rule_uses_the_mdc_directory_format(self, project: Path) -> None:
        """`.cursorrules` is legacy; the rules directory is current."""
        shim = build_instructions(project).file(CURSOR_RULE_PATH)
        assert shim is not None
        assert shim.path.startswith(".cursor/rules/")
        assert shim.path.endswith(".mdc")

    def test_the_cursor_rule_carries_frontmatter(self, project: Path) -> None:
        shim = build_instructions(project).file(CURSOR_RULE_PATH)
        assert shim is not None
        assert shim.content.startswith("---\n")
        assert "alwaysApply: true" in shim.content

    def test_no_override_file_is_ever_written(self, project: Path) -> None:
        """`AGENTS.override.md` is Codex's way for a person to override
        what this produces. Writing one would take that away."""
        paths = {file.path for file in build_instructions(project).files}
        assert not any("override" in path for path in paths)


class TestBudget:
    """Codex truncates at 32 KiB, silently."""

    def test_a_normal_project_is_well_under(self, project: Path) -> None:
        instructions = build_instructions(project)
        assert instructions.files[0].size < CODEX_BUDGET
        assert instructions.warnings == () or all(
            "bytes" not in warning for warning in instructions.warnings
        )

    def test_exceeding_the_budget_warns(self, project: Path) -> None:
        """Rather than letting a project discover it when an agent stops
        knowing the second half of its own conventions."""
        facts = ProjectFacts(name="big", summary="x" * 200)
        instructions = build_instructions(project, facts=facts, budget=100)
        assert any("over the 100-byte limit" in w for w in instructions.warnings)

    def test_the_warning_says_what_to_do(self, project: Path) -> None:
        facts = ProjectFacts(name="big", summary="x" * 200)
        instructions = build_instructions(project, facts=facts, budget=100)
        warning = next(w for w in instructions.warnings if "limit" in w)
        assert "nested AGENTS.md" in warning

    def test_an_empty_project_warns_about_having_no_content(
        self, tmp_path: Path
    ) -> None:
        instructions = build_instructions(tmp_path)
        assert any("No scenes or prefabs" in w for w in instructions.warnings)


class TestWriting:
    """Putting the files on disk."""

    def test_writes_every_file(self, project: Path) -> None:
        instructions = build_instructions(project)
        write_instructions(project, instructions)

        assert (project / AGENTS_FILE).exists()
        assert (project / "CLAUDE.md").exists()
        assert (project / CURSOR_RULE_PATH).exists()

    def test_creates_the_cursor_rules_directory(self, project: Path) -> None:
        write_instructions(project, build_instructions(project))
        assert (project / ".cursor" / "rules").is_dir()

    def test_a_second_write_touches_nothing(self, project: Path) -> None:
        """Which keeps it out of a git diff and out of a file watcher's
        way."""
        instructions = build_instructions(project)
        assert write_instructions(project, instructions)
        assert write_instructions(project, instructions) == ()

    def test_hand_written_content_survives_a_write(self, project: Path) -> None:
        """The case that matters most."""
        (project / "CLAUDE.md").write_text(
            "# my_game\n\nDo NOT touch the collision layers: see #412.\n",
            encoding="utf-8",
        )

        write_instructions(project, build_instructions(project))

        content = (project / "CLAUDE.md").read_text(encoding="utf-8")
        assert "Do NOT touch the collision layers: see #412." in content
        assert "@AGENTS.md" in content

    def test_hand_written_content_survives_regeneration(self, project: Path) -> None:
        write_instructions(project, build_instructions(project))

        agents = project / AGENTS_FILE
        agents.write_text(
            agents.read_text(encoding="utf-8") + "\n## Mine\n\nKeep me.\n",
            encoding="utf-8",
        )

        write_instructions(project, build_instructions(project))

        content = agents.read_text(encoding="utf-8")
        assert "Keep me." in content
        assert content.count(BEGIN_MARKER) == 1


class TestDriftCheck:
    """What a CI step runs."""

    def test_a_missing_file_is_drift(self, project: Path) -> None:
        drifts = check_instructions(project, build_instructions(project))
        assert {drift.path for drift in drifts} == {
            AGENTS_FILE,
            "CLAUDE.md",
            "GEMINI.md",
            CURSOR_RULE_PATH,
        }
        assert all(drift.reason == "missing" for drift in drifts)

    def test_nothing_drifts_after_writing(self, project: Path) -> None:
        instructions = build_instructions(project)
        write_instructions(project, instructions)
        assert check_instructions(project, instructions) == ()

    def test_a_stale_block_is_drift(self, project: Path) -> None:
        instructions = build_instructions(project)
        write_instructions(project, instructions)

        agents = project / AGENTS_FILE
        agents.write_text(
            agents.read_text(encoding="utf-8").replace("uv run pytest", "make test"),
            encoding="utf-8",
        )

        drifts = check_instructions(project, instructions)
        assert any(
            drift.path == AGENTS_FILE and "stale" in drift.reason for drift in drifts
        )

    def test_a_hand_edit_outside_the_block_is_not_drift(self, project: Path) -> None:
        """The point of the markers: hand edits are expected, not a
        failure to be corrected."""
        instructions = build_instructions(project)
        write_instructions(project, instructions)

        agents = project / AGENTS_FILE
        agents.write_text(
            agents.read_text(encoding="utf-8") + "\n## Mine\n\nKeep me.\n",
            encoding="utf-8",
        )

        assert check_instructions(project, instructions) == ()

    def test_a_file_with_no_block_is_drift_that_says_what_to_do(
        self, project: Path
    ) -> None:
        (project / AGENTS_FILE).write_text("# Mine only\n", encoding="utf-8")
        drifts = check_instructions(project, build_instructions(project))
        reason = next(drift.reason for drift in drifts if drift.path == AGENTS_FILE)
        assert "run the generator" in reason
