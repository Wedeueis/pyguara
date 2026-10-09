"""`PlayControlsPanel`: pausing and single-stepping from the editor.

The design point worth testing is how a single step is implemented. It
**unpauses for one frame** rather than calling `Application.step()`,
because the panel draws inside the editor's frame, which is inside the
application's frame -- stepping there would re-enter the loop, integrate
physics twice and draw the editor from inside itself. The first symptom
would be a game running at double speed only while the editor is open.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("imgui_bundle")

from imgui_bundle import imgui  # noqa: E402

from pyguara.ecs.manager import EntityManager  # noqa: E402
from pyguara.editor.panels.base import PanelContext  # noqa: E402
from pyguara.editor.selection import Selection  # noqa: E402
from pyguara.studio.panels.play import (  # noqa: E402
    MAX_TIME_SCALE,
    PlayControlsPanel,
)


class FakeApplication:
    """Just enough of `Application` to drive the transport.

    `step` records being called, which is how the re-entrancy test knows
    the panel did not call it.
    """

    def __init__(self) -> None:
        self.paused = False
        self.time_scale = 1.0
        self.steps = 0

    def step(self) -> bool:
        self.steps += 1
        return True


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
def application() -> FakeApplication:
    """A running fake application."""
    return FakeApplication()


@pytest.fixture
def panel(application: FakeApplication) -> PlayControlsPanel:
    """A play panel over it."""
    return PlayControlsPanel(application)


@pytest.fixture
def context(world: EntityManager) -> PanelContext:
    """An empty panel context; these controls read no scene."""
    return PanelContext(entity_manager=world, selection=Selection())


def frame(panel: PlayControlsPanel, context: PanelContext) -> None:
    """Draw one frame of the panel."""
    imgui.new_frame()
    imgui.set_next_window_size(imgui.ImVec2(400, 120))
    panel.draw(context)
    imgui.render()


class TestPausing:
    """The toggle."""

    def test_it_starts_following_the_application(
        self, panel: PlayControlsPanel, application: FakeApplication
    ) -> None:
        assert panel.paused is False
        application.paused = True
        assert panel.paused is True

    def test_toggling_pauses(
        self, panel: PlayControlsPanel, application: FakeApplication
    ) -> None:
        panel.toggle_pause()
        assert application.paused is True

    def test_toggling_again_resumes(
        self, panel: PlayControlsPanel, application: FakeApplication
    ) -> None:
        panel.toggle_pause()
        panel.toggle_pause()
        assert application.paused is False


class TestSingleStep:
    """One frame, then paused again."""

    def test_it_never_calls_step_itself(
        self,
        gui: None,
        panel: PlayControlsPanel,
        application: FakeApplication,
        context: PanelContext,
    ) -> None:
        """The whole point. Calling `Application.step()` from inside the
        editor's frame re-enters the application's frame."""
        application.paused = True
        panel.request_step()
        for _ in range(4):
            frame(panel, context)

        assert application.steps == 0

    def test_requesting_a_step_unpauses(
        self, panel: PlayControlsPanel, application: FakeApplication
    ) -> None:
        application.paused = True
        panel.request_step()
        assert application.paused is False

    def test_it_re_pauses_after_one_frame(
        self,
        gui: None,
        panel: PlayControlsPanel,
        application: FakeApplication,
        context: PanelContext,
    ) -> None:
        application.paused = True
        panel.request_step()

        frame(panel, context)

        assert application.paused is True
        assert panel.pending_steps == 0

    def test_several_frames_stay_running_until_spent(
        self,
        gui: None,
        panel: PlayControlsPanel,
        application: FakeApplication,
        context: PanelContext,
    ) -> None:
        application.paused = True
        panel.request_step(3)

        frame(panel, context)
        assert application.paused is False
        frame(panel, context)
        assert application.paused is False
        frame(panel, context)
        assert application.paused is True

    def test_a_zero_step_does_nothing(
        self, panel: PlayControlsPanel, application: FakeApplication
    ) -> None:
        application.paused = True
        panel.request_step(0)
        assert application.paused is True
        assert panel.pending_steps == 0

    def test_a_negative_step_does_nothing(
        self, panel: PlayControlsPanel, application: FakeApplication
    ) -> None:
        application.paused = True
        panel.request_step(-5)
        assert application.paused is True


class TestTimeScale:
    """Slowing the game down to watch something."""

    def test_the_bound_is_documented_and_positive(self) -> None:
        """Past it a fixed-timestep loop spends the whole frame catching
        up and the display stops responding."""
        assert MAX_TIME_SCALE > 1.0

    def test_it_reads_the_application(
        self,
        gui: None,
        panel: PlayControlsPanel,
        application: FakeApplication,
        context: PanelContext,
    ) -> None:
        application.time_scale = 0.25
        frame(panel, context)
        frame(panel, context)


class TestDrawing:
    """It draws in every state."""

    def test_it_draws_while_running(
        self, gui: None, panel: PlayControlsPanel, context: PanelContext
    ) -> None:
        frame(panel, context)
        frame(panel, context)
        assert imgui.get_draw_data().total_vtx_count > 0

    def test_it_draws_while_paused(
        self,
        gui: None,
        panel: PlayControlsPanel,
        application: FakeApplication,
        context: PanelContext,
    ) -> None:
        application.paused = True
        frame(panel, context)
        frame(panel, context)
        assert imgui.get_draw_data().total_vtx_count > 0

    def test_it_survives_an_application_missing_the_attributes(
        self, gui: None, context: PanelContext
    ) -> None:
        """A bare object stands in for anything that is not a full
        `Application`; the panel reads defaults rather than raising."""
        panel = PlayControlsPanel(object())
        assert panel.paused is False
        frame(panel, context)
