"""`studio.model.projectmap`: the inventory an agent reads first.

The game-content analogue of a coding agent's repository map. Two things
are being pinned: that it finds the right files without walking build
output, and that `to_markdown` honours its budget *honestly* -- a map that
claims to be complete when it was truncated is worse than a short one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyguara.prefabs.registry import ComponentRegistry
from pyguara.studio.model.projectmap import build_project_map


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A small project tree, including directories that must be skipped."""
    (tmp_path / "scenes").mkdir()
    (tmp_path / "scenes" / "level_1.scene").write_text("{}", encoding="utf-8")
    (tmp_path / "scenes" / "level_2.scene.json").write_text("{}", encoding="utf-8")

    (tmp_path / "prefabs").mkdir()
    (tmp_path / "prefabs" / "goblin.prefab.json").write_text("{}", encoding="utf-8")
    (tmp_path / "prefabs" / "chest.prefab.yaml").write_text("{}", encoding="utf-8")

    (tmp_path / "assets" / "textures").mkdir(parents=True)
    (tmp_path / "assets" / "textures" / "hero.png").write_bytes(b"")
    (tmp_path / "assets" / "textures" / "tree.png").write_bytes(b"")
    (tmp_path / "assets" / "sfx").mkdir()
    (tmp_path / "assets" / "sfx" / "hit.ogg").write_bytes(b"")

    (tmp_path / "main.py").write_text("", encoding="utf-8")

    # Must not be walked.
    for skipped in (".venv", "__pycache__", "dist", ".git"):
        (tmp_path / skipped).mkdir()
        (tmp_path / skipped / "decoy.scene").write_text("{}", encoding="utf-8")
        (tmp_path / skipped / "decoy.png").write_bytes(b"")

    return tmp_path


class TestDiscovery:
    """What the walk finds."""

    def test_finds_both_scene_spellings(self, project: Path) -> None:
        scenes = build_project_map(project).scenes
        assert scenes == ("scenes/level_1.scene", "scenes/level_2.scene.json")

    def test_finds_prefabs_in_every_supported_format(self, project: Path) -> None:
        prefabs = build_project_map(project).prefabs
        assert prefabs == ("prefabs/chest.prefab.yaml", "prefabs/goblin.prefab.json")

    def test_a_prefab_is_not_also_counted_as_a_scene(self, project: Path) -> None:
        """`.prefab.json` ends in `.json`, so order of checks matters."""
        project_map = build_project_map(project)
        assert not any("prefab" in scene for scene in project_map.scenes)

    def test_counts_assets_by_extension(self, project: Path) -> None:
        """Counts rather than names: what an agent needs up front is which
        *kinds* exist, and it can list names on demand."""
        assets = build_project_map(project).assets
        assert assets == {".png": 2, ".ogg": 1}

    def test_reports_the_total_asset_count(self, project: Path) -> None:
        assert build_project_map(project).asset_count == 3

    def test_records_where_things_were_found(self, project: Path) -> None:
        project_map = build_project_map(project)
        assert project_map.scene_directories == ("scenes",)
        assert project_map.asset_directories == (
            "assets/sfx",
            "assets/textures",
        )

    def test_skips_build_output_and_caches(self, project: Path) -> None:
        """A real project's `.venv` is most of the files on disk."""
        project_map = build_project_map(project)
        joined = " ".join(project_map.scenes)
        assert "decoy" not in joined
        assert project_map.assets.get(".png") == 2

    def test_listings_are_sorted(self, project: Path) -> None:
        """Read by a machine, so it has to be deterministic."""
        project_map = build_project_map(project)
        assert list(project_map.scenes) == sorted(project_map.scenes)

    def test_an_empty_project_maps_cleanly(self, tmp_path: Path) -> None:
        project_map = build_project_map(tmp_path)
        assert project_map.scenes == ()
        assert project_map.asset_count == 0

    def test_a_file_is_not_a_project(self, tmp_path: Path) -> None:
        target = tmp_path / "file.txt"
        target.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="not a directory"):
            build_project_map(target)


class TestComponents:
    """The registry half."""

    def test_lists_registered_components(self, project: Path) -> None:
        registry = ComponentRegistry()
        from pyguara.common.components import Tag, Transform

        registry.register(Tag)
        registry.register(Transform)

        assert build_project_map(project, registry=registry).components == (
            "Tag",
            "Transform",
        )

    def test_without_a_registry_the_list_is_empty(self, project: Path) -> None:
        """What a map built outside a running engine gets."""
        assert build_project_map(project).components == ()


class TestMarkdown:
    """Rendering, and the budget."""

    def test_includes_the_counts(self, project: Path) -> None:
        rendered = build_project_map(project).to_markdown()
        assert "- Scenes: 2" in rendered
        assert "- Prefabs: 2" in rendered
        assert "- Asset files: 3" in rendered

    def test_lists_the_scenes(self, project: Path) -> None:
        rendered = build_project_map(project).to_markdown()
        assert "scenes/level_1.scene" in rendered

    def test_lists_the_components_inline(self, project: Path) -> None:
        registry = ComponentRegistry()
        from pyguara.common.components import Tag

        registry.register(Tag)
        rendered = build_project_map(project, registry=registry).to_markdown()
        assert "`Tag`" in rendered

    def test_breaks_assets_down_by_extension(self, project: Path) -> None:
        rendered = build_project_map(project).to_markdown()
        assert "`.png`: 2" in rendered

    def test_stays_within_the_budget(self, project: Path) -> None:
        rendered = build_project_map(project).to_markdown(budget=220)
        assert len(rendered) <= 220

    def test_the_counts_survive_a_tiny_budget(self, project: Path) -> None:
        """The counts come first precisely so a small budget still
        produces something useful."""
        rendered = build_project_map(project).to_markdown(budget=300)
        assert "## Project contents" in rendered

    def test_truncation_is_announced(self, project: Path) -> None:
        """A map that lies about being complete is worse than a short
        one."""
        rendered = build_project_map(project).to_markdown(budget=320)
        assert "omitted to stay within" in rendered

    def test_a_generous_budget_omits_nothing(self, project: Path) -> None:
        rendered = build_project_map(project).to_markdown(budget=100_000)
        assert "omitted to stay within" not in rendered
        assert "## Assets" in rendered

    def test_a_section_is_never_cut_mid_list(self, project: Path) -> None:
        """Sections are emitted whole or not at all."""
        rendered = build_project_map(project).to_markdown(budget=420)
        for line in rendered.splitlines():
            assert not line.endswith("`") or line.count("`") % 2 == 0

    def test_a_non_positive_budget_is_refused(self, project: Path) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            build_project_map(project).to_markdown(budget=0)

    def test_empty_sections_are_omitted(self, tmp_path: Path) -> None:
        rendered = build_project_map(tmp_path).to_markdown()
        assert "## Scenes" not in rendered
        assert "## Project contents" in rendered

    def test_long_listings_are_capped_with_a_remainder(self, tmp_path: Path) -> None:
        (tmp_path / "scenes").mkdir()
        for index in range(60):
            (tmp_path / "scenes" / f"level_{index:03d}.scene").write_text(
                "{}", encoding="utf-8"
            )

        rendered = build_project_map(tmp_path).to_markdown(budget=100_000)
        assert "and 20 more" in rendered


class TestSerialization:
    """The dict form."""

    def test_carries_every_section(self, project: Path) -> None:
        data = build_project_map(project).to_dict()
        assert data["asset_count"] == 3
        assert len(data["scenes"]) == 2
        assert len(data["prefabs"]) == 2
        assert data["assets"][".png"] == 2


class TestBudgetEdges:
    """The note has to survive a tight budget, since that is when it
    matters most."""

    def test_room_is_reserved_for_the_note(self, project: Path) -> None:
        """A first attempt appended the note only if it happened to fit,
        so it vanished exactly when the budget was tightest.

        Room is now reserved up front, which is checked by finding a
        budget that fits the first section and the note but not the
        second section, and asserting both are present.
        """
        project_map = build_project_map(project)
        full = project_map.to_markdown(budget=100_000)
        counts_only = full.split("\n\n##")[0]
        note_allowance = 80

        rendered = project_map.to_markdown(budget=len(counts_only) + note_allowance)
        assert "## Project contents" in rendered
        assert "omitted to stay within" in rendered

    def test_content_wins_when_only_one_of_the_two_fits(self, project: Path) -> None:
        """At a budget that holds the first section or the note but not
        both, the section is the more useful half."""
        project_map = build_project_map(project)
        counts_only = project_map.to_markdown(budget=100_000).split("\n\n##")[0]

        rendered = project_map.to_markdown(budget=len(counts_only) + 2)
        assert "## Project contents" in rendered
        assert "omitted to stay within" not in rendered

    def test_still_within_budget_with_the_note(self, project: Path) -> None:
        project_map = build_project_map(project)
        for budget in range(60, 600, 7):
            rendered = project_map.to_markdown(budget=budget)
            assert len(rendered) <= budget, budget

    def test_a_budget_too_small_for_any_section_says_so(self, project: Path) -> None:
        """More use than an empty string: the caller is left knowing why,
        rather than wondering whether the project is empty."""
        rendered = build_project_map(project).to_markdown(budget=80)
        assert "does not fit in 80 characters" in rendered
        assert len(rendered) <= 80

    def test_an_absurd_budget_returns_nothing_rather_than_overrunning(
        self, project: Path
    ) -> None:
        assert build_project_map(project).to_markdown(budget=5) == ""
