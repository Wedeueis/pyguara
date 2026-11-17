"""The Config panel, over real ImGui frames.

The panel owns no state worth testing beyond its filter; what matters is
that every edit it accepts leaves through the `config` operation, and
that a refusal reaches the person instead of a log.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("imgui_bundle")

from imgui_bundle import imgui  # noqa: E402

from pyguara.common.types import Color  # noqa: E402
from pyguara.config.manager import ConfigManager  # noqa: E402
from pyguara.config.types import LogLevel  # noqa: E402
from pyguara.ecs.manager import EntityManager  # noqa: E402
from pyguara.studio.agent.journal import Actor  # noqa: E402
from pyguara.studio.panels.base import PanelContext  # noqa: E402
from pyguara.studio.panels.config import ConfigPanel  # noqa: E402
from pyguara.studio.selection import Selection  # noqa: E402
from pyguara.studio.session import StudioSession  # noqa: E402


class Toasts:
    """Collects what a panel reports."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def push(self, message: str, level: object) -> None:
        self.messages.append((getattr(level, "value", str(level)), message))


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
def manager(tmp_path: Path) -> ConfigManager:
    """A configuration at its defaults."""
    return ConfigManager(file_path=tmp_path / "game_config.json")


@pytest.fixture
def attachment(populated: EntityManager, core_registry, manager, ops):
    """What the panel needs of a `StudioAttachment`."""
    session = StudioSession(
        populated, component_registry=core_registry, config_manager=manager
    )
    return SimpleNamespace(session=session, operations=ops)


@pytest.fixture
def panel(attachment) -> ConfigPanel:
    """A visible panel whose reports are collected."""
    panel = ConfigPanel(attachment, visible=True)
    panel.toasts = Toasts()
    return panel


def draw(panel: ConfigPanel, *, frames: int = 2) -> int:
    """Draw the panel for several frames and return the vertex count."""
    context = PanelContext(entity_manager=None, selection=Selection())
    total = 0
    for _ in range(frames):
        imgui.new_frame()
        imgui.set_next_window_pos(imgui.ImVec2(0, 0))
        imgui.set_next_window_size(imgui.ImVec2(600, 700))
        panel.draw(context)
        imgui.render()
        total = imgui.get_draw_data().total_vtx_count
    return total


class TestDrawing:
    """It draws whatever state the configuration is in."""

    def test_it_draws_the_sections(self, gui: None, panel: ConfigPanel) -> None:
        assert draw(panel) > 0

    def test_every_setting_type_has_a_widget(
        self, gui: None, panel: ConfigPanel
    ) -> None:
        """A filter opens every matching section, so each widget arm runs."""
        collapsed = draw(panel)
        panel._filter = "e"
        assert draw(panel) > collapsed

    def test_a_pinned_setting_draws(
        self, gui: None, panel: ConfigPanel, manager: ConfigManager
    ) -> None:
        manager.define_profile("hard", {"physics": {"substeps": 9}})
        manager.push_profile("hard")
        panel._filter = "substeps"
        assert draw(panel) > 0

    def test_it_draws_without_a_session(self, gui: None, ops) -> None:
        panel = ConfigPanel(SimpleNamespace(session=None, operations=ops), visible=True)
        assert draw(panel) > 0

    def test_it_draws_without_a_configuration(
        self, gui: None, ops, populated: EntityManager, core_registry
    ) -> None:
        bare = StudioSession(populated, component_registry=core_registry)
        panel = ConfigPanel(SimpleNamespace(session=bare, operations=ops), visible=True)
        assert draw(panel) > 0

    def test_it_is_hidden_until_asked_for(self, attachment) -> None:
        assert ConfigPanel(attachment).visible is False


class TestWriting:
    """An accepted edit is the `config` operation."""

    def test_a_write_reaches_the_config_and_the_history(
        self, panel: ConfigPanel, attachment, manager: ConfigManager
    ) -> None:
        panel.write("physics", "substeps", 8)
        assert manager.config.physics.substeps == 8
        assert attachment.session.stack.undo_labels == ("Set config physics.substeps",)

    def test_it_is_attributed_to_the_person(
        self, panel: ConfigPanel, attachment
    ) -> None:
        panel.write("physics", "substeps", 8)
        assert attachment.session.journal.entries[-1].actor is Actor.HUMAN

    def test_an_enum_and_a_colour_cross_the_operation(
        self, panel: ConfigPanel, manager: ConfigManager
    ) -> None:
        panel.write("debug", "log_level", LogLevel.DEBUG)
        panel.write("display", "default_color", Color(9, 8, 7))
        assert manager.config.debug.log_level is LogLevel.DEBUG
        assert manager.config.display.default_color == Color(9, 8, 7)
        assert panel.toasts.messages == []

    def test_a_drag_is_one_history_entry(self, panel: ConfigPanel, attachment) -> None:
        for volume in (0.9, 0.8, 0.7):
            panel.write("audio", "master_volume", volume, coalesce=True)
        assert len(attachment.session.stack.undo_labels) == 1

    def test_a_refusal_is_reported_on_screen(
        self, panel: ConfigPanel, manager: ConfigManager
    ) -> None:
        panel.write("display", "screen_width", -5)
        assert manager.config.display.screen_width == 1200
        level, message = panel.toasts.messages[-1]
        assert level == "error"
        assert message.startswith("display.screen_width:")


class TestSaving:
    """The Save button."""

    def test_it_writes_the_file_and_says_so(
        self, panel: ConfigPanel, manager: ConfigManager
    ) -> None:
        panel.write("physics", "substeps", 8)
        panel.save()
        assert manager.file_path.exists()
        assert panel.toasts.messages[-1] == ("info", f"Saved {manager.file_path}")

    def test_a_failed_save_is_reported(
        self, panel: ConfigPanel, manager: ConfigManager, tmp_path: Path
    ) -> None:
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        manager._file_path = blocker / "game_config.json"
        panel.save()
        assert panel.toasts.messages[-1][0] == "error"
