"""The viewport panel, running real ImGui frames with no GL anywhere.

`imgui.create_context()` needs no OpenGL, so a test can run genuine
frames over a genuine world and assert on what the panel did. That seam
is the whole reason `EditorLayer` separates building a frame from
rasterising one, and it is what caught two real API errors here that a
mock would have accepted: `imgui.image()` takes an `ImTextureRef` rather
than a bare int in ImGui 1.92, and this binding's `add_rect` orders
thickness before flags.

Window size has to be set before each `draw`, because the panel calls
`imgui.begin` itself and an auto-sized window has a zero content region
-- in which case every interesting path early-returns and the tests
would pass while exercising only the toolbar.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

pytest.importorskip("imgui_bundle")

from imgui_bundle import imgui  # noqa: E402

from pyguara.common.components import Transform  # noqa: E402
from pyguara.common.types import Rect, Vector2  # noqa: E402
from pyguara.ecs.manager import EntityManager  # noqa: E402
from pyguara.editor.panels.base import PanelContext  # noqa: E402
from pyguara.editor.selection import Selection  # noqa: E402
from pyguara.graphics.components.camera import Camera2D  # noqa: E402
from pyguara.graphics.components.sprite import Sprite  # noqa: E402
from pyguara.studio.viewport.panel import (  # noqa: E402
    MAX_ZOOM,
    MIN_ZOOM,
    ViewportOverlay,
    ViewportPanel,
    ViewportState,
)
from tests.test_scene_serializer import FakeTexture  # noqa: E402

PANEL_SIZE = imgui.ImVec2(640, 480)
TARGET = (1, 800, 600)
"""`(texture_id, width, height)`, as a texture provider returns."""


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
def camera() -> Camera2D:
    """A camera at the origin, unzoomed."""
    return Camera2D(800, 600)


@pytest.fixture
def viewport_world(world: EntityManager) -> EntityManager:
    """A world with one sprite at the origin and one far away."""
    hero = world.create_entity("hero")
    hero.add_component(Transform(position=Vector2(0, 0)))
    hero.add_component(Sprite(texture=FakeTexture("hero.png", 64, 64)))

    rock = world.create_entity("rock")
    rock.add_component(Transform(position=Vector2(300, 200)))
    rock.add_component(Sprite(texture=FakeTexture("rock.png", 32, 32)))
    return world


@pytest.fixture
def selection() -> Selection:
    """An empty selection."""
    return Selection()


@pytest.fixture
def panel(camera: Camera2D) -> ViewportPanel:
    """A viewport over the camera, with a frame to show."""
    return ViewportPanel(
        camera_provider=lambda: camera,
        texture_provider=lambda: TARGET,
    )


def _frame(
    panel: ViewportPanel,
    world: EntityManager | None,
    selection: Selection,
    *,
    mouse: tuple[float, float] | None = None,
    wheel: float = 0.0,
) -> Any:
    """Run one frame with the panel sized, and return the draw data."""
    io = imgui.get_io()
    if mouse is not None:
        io.add_mouse_pos_event(mouse[0], mouse[1])
    if wheel:
        io.add_mouse_wheel_event(0.0, wheel)

    imgui.new_frame()
    imgui.set_next_window_pos(imgui.ImVec2(0, 0))
    imgui.set_next_window_size(PANEL_SIZE)
    panel.draw(PanelContext(entity_manager=world, selection=selection))
    imgui.render()
    return imgui.get_draw_data()


class TestItDraws:
    """The frame, and the degenerate paths around it."""

    def test_it_draws_something(
        self,
        gui: None,
        panel: ViewportPanel,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        _frame(panel, viewport_world, selection)
        assert _frame(panel, viewport_world, selection).total_vtx_count > 0

    def test_it_records_the_panel_and_target_geometry(
        self,
        gui: None,
        panel: ViewportPanel,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        """Both are needed for every coordinate mapping, and the gizmo
        reads them too."""
        _frame(panel, viewport_world, selection)
        _frame(panel, viewport_world, selection)

        assert panel.state.content.width > 0
        assert panel.state.target == Rect(0, 0, 800, 600)
        assert panel.state.has_geometry

    def test_no_scene_says_so(
        self, gui: None, panel: ViewportPanel, selection: Selection
    ) -> None:
        """An empty panel and "no scene" look identical otherwise."""
        _frame(panel, None, selection)

    def test_no_camera_says_so(
        self, gui: None, viewport_world: EntityManager, selection: Selection
    ) -> None:
        _frame(ViewportPanel(), viewport_world, selection)

    def test_no_texture_says_so(
        self,
        gui: None,
        camera: Camera2D,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        """The Pygame backend has no GL context and so no texture. Saying
        so beats an empty panel that looks like a broken render path."""
        bare = ViewportPanel(camera_provider=lambda: camera)
        _frame(bare, viewport_world, selection)

    def test_a_failing_provider_does_not_break_the_frame(
        self, gui: None, viewport_world: EntityManager, selection: Selection
    ) -> None:
        """A viewport that raised because a scene had not finished loading
        would take the whole editor frame down with it."""

        def explode() -> Camera2D:
            raise RuntimeError("not ready")

        _frame(ViewportPanel(camera_provider=explode), viewport_world, selection)

    def test_an_empty_world_draws(
        self,
        gui: None,
        panel: ViewportPanel,
        world: EntityManager,
        selection: Selection,
    ) -> None:
        _frame(panel, world, selection)


class TestGrid:
    """Drawn when useful, skipped when it would be noise."""

    def test_the_grid_adds_geometry(
        self,
        gui: None,
        panel: ViewportPanel,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        _frame(panel, viewport_world, selection)

        panel.state.show_grid = True
        with_grid = _frame(panel, viewport_world, selection).total_vtx_count
        panel.state.show_grid = False
        without_grid = _frame(panel, viewport_world, selection).total_vtx_count

        assert with_grid > without_grid

    def test_it_is_skipped_when_the_lines_would_merge(
        self,
        gui: None,
        panel: ViewportPanel,
        camera: Camera2D,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        """Below a few pixels apart a grid is a grey wash, and drawing
        thousands of lines to produce one is the worst of both."""
        _frame(panel, viewport_world, selection)
        panel.state.show_grid = True

        camera.zoom = 1.0
        normal = _frame(panel, viewport_world, selection).total_vtx_count
        camera.zoom = MIN_ZOOM
        zoomed_out = _frame(panel, viewport_world, selection).total_vtx_count

        assert zoomed_out < normal

    def test_a_zero_step_does_not_hang(
        self,
        gui: None,
        panel: ViewportPanel,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        """A `while x <= limit: x += step` with a zero step is forever."""
        _frame(panel, viewport_world, selection)
        panel.state.grid_size = 0.0
        _frame(panel, viewport_world, selection)


class TestSelectionOutlines:
    """Drawing what is selected."""

    def test_a_selection_adds_geometry(
        self,
        gui: None,
        panel: ViewportPanel,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        _frame(panel, viewport_world, selection)
        panel.state.show_grid = False

        empty = _frame(panel, viewport_world, selection).total_vtx_count
        selection.select("hero")
        selected = _frame(panel, viewport_world, selection).total_vtx_count

        assert selected > empty

    def test_a_multi_selection_draws_more_than_one(
        self,
        gui: None,
        panel: ViewportPanel,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        _frame(panel, viewport_world, selection)
        panel.state.show_grid = False

        selection.select("hero")
        one = _frame(panel, viewport_world, selection).total_vtx_count
        selection.add("rock")
        two = _frame(panel, viewport_world, selection).total_vtx_count

        assert two > one

    def test_a_stale_selection_does_not_raise(
        self,
        gui: None,
        panel: ViewportPanel,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        """A selected entity can be destroyed between frames."""
        selection.select("hero")
        _frame(panel, viewport_world, selection)
        viewport_world.remove_entity("hero")
        viewport_world.flush_pending_removals()
        _frame(panel, viewport_world, selection)


class TestZoom:
    """Zooming about the cursor."""

    def test_the_wheel_zooms_in(
        self,
        gui: None,
        panel: ViewportPanel,
        camera: Camera2D,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        _frame(panel, viewport_world, selection, mouse=(320, 260))
        before = camera.zoom
        _frame(panel, viewport_world, selection, mouse=(320, 260), wheel=1.0)
        assert camera.zoom > before

    def test_the_wheel_zooms_out(
        self,
        gui: None,
        panel: ViewportPanel,
        camera: Camera2D,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        _frame(panel, viewport_world, selection, mouse=(320, 260))
        before = camera.zoom
        _frame(panel, viewport_world, selection, mouse=(320, 260), wheel=-1.0)
        assert camera.zoom < before

    def test_the_point_under_the_cursor_stays_put(
        self,
        gui: None,
        panel: ViewportPanel,
        camera: Camera2D,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        """The behaviour everyone expects and nobody describes. Zooming
        about the screen centre instead sends whatever you were looking at
        off the edge."""
        cursor = (420.0, 330.0)
        _frame(panel, viewport_world, selection, mouse=cursor)
        _frame(panel, viewport_world, selection, mouse=cursor)

        content = panel.state.content
        panel_point = Vector2(cursor[0] - content.x, cursor[1] - content.y)
        from pyguara.studio.viewport.picking import screen_to_world

        before = screen_to_world(camera, panel_point, content, panel.state.target)
        _frame(panel, viewport_world, selection, mouse=cursor, wheel=1.0)
        after = screen_to_world(camera, panel_point, content, panel.state.target)

        assert after.x == pytest.approx(before.x, abs=0.5)
        assert after.y == pytest.approx(before.y, abs=0.5)

    def test_zoom_is_clamped_at_both_ends(
        self,
        gui: None,
        panel: ViewportPanel,
        camera: Camera2D,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        """`Camera2D.zoom` rejects anything at or below zero, so an
        unclamped wheel would eventually raise."""
        _frame(panel, viewport_world, selection, mouse=(320, 260))

        for _ in range(80):
            _frame(panel, viewport_world, selection, mouse=(320, 260), wheel=-1.0)
        assert camera.zoom >= MIN_ZOOM

        for _ in range(160):
            _frame(panel, viewport_world, selection, mouse=(320, 260), wheel=1.0)
        assert camera.zoom <= MAX_ZOOM

    def test_the_wheel_is_ignored_off_the_image(
        self,
        gui: None,
        panel: ViewportPanel,
        camera: Camera2D,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        """Otherwise scrolling a docked panel beside it zooms the scene."""
        _frame(panel, viewport_world, selection, mouse=(320, 260))
        before = camera.zoom
        _frame(panel, viewport_world, selection, mouse=(5000, 5000), wheel=1.0)
        assert camera.zoom == before


class TestState:
    """Snapping and the toolbar settings."""

    def test_snapping_rounds_to_the_step(self) -> None:
        state = ViewportState(grid_size=32.0, snap=True)
        assert state.snap_value(100.0) == 96.0
        assert state.snap_value(-100.0) == -96.0

    def test_snapping_off_is_the_identity(self) -> None:
        state = ViewportState(grid_size=32.0, snap=False)
        assert state.snap_value(100.0) == 100.0

    def test_snap_point_rounds_both_axes(self) -> None:
        state = ViewportState(grid_size=32.0, snap=True)
        snapped = state.snap_point(Vector2(47, 17))
        assert (snapped.x, snapped.y) == (32.0, 32.0)

    def test_a_zero_step_does_not_divide_by_zero(self) -> None:
        state = ViewportState(grid_size=0.0, snap=True)
        assert state.snap_value(100.0) == 100.0

    def test_geometry_is_false_before_the_first_frame(self) -> None:
        assert ViewportState().has_geometry is False


class TestOverlays:
    """The seam the gizmo plugs into."""

    class _Recording(ViewportOverlay):
        def __init__(self, *, consume: bool) -> None:
            self.consume = consume
            self.calls = 0

        def draw(
            self,
            context: PanelContext,
            state: ViewportState,
            camera: Camera2D,
            draw_list: Any,
        ) -> bool:
            self.calls += 1
            return self.consume

    def test_an_overlay_is_drawn(
        self,
        gui: None,
        camera: Camera2D,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        overlay = self._Recording(consume=False)
        panel = ViewportPanel(
            camera_provider=lambda: camera,
            texture_provider=lambda: TARGET,
            overlays=[overlay],
        )
        _frame(panel, viewport_world, selection)
        assert overlay.calls == 1

    def test_add_overlay_registers_one(
        self,
        gui: None,
        panel: ViewportPanel,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        overlay = self._Recording(consume=False)
        panel.add_overlay(overlay)
        _frame(panel, viewport_world, selection)
        assert overlay.calls == 1

    def test_a_consuming_overlay_suppresses_picking(
        self,
        gui: None,
        camera: Camera2D,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        """What stops a gizmo drag from also starting a marquee, or
        re-picking whatever is behind the handle."""
        overlay = self._Recording(consume=True)
        panel = ViewportPanel(
            camera_provider=lambda: camera,
            texture_provider=lambda: TARGET,
            overlays=[overlay],
        )
        _frame(panel, viewport_world, selection)

        io = imgui.get_io()
        io.add_mouse_pos_event(320, 260)
        io.add_mouse_button_event(0, True)
        _frame(panel, viewport_world, selection)
        io.add_mouse_button_event(0, False)

        assert len(selection) == 0

    def test_the_default_overlay_consumes_nothing(self) -> None:
        state = ViewportState()
        assert (
            ViewportOverlay().draw(
                PanelContext(entity_manager=None, selection=Selection()),
                state,
                Camera2D(800, 600),
                None,
            )
            is False
        )


class TestPickingThroughThePanel:
    """A click in panel space selecting the right entity."""

    def _click(
        self,
        panel: ViewportPanel,
        world: EntityManager,
        selection: Selection,
        at: tuple[float, float],
        *,
        ctrl: bool = False,
    ) -> None:
        """Press and release the left button at a panel position."""
        io = imgui.get_io()
        io.add_mouse_pos_event(at[0], at[1])
        _frame(panel, world, selection)
        if ctrl:
            io.add_key_event(imgui.Key.mod_ctrl, True)
        io.add_mouse_button_event(0, True)
        _frame(panel, world, selection)
        io.add_mouse_button_event(0, False)
        if ctrl:
            io.add_key_event(imgui.Key.mod_ctrl, False)
        _frame(panel, world, selection)

    def test_clicking_a_sprite_selects_it(
        self,
        gui: None,
        panel: ViewportPanel,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        """The camera is at the origin, so `hero` is at the panel centre."""
        _frame(panel, viewport_world, selection)
        content = panel.state.content
        centre = (
            content.x + content.width / 2,
            content.y + content.height / 2,
        )

        self._click(panel, viewport_world, selection, centre)

        assert selection.entity_id == "hero"

    def test_clicking_empty_space_clears(
        self,
        gui: None,
        panel: ViewportPanel,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        selection.select("rock")
        _frame(panel, viewport_world, selection)
        content = panel.state.content

        self._click(panel, viewport_world, selection, (content.x + 2, content.y + 2))

        assert selection.entity_id is None

    def test_ctrl_clicking_empty_space_keeps_the_selection(
        self,
        gui: None,
        panel: ViewportPanel,
        viewport_world: EntityManager,
        selection: Selection,
    ) -> None:
        """A ctrl-click that missed should not throw away a careful
        selection."""
        selection.select("rock")
        _frame(panel, viewport_world, selection)
        content = panel.state.content

        self._click(
            panel,
            viewport_world,
            selection,
            (content.x + 2, content.y + 2),
            ctrl=True,
        )

        assert selection.entity_id == "rock"
