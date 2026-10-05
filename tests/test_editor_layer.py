"""`EditorLayer` lifecycle, world resolution and input routing.

Built with no renderer, which is the point of the split: the layer can run
real ImGui frames over a real world without a GL context anywhere.
"""

from __future__ import annotations

from typing import Any

import pytest

from pyguara.di.container import DIContainer
from pyguara.ecs.manager import EntityManager
from pyguara.events.input import KeyDownEvent, MouseMotionEvent
from pyguara.input import keys
from pyguara.scene.manager import SceneManager

pytest.importorskip("imgui_bundle")

from pyguara.editor.layer import EditorLayer, default_panels  # noqa: E402
from pyguara.editor.panels.base import EditorPanel, PanelContext  # noqa: E402


class RecordingPanel(EditorPanel):
    """A panel that records the contexts it was drawn with."""

    def __init__(self, title: str = "Recording") -> None:
        super().__init__(title)
        self.contexts: list[PanelContext] = []

    def draw(self, context: PanelContext) -> None:
        self.contexts.append(context)


class _FakeScene:
    def __init__(self, entity_manager: EntityManager) -> None:
        self.entity_manager = entity_manager


class _FakeSceneManager:
    def __init__(self, scene: Any = None) -> None:
        self.current_scene = scene


@pytest.fixture
def container() -> DIContainer:
    """A container with no scene manager at all."""
    return DIContainer()


@pytest.fixture
def world() -> EntityManager:
    manager = EntityManager()
    manager.create_entity("alpha")
    return manager


def _layer(container: DIContainer, panels: list[EditorPanel] | None = None):
    """Build a renderer-less layer, so no GL is involved."""
    return EditorLayer(container, renderer_factory=None, panels=panels)


@pytest.mark.unit
class TestFrameBuilding:
    def test_it_builds_a_frame_with_the_default_panels(
        self, container: DIContainer
    ) -> None:
        layer = _layer(container)
        try:
            layer.build_frame(1280, 720, dt=1 / 60)
            draw_data = layer.build_frame(1280, 720, dt=1 / 60)
            assert draw_data.total_vtx_count > 0
        finally:
            layer.release()

    def test_default_panels_are_hierarchy_and_inspector(self) -> None:
        assert [panel.title for panel in default_panels()] == [
            "Hierarchy",
            "Inspector",
        ]

    def test_a_hidden_panel_is_not_drawn(self, container: DIContainer) -> None:
        panel = RecordingPanel()
        panel.visible = False
        layer = _layer(container, [panel])
        try:
            layer.build_frame(800, 600, dt=1 / 60)
            assert panel.contexts == []
        finally:
            layer.release()

    def test_render_does_nothing_while_hidden(self, container: DIContainer) -> None:
        panel = RecordingPanel()
        layer = _layer(container, [panel])
        try:
            layer.toggle()
            assert layer.visible is False
            layer.render(800, 600, dt=1 / 60)
            assert panel.contexts == []
        finally:
            layer.release()

    def test_a_zero_sized_target_is_skipped(self, container: DIContainer) -> None:
        """A minimised window reports 0x0, and ImGui asserts on it."""
        panel = RecordingPanel()
        layer = _layer(container, [panel])
        try:
            layer.render(0, 0, dt=1 / 60)
            assert panel.contexts == []
        finally:
            layer.release()

    def test_a_measured_dt_is_positive(self, container: DIContainer) -> None:
        """`BaseRenderPass.execute` is handed no delta time, so the layer
        measures its own -- and ImGui asserts on a non-positive one."""
        layer = _layer(container)
        try:
            layer.build_frame(800, 600)
            layer.build_frame(800, 600)
        finally:
            layer.release()

    def test_an_added_panel_is_drawn(self, container: DIContainer) -> None:
        layer = _layer(container, [])
        panel = RecordingPanel()
        try:
            layer.add_panel(panel)
            layer.build_frame(800, 600, dt=1 / 60)
            assert len(panel.contexts) == 1
        finally:
            layer.release()


@pytest.mark.unit
class TestWorldResolution:
    def test_no_scene_manager_yields_no_world(self, container: DIContainer) -> None:
        panel = RecordingPanel()
        layer = _layer(container, [panel])
        try:
            layer.build_frame(800, 600, dt=1 / 60)
            assert panel.contexts[-1].entity_manager is None
        finally:
            layer.release()

    def test_no_active_scene_yields_no_world(self, container: DIContainer) -> None:
        container.register_instance(SceneManager, _FakeSceneManager(None))
        panel = RecordingPanel()
        layer = _layer(container, [panel])
        try:
            layer.build_frame(800, 600, dt=1 / 60)
            assert panel.contexts[-1].entity_manager is None
        finally:
            layer.release()

    def test_the_active_scene_world_is_passed_through(
        self, container: DIContainer, world: EntityManager
    ) -> None:
        container.register_instance(SceneManager, _FakeSceneManager(_FakeScene(world)))
        panel = RecordingPanel()
        layer = _layer(container, [panel])
        try:
            layer.build_frame(800, 600, dt=1 / 60)
            assert panel.contexts[-1].entity_manager is world
        finally:
            layer.release()

    def test_a_scene_switch_is_picked_up_without_a_restart(
        self, container: DIContainer, world: EntityManager
    ) -> None:
        """Each scene owns its own `EntityManager` -- there is no global one
        -- so the layer must re-resolve every frame rather than cache."""
        scene_manager = _FakeSceneManager(_FakeScene(world))
        container.register_instance(SceneManager, scene_manager)
        panel = RecordingPanel()
        layer = _layer(container, [panel])
        try:
            layer.build_frame(800, 600, dt=1 / 60)

            second_world = EntityManager()
            scene_manager.current_scene = _FakeScene(second_world)
            layer.build_frame(800, 600, dt=1 / 60)

            assert panel.contexts[0].entity_manager is world
            assert panel.contexts[1].entity_manager is second_world
        finally:
            layer.release()


@pytest.mark.unit
class TestInputRouting:
    def test_events_are_ignored_while_hidden(self, container: DIContainer) -> None:
        layer = _layer(container)
        try:
            layer.toggle()
            consumed = layer.process_event(MouseMotionEvent(x=1, y=1, rel_x=0, rel_y=0))
            assert consumed is False
        finally:
            layer.release()

    def test_an_event_outside_any_window_is_not_consumed(
        self, container: DIContainer
    ) -> None:
        layer = _layer(container)
        try:
            layer.build_frame(1280, 720, dt=1 / 60)
            consumed = layer.process_event(
                MouseMotionEvent(x=1270, y=710, rel_x=0, rel_y=0)
            )
            assert consumed is False
        finally:
            layer.release()

    def test_a_foreign_event_type_is_never_consumed(
        self, container: DIContainer
    ) -> None:
        layer = _layer(container)
        try:
            layer.build_frame(800, 600, dt=1 / 60)
            assert layer.process_event(object()) is False
        finally:
            layer.release()

    def test_a_key_event_is_routed_without_raising(
        self, container: DIContainer
    ) -> None:
        layer = _layer(container)
        try:
            layer.build_frame(800, 600, dt=1 / 60)
            assert isinstance(layer.process_event(KeyDownEvent(key_code=keys.A)), bool)
        finally:
            layer.release()


@pytest.mark.unit
class TestLifecycle:
    def test_release_is_idempotent(self, container: DIContainer) -> None:
        layer = _layer(container)
        layer.release()
        layer.release()

    def test_two_layers_do_not_share_a_context(self, container: DIContainer) -> None:
        """Each layer owns its ImGui context and makes it current before
        touching IO, so the second cannot swallow the first's frames."""
        first_panel = RecordingPanel("first")
        second_panel = RecordingPanel("second")
        first = _layer(container, [first_panel])
        second = _layer(container, [second_panel])
        try:
            first.build_frame(800, 600, dt=1 / 60)
            second.build_frame(640, 480, dt=1 / 60)
            assert len(first_panel.contexts) == 1
            assert len(second_panel.contexts) == 1
        finally:
            second.release()
            first.release()

    def test_the_selection_is_shared_with_the_panels(
        self, container: DIContainer, world: EntityManager
    ) -> None:
        container.register_instance(SceneManager, _FakeSceneManager(_FakeScene(world)))
        panel = RecordingPanel()
        layer = _layer(container, [panel])
        try:
            layer.selection.select("alpha")
            layer.build_frame(800, 600, dt=1 / 60)
            assert panel.contexts[-1].selection.entity_id == "alpha"
        finally:
            layer.release()
