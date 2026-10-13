"""The dock layout is responsive, and it is remembered.

Two things that used to be hand-rolled and should not have been.

The layout was rebuilt from scratch -- `dock_builder_remove_node` and a
fresh set of splits -- every time the window changed size. ImGui's dockspace
already keeps each node's share of its parent and rescales when the root
changes, which is the behaviour wanted; rebuilding threw away every splitter
the developer had dragged, on every resize.

And nothing was remembered between runs, so an authoring tool re-arranged
itself every morning. ImGui's own settings file stores each window's dock
node, size and collapsed state and restores them by title; writing a second
one on top of it would be a worse version of something that works.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pyguara.di.container import DIContainer

pytest.importorskip("imgui_bundle")

from imgui_bundle import imgui  # noqa: E402

from pyguara.editor.layer import DockLayout, EditorLayer  # noqa: E402
from pyguara.editor.panels.base import EditorPanel, PanelContext  # noqa: E402


class StubPanel(EditorPanel):
    """A panel that draws a window and nothing else."""

    def draw(self, context: PanelContext) -> None:
        if imgui.begin(self.title)[0]:
            imgui.text(self.title)
        imgui.end()


def _layout() -> DockLayout:
    return DockLayout(
        left=("Left",),
        right=("Right",),
        bottom=("Bottom",),
        centre=("Centre",),
        top_ratio=0.1,
    )


def _layer(settings: Path | None = None) -> EditorLayer:
    """A renderer-less layer with four dockable panels."""
    panels: list[EditorPanel] = [
        StubPanel("Left"),
        StubPanel("Right"),
        StubPanel("Bottom"),
        StubPanel("Centre"),
    ]
    layer = EditorLayer(DIContainer(), renderer_factory=None, panels=panels)
    if settings is not None:
        layer.set_settings_file(settings)
    layer.set_default_layout(_layout())
    return layer


def _count_applies(layer: EditorLayer) -> list[int]:
    """Replace `_apply_layout` with a counting wrapper.

    Returns:
        A one-element list holding the call count.
    """
    calls = [0]
    original = layer._apply_layout

    def counted(*args: Any, **kwargs: Any) -> None:
        calls[0] += 1
        original(*args, **kwargs)

    layer._apply_layout = counted  # type: ignore[method-assign]
    return calls


def _node_width(title: str) -> float:
    """Return the width of the dock node a panel sits in.

    Args:
        title: The panel's window title.

    Returns:
        The node's width in pixels, or 0.0 when it is not docked.
    """
    window = imgui.internal.find_window_by_name(title)
    if window is None or window.dock_node is None:
        return 0.0
    return float(window.dock_node.size.x)


@pytest.mark.unit
class TestItIsBuiltOnce:
    def test_a_resize_does_not_rebuild_it(self) -> None:
        layer = _layer()
        try:
            layer.build_frame(1280, 720, dt=1 / 60)
            calls = _count_applies(layer)
            for width, height in ((1920, 1080), (2560, 1080), (3440, 1440)):
                layer.build_frame(width, height, dt=1 / 60)
            assert calls[0] == 0, (
                "the dock tree was rebuilt on resize, which discards every "
                "splitter the developer dragged"
            )
        finally:
            layer.release()

    def test_it_is_applied_on_the_first_frame(self) -> None:
        layer = _layer()
        calls = _count_applies(layer)
        try:
            layer.build_frame(1280, 720, dt=1 / 60)
            layer.build_frame(1280, 720, dt=1 / 60)
            assert calls[0] == 1
        finally:
            layer.release()

    def test_resetting_rebuilds_it(self) -> None:
        layer = _layer()
        try:
            layer.build_frame(1280, 720, dt=1 / 60)
            calls = _count_applies(layer)
            layer.set_default_layout(_layout(), force=True)
            layer.build_frame(1280, 720, dt=1 / 60)
            assert calls[0] == 1
        finally:
            layer.release()


@pytest.mark.unit
class TestTheCentreTakesTheSlack:
    """What ImGui does when the root grows, and what an editor wants.

    A side dock keeps the width it was given and the centre absorbs the
    difference -- the same as Godot, Unity and VS Code. Rebuilding the
    tree on every resize overrode that with a *percentage* of the window,
    which is how a 20% hierarchy panel becomes 688px wide on a 21:9
    display while the viewport is squeezed for no reason.
    """

    def test_a_side_panel_keeps_its_width(self) -> None:
        layer = _layer()
        try:
            for _ in range(3):
                layer.build_frame(1280, 720, dt=1 / 60)
            narrow = _node_width("Left")
            assert narrow > 0.0, "the panel never docked"

            for _ in range(3):
                layer.build_frame(2560, 1440, dt=1 / 60)

            assert _node_width("Left") == pytest.approx(narrow, abs=2.0)
        finally:
            layer.release()

    def test_the_centre_grows_by_the_whole_difference(self) -> None:
        layer = _layer()
        try:
            for _ in range(3):
                layer.build_frame(1280, 720, dt=1 / 60)
            narrow = _node_width("Centre")

            for _ in range(3):
                layer.build_frame(2560, 1440, dt=1 / 60)

            assert _node_width("Centre") == pytest.approx(narrow + 1280, abs=8.0), (
                "the extra width went somewhere other than the viewport"
            )
        finally:
            layer.release()

    def test_an_ultrawide_window_does_not_inflate_the_sides(self) -> None:
        """21:9 is where the old behaviour showed worst: every panel
        scaled with the window, so the hierarchy took a third of the
        screen and the text in it was clipped anyway."""
        layer = _layer()
        try:
            for _ in range(3):
                layer.build_frame(1280, 720, dt=1 / 60)
            sides = (_node_width("Left"), _node_width("Right"))

            for _ in range(3):
                layer.build_frame(3440, 1440, dt=1 / 60)

            assert (_node_width("Left"), _node_width("Right")) == pytest.approx(
                sides, abs=2.0
            )
            for title in ("Left", "Right", "Bottom", "Centre"):
                assert _node_width(title) > 0.0, f"{title} is not docked"
        finally:
            layer.release()


@pytest.mark.unit
class TestSettings:
    def test_nothing_is_written_by_default(self, tmp_path: Path) -> None:
        """The bare editor and every test want nothing on disk: a dev tool
        dropping an `imgui.ini` into the project root is a surprise."""
        layer = _layer()
        try:
            assert layer.settings_file is None
            layer.build_frame(1280, 720, dt=1 / 60)
        finally:
            layer.release()
        assert list(tmp_path.iterdir()) == []

    def test_the_arrangement_is_written_on_release(self, tmp_path: Path) -> None:
        path = tmp_path / ".pyguara" / "studio-layout.ini"
        layer = _layer(path)
        try:
            for _ in range(3):
                layer.build_frame(1280, 720, dt=1 / 60)
        finally:
            layer.release()

        assert path.exists()
        assert "Left" in path.read_text()

    def test_the_directory_is_created(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "deeper" / "studio-layout.ini"
        layer = _layer(path)
        try:
            layer.build_frame(1280, 720, dt=1 / 60)
        finally:
            layer.release()

        assert path.exists()

    def test_a_saved_arrangement_is_not_overwritten(self, tmp_path: Path) -> None:
        """The dock builder would replace what ImGui had just loaded, and
        with it every splitter dragged last session."""
        path = tmp_path / "studio-layout.ini"
        first = _layer(path)
        try:
            for _ in range(3):
                first.build_frame(1280, 720, dt=1 / 60)
        finally:
            first.release()

        second = _layer(path)
        assert second.settings_restored is True
        calls = _count_applies(second)
        try:
            for _ in range(3):
                second.build_frame(1280, 720, dt=1 / 60)
            assert calls[0] == 0
        finally:
            second.release()

    def test_a_first_run_still_gets_the_default(self, tmp_path: Path) -> None:
        layer = _layer(tmp_path / "studio-layout.ini")
        assert layer.settings_restored is False
        calls = _count_applies(layer)
        try:
            layer.build_frame(1280, 720, dt=1 / 60)
            assert calls[0] == 1
        finally:
            layer.release()

    def test_reset_discards_a_saved_arrangement(self, tmp_path: Path) -> None:
        """The one action that is meant to."""
        path = tmp_path / "studio-layout.ini"
        first = _layer(path)
        try:
            for _ in range(3):
                first.build_frame(1280, 720, dt=1 / 60)
        finally:
            first.release()

        second = _layer(path)
        calls = _count_applies(second)
        try:
            second.build_frame(1280, 720, dt=1 / 60)
            second.set_default_layout(_layout(), force=True)
            second.build_frame(1280, 720, dt=1 / 60)
            assert calls[0] == 1
        finally:
            second.release()

    def test_turning_it_off_stops_writing(self, tmp_path: Path) -> None:
        path = tmp_path / "studio-layout.ini"
        layer = _layer(path)
        try:
            layer.build_frame(1280, 720, dt=1 / 60)
            layer.set_settings_file(None)
            assert layer.settings_file is None
        finally:
            layer.release()

        assert not path.exists()
