"""What is in this project, compactly enough to read first.

The game-content analogue of the repository map that coding agents build
over source trees. An agent opening an unfamiliar PyGuara project needs to
know what scenes exist, what prefabs it can instance, which components are
registered and what the assets look like -- before it can usefully ask
anything else. Discovering that by listing directories costs a dozen tool
calls and arrives as unordered noise.

**Budgeted, deliberately.** Codex truncates an instruction file at 32 KiB
and every agent pays for context by the token, so `to_markdown()` takes a
character budget and spends it in priority order: the counts that orient a
reader first, the long file listings last, each section truncated with an
honest "+N more" rather than silently cut. A map that lies about being
complete is worse than a short one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyguara.log import get_logger
from pyguara.prefabs.registry import ComponentRegistry

logger = get_logger(__name__)

DEFAULT_BUDGET = 8000
"""Characters `to_markdown` will spend by default.

Well under Codex's 32 KiB instruction-file ceiling, because the map is one
section of a generated `AGENTS.md` rather than the whole of it.
"""

SCENE_SUFFIXES = (".scene", ".scene.json")
"""What a scene file is called. Both spellings are in use."""

PREFAB_SUFFIXES = (".prefab.json", ".prefab.yaml", ".prefab.yml")
"""What a prefab file is called, per `PrefabLoader.supported_extensions`."""

# Directories never worth walking: build output, caches, virtualenvs and
# the editor's own scratch space. Checked by name at every level, so a
# nested `__pycache__` is skipped as readily as a top-level one.
_SKIP_DIRECTORIES = frozenset(
    {
        ".agent-view",
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".scratch",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "site",
        "venv",
    }
)

# How many entries each listing shows before it says "+N more".
_LIST_CAP = 40


@dataclass(frozen=True)
class ProjectMap:
    """An inventory of a project's authored content.

    Attributes:
        root: The project directory this was built from.
        scenes: Scene files, as paths relative to `root`.
        prefabs: Prefab files, relative to `root`.
        components: Registered component names.
        assets: Asset file extension to how many there are.
        scene_directories: Where scenes were found, relative to `root`.
        asset_directories: Where assets were found, relative to `root`.
    """

    root: Path
    scenes: tuple[str, ...] = ()
    prefabs: tuple[str, ...] = ()
    components: tuple[str, ...] = ()
    assets: dict[str, int] = field(default_factory=dict)
    scene_directories: tuple[str, ...] = ()
    asset_directories: tuple[str, ...] = ()

    @property
    def asset_count(self) -> int:
        """How many asset files were found in total."""
        return sum(self.assets.values())

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form.

        Returns:
            The map as a plain dict.
        """
        return {
            "root": str(self.root),
            "scenes": list(self.scenes),
            "prefabs": list(self.prefabs),
            "components": list(self.components),
            "assets": dict(self.assets),
            "asset_count": self.asset_count,
            "scene_directories": list(self.scene_directories),
            "asset_directories": list(self.asset_directories),
        }

    def to_markdown(self, budget: int = DEFAULT_BUDGET) -> str:
        """Render the map as Markdown, within `budget` characters.

        Sections are emitted in priority order, whole or not at all -- a
        listing cut mid-item reads as a shorter list rather than a
        truncated one. When anything is left out the document says so, and
        says how much. A map that claims to be complete when it was
        truncated is worse than a short one.

        The counts section comes first precisely so that a budget too
        small for anything else still produces something useful.

        Args:
            budget: Characters to spend. Must be positive.

        Returns:
            The Markdown.

        Raises:
            ValueError: If `budget` is not positive.
        """
        if budget <= 0:
            raise ValueError(f"budget must be positive, got {budget}")

        sections: list[str] = [self._counts_section()]
        for section in (
            self._components_section(),
            self._scenes_section(),
            self._prefabs_section(),
            self._assets_section(),
        ):
            if section:
                sections.append(section)

        rendered, omitted = self._fill(sections, budget, reserve=0)
        if not omitted:
            return rendered

        if rendered:
            # Something was left out, so the note has to fit. Re-fill with
            # room reserved for it rather than appending and overrunning --
            # or, as a first attempt did, appending only when it happened
            # to fit, which silently dropped the note exactly when the
            # budget was tightest and the warning mattered most.
            note = _omission_note(omitted, budget)
            refilled, refilled_omitted = self._fill(sections, budget, reserve=len(note))
            if refilled and refilled_omitted:
                note = _omission_note(refilled_omitted, budget)
                if len(refilled) + len(note) <= budget:
                    return refilled + note
            # Reserving pushed out every section, or the note still will
            # not fit. Content beats the apology about it.
            return rendered

        # Not even the first section fits. Sections are emitted whole, so
        # there is nothing to return but a statement of that -- which is
        # more use than an empty string, since the caller is left knowing
        # why rather than wondering whether the project is empty.
        too_small = (
            f"_A project map does not fit in {budget} characters; "
            f"{len(sections)} section(s) omitted._"
        )
        return too_small if len(too_small) <= budget else ""

    @staticmethod
    def _fill(sections: list[str], budget: int, *, reserve: int) -> tuple[str, int]:
        """Join as many whole sections as fit, and say how many did not.

        Args:
            sections: The sections, in priority order.
            budget: Total characters allowed.
            reserve: Characters to keep free at the end.

        Returns:
            `(rendered, omitted_count)`.
        """
        rendered = ""
        for index, section in enumerate(sections):
            candidate = section if not rendered else f"{rendered}\n\n{section}"
            if len(candidate) + reserve > budget:
                return rendered, len(sections) - index
            rendered = candidate
        return rendered, 0

    def _counts_section(self) -> str:
        """Render the orienting counts.

        Returns:
            A Markdown section.
        """
        lines = [
            "## Project contents",
            "",
            f"- Scenes: {len(self.scenes)}",
            f"- Prefabs: {len(self.prefabs)}",
            f"- Registered components: {len(self.components)}",
            f"- Asset files: {self.asset_count}",
        ]
        if self.scene_directories:
            lines.append(f"- Scene directories: {', '.join(self.scene_directories)}")
        if self.asset_directories:
            lines.append(f"- Asset directories: {', '.join(self.asset_directories)}")
        return "\n".join(lines)

    def _components_section(self) -> str:
        """Render the registered component names.

        Returns:
            A Markdown section, or "" when there are none.
        """
        if not self.components:
            return ""
        # Comma-separated rather than a bullet per name: this is the
        # longest list and the one where each entry is a single word.
        return "\n".join(
            [
                "## Registered components",
                "",
                "Attachable by name through the component registry.",
                "",
                _inline_list(self.components),
            ]
        )

    def _scenes_section(self) -> str:
        """Render the scene files.

        Returns:
            A Markdown section, or "" when there are none.
        """
        if not self.scenes:
            return ""
        return "\n".join(["## Scenes", "", _bullet_list(self.scenes)])

    def _prefabs_section(self) -> str:
        """Render the prefab files.

        Returns:
            A Markdown section, or "" when there are none.
        """
        if not self.prefabs:
            return ""
        return "\n".join(["## Prefabs", "", _bullet_list(self.prefabs)])

    def _assets_section(self) -> str:
        """Render the asset breakdown by extension.

        Counts rather than names: an asset directory holds hundreds of
        files whose individual names an agent can list on demand, and what
        it needs up front is which *kinds* exist.

        Returns:
            A Markdown section, or "" when there are none.
        """
        if not self.assets:
            return ""
        lines = ["## Assets", ""]
        for suffix, count in sorted(
            self.assets.items(), key=lambda item: (-item[1], item[0])
        ):
            lines.append(f"- `{suffix}`: {count}")
        return "\n".join(lines)


def build_project_map(
    root: Path,
    *,
    registry: ComponentRegistry | None = None,
    asset_suffixes: tuple[str, ...] = (
        ".png",
        ".jpg",
        ".jpeg",
        ".ogg",
        ".wav",
        ".ttf",
        ".tmx",
        ".tsx",
    ),
) -> ProjectMap:
    """Walk `root` and inventory what an agent would need to know.

    Args:
        root: The project directory.
        registry: The component registry to read names from. None leaves
            the component list empty, which is what a map built outside a
            running engine gets.
        asset_suffixes: Which file extensions count as assets.

    Returns:
        The map. An unreadable directory is skipped with a warning rather
        than failing the walk -- a project with one permission-denied
        folder still has a usable map.

    Raises:
        ValueError: If `root` is not a directory.
    """
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not a directory.")

    scenes: list[str] = []
    prefabs: list[str] = []
    assets: dict[str, int] = {}
    scene_directories: set[str] = set()
    asset_directories: set[str] = set()

    for path in _walk(root):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:  # pragma: no cover - _walk yields only descendants
            continue

        name = path.name.lower()
        parent = path.parent.relative_to(root).as_posix() or "."

        if name.endswith(PREFAB_SUFFIXES):
            prefabs.append(relative)
        elif name.endswith(SCENE_SUFFIXES):
            scenes.append(relative)
            scene_directories.add(parent)
        elif path.suffix.lower() in asset_suffixes:
            assets[path.suffix.lower()] = assets.get(path.suffix.lower(), 0) + 1
            asset_directories.add(parent)

    components = tuple(registry.list_components()) if registry is not None else ()

    return ProjectMap(
        root=root,
        scenes=tuple(sorted(scenes)),
        prefabs=tuple(sorted(prefabs)),
        components=components,
        assets=assets,
        scene_directories=tuple(sorted(scene_directories)),
        asset_directories=tuple(sorted(asset_directories)),
    )


def _walk(root: Path) -> list[Path]:
    """Return every file under `root`, skipping uninteresting directories.

    Hand-rolled rather than `Path.rglob`, so a skipped directory is not
    descended into at all. `rglob` would walk the whole of `.venv` and
    filter afterwards, which on a real project is most of the work.

    Args:
        root: The directory to walk.

    Returns:
        Every file found.
    """
    files: list[Path] = []
    stack = [root]
    while stack:
        directory = stack.pop()
        try:
            entries = list(directory.iterdir())
        except OSError as exc:
            logger.warning(f"Skipping {directory}: {exc}")
            continue

        for entry in entries:
            if entry.is_dir():
                if entry.name not in _SKIP_DIRECTORIES:
                    stack.append(entry)
            elif entry.is_file():
                files.append(entry)
    return files


def _omission_note(omitted: int, budget: int) -> str:
    """Render the trailing note that says what was left out.

    Args:
        omitted: How many sections were omitted.
        budget: The budget that forced it, named so a reader can raise it.

    Returns:
        The note, including its leading blank line.
    """
    return (
        f"\n\n_{omitted} further section(s) omitted to stay within a "
        f"{budget}-character budget._"
    )


def _bullet_list(items: tuple[str, ...], cap: int = _LIST_CAP) -> str:
    """Render items as a bullet list, capped with an honest remainder.

    Args:
        items: The items to list.
        cap: How many to show.

    Returns:
        The Markdown list.
    """
    shown = [f"- `{item}`" for item in items[:cap]]
    if len(items) > cap:
        shown.append(f"- _... and {len(items) - cap} more_")
    return "\n".join(shown)


def _inline_list(items: tuple[str, ...], cap: int = _LIST_CAP * 3) -> str:
    """Render items as one comma-separated line, capped.

    Args:
        items: The items to list.
        cap: How many to show.

    Returns:
        The Markdown line.
    """
    shown = ", ".join(f"`{item}`" for item in items[:cap])
    if len(items) > cap:
        shown += f", _... and {len(items) - cap} more_"
    return shown
