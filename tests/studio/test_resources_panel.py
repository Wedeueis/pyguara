"""The Resources panel, over real ImGui frames and a real resource manager.

What is checked is that the panel is only a caller of the `resources`
operation: a spawn it makes is on the history, a failure it meets is on
screen, and it does not re-read the whole index every frame.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("imgui_bundle")

from imgui_bundle import imgui  # noqa: E402

from pyguara.ecs.manager import EntityManager  # noqa: E402
from pyguara.resources.loaders.data_loader import JsonLoader  # noqa: E402
from pyguara.resources.manager import ResourceManager  # noqa: E402
from pyguara.studio.agent.journal import Actor  # noqa: E402
from pyguara.studio.panels.base import PanelContext  # noqa: E402
from pyguara.studio.panels.resources import (  # noqa: E402
    MAX_PREVIEW_CHARS,
    REFRESH_FRAMES,
    ResourcesPanel,
    preview_lines,
)
from pyguara.studio.selection import Selection  # noqa: E402
from pyguara.studio.session import StudioSession  # noqa: E402


class Toasts:
    """Collects what a panel reports."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def push(self, message: str, level: object) -> None:
        self.messages.append((getattr(level, "value", str(level)), message))


class CountingRegistry:
    """An operation registry that counts the calls passed through it."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.calls: list[str] = []

    def invoke(self, session, name, arguments, *, actor):
        self.calls.append(arguments["operation"])
        return self._inner.invoke(session, name, arguments, actor=actor)


@pytest.fixture
def gui() -> Iterator[None]:
    """An ImGui context with no renderer and no GL."""
    context = imgui.create_context()
    imgui.set_current_context(context)
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1280, 720)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    io.set_ini_filename("")
    yield
    imgui.destroy_context(context)


@pytest.fixture
def assets(tmp_path: Path) -> Path:
    """Two data files: one that spawns, one that does not."""
    root = tmp_path / "assets"
    root.mkdir()
    (root / "crate.json").write_text(
        json.dumps({"Transform": {}, "notes": "x"}), encoding="utf-8"
    )
    (root / "tuning.json").write_text(json.dumps({"speed": 3}), encoding="utf-8")
    return root


@pytest.fixture
def attachment(populated: EntityManager, core_registry, assets, ops):
    """What the panel needs of a `StudioAttachment`."""
    manager = ResourceManager()
    manager.register_loader(JsonLoader())
    manager.index_directory(str(assets))
    session = StudioSession(
        populated, component_registry=core_registry, resource_manager=manager
    )
    return SimpleNamespace(session=session, operations=CountingRegistry(ops))


@pytest.fixture
def panel(attachment) -> ResourcesPanel:
    """A visible panel whose reports are collected."""
    panel = ResourcesPanel(attachment, visible=True)
    panel.toasts = Toasts()
    return panel


def draw(panel: ResourcesPanel, *, frames: int = 2) -> int:
    """Draw the panel for several frames and return the vertex count."""
    context = PanelContext(entity_manager=None, selection=Selection())
    total = 0
    for _ in range(frames):
        imgui.new_frame()
        imgui.set_next_window_pos(imgui.ImVec2(0, 0))
        imgui.set_next_window_size(imgui.ImVec2(700, 600))
        panel.draw(context)
        imgui.render()
        total = imgui.get_draw_data().total_vtx_count
    return total


class TestDrawing:
    """It draws whatever there is to browse."""

    def test_it_draws_the_lists(self, gui: None, panel: ResourcesPanel) -> None:
        assert draw(panel) > 0

    def test_a_selection_adds_the_actions_and_the_preview(
        self, gui: None, panel: ResourcesPanel, assets: Path
    ) -> None:
        bare = draw(panel)
        panel.select(str(assets / "crate.json"))
        assert draw(panel) > bare

    def test_it_draws_without_a_session(self, gui: None, ops) -> None:
        panel = ResourcesPanel(
            SimpleNamespace(session=None, operations=ops), visible=True
        )
        assert draw(panel) > 0

    def test_it_draws_without_a_resource_manager(
        self, gui: None, ops, populated: EntityManager, core_registry
    ) -> None:
        bare = StudioSession(populated, component_registry=core_registry)
        panel = ResourcesPanel(
            SimpleNamespace(session=bare, operations=ops), visible=True
        )
        assert draw(panel) > 0

    def test_it_is_hidden_until_asked_for(self, attachment) -> None:
        assert ResourcesPanel(attachment).visible is False


class TestTheListingIsNotReadEveryFrame:
    """Listing sorts the whole index, which a frame should not pay for."""

    def test_one_listing_serves_many_frames(
        self, gui: None, panel: ResourcesPanel, attachment
    ) -> None:
        draw(panel, frames=REFRESH_FRAMES)
        assert attachment.operations.calls.count("list") == 1

    def test_it_is_read_again_when_it_is_due(
        self, gui: None, panel: ResourcesPanel, attachment
    ) -> None:
        draw(panel, frames=REFRESH_FRAMES + 1)
        assert attachment.operations.calls.count("list") == 2

    def test_a_changed_filter_reads_it_at_once(
        self, gui: None, panel: ResourcesPanel, attachment
    ) -> None:
        draw(panel, frames=2)
        panel._filter = "crate"
        draw(panel, frames=2)
        assert attachment.operations.calls.count("list") == 2
        assert [Path(e["path"]).name for e in panel._listing["indexed"]] == [
            "crate.json"
        ]


class TestSelecting:
    """A selection is previewed through the operation."""

    def test_a_data_file_is_previewed(
        self, panel: ResourcesPanel, assets: Path
    ) -> None:
        panel.select(str(assets / "tuning.json"))
        assert panel.selected == str(assets / "tuning.json")
        assert panel.preview["data"] == {"speed": 3}

    def test_a_failed_preview_is_kept_to_show(
        self, panel: ResourcesPanel, assets: Path
    ) -> None:
        panel.select(str(assets / "gone.json"))
        assert "gone.json" in panel.preview["error"]
        assert preview_lines(panel.preview) == [panel.preview["error"]]


class TestSpawning:
    """Spawn into Scene."""

    def test_it_creates_the_entity_on_the_history(
        self, panel: ResourcesPanel, attachment, assets: Path
    ) -> None:
        panel.select(str(assets / "crate.json"))
        panel.spawn()
        session = attachment.session
        assert session.world.get_entity("crate") is not None
        assert session.stack.can_undo
        assert session.journal.entries[-1].actor is Actor.HUMAN

    def test_it_says_what_it_made_and_what_it_skipped(
        self, panel: ResourcesPanel, assets: Path
    ) -> None:
        panel.select(str(assets / "crate.json"))
        panel.spawn()
        assert panel.toasts.messages[-1] == (
            "info",
            "Spawned crate (not components: notes)",
        )

    def test_a_refusal_is_reported_on_screen(
        self, panel: ResourcesPanel, assets: Path
    ) -> None:
        panel.select(str(assets / "tuning.json"))
        panel.spawn()
        level, message = panel.toasts.messages[-1]
        assert level == "error"
        assert "speed" in message

    def test_nothing_selected_does_nothing(
        self, panel: ResourcesPanel, attachment
    ) -> None:
        panel.spawn()
        panel.reload()
        assert attachment.operations.calls == []
        assert panel.toasts.messages == []


class TestReloading:
    """Reload."""

    def test_the_preview_follows_the_file(
        self, panel: ResourcesPanel, assets: Path
    ) -> None:
        path = assets / "tuning.json"
        panel.select(str(path))
        path.write_text(json.dumps({"speed": 9}), encoding="utf-8")
        panel.reload()
        assert panel.preview["data"] == {"speed": 9}
        assert panel.toasts.messages[-1] == ("info", f"Reloaded {path}")

    def test_a_failed_reload_is_reported(
        self, panel: ResourcesPanel, assets: Path
    ) -> None:
        path = assets / "tuning.json"
        panel.select(str(path))
        path.write_text("{", encoding="utf-8")
        panel.reload()
        assert panel.toasts.messages[-1][0] == "error"


class TestPreviewLines:
    """What the preview area shows."""

    def test_nothing_selected_shows_nothing(self) -> None:
        assert preview_lines(None) == []

    def test_an_unloaded_resource_says_so(self) -> None:
        assert preview_lines({"path": "a.png", "loaded": False}) == ["Not loaded."]

    def test_a_loaded_texture_shows_its_type_and_size(self) -> None:
        lines = preview_lines(
            {"path": "a.png", "loaded": True, "type": "Texture", "bytes": 64}
        )
        assert lines == ["Texture, 64 bytes"]

    def test_long_data_is_cut_and_says_by_how_much(self) -> None:
        preview = {
            "path": "big.json",
            "loaded": True,
            "type": "DataResource",
            "bytes": 1,
            "data": {"text": "x" * (MAX_PREVIEW_CHARS * 2)},
        }
        body = preview_lines(preview)[1]
        assert body.endswith("more characters")
        assert len(body) < MAX_PREVIEW_CHARS + 60
