"""Play, pause and step the game without leaving the editor.

`Application` already has everything this needs -- `paused`, `time_scale`
and a `step()` that runs exactly one frame -- so the panel is a face on
them rather than a second loop. That matters: a second loop would
double-step physics, and the first symptom would be a game that runs at
twice speed only while the editor is open.

Pausing is how the viewport becomes an editor rather than a window onto a
moving scene. Dragging a gizmo while physics is integrating is possible
and almost never what anyone means, because the body is re-solved
underneath the drag.

**There is no "reset to where play began".** It would mean restoring the
whole world, and the only mechanism for that is `SceneSerializer`, which
silently skips any component the registry does not know -- which is every
component a *game* defines unless it registered them. A reset that
quietly dropped the player's controller would be worse than no reset, so
the panel says what to do instead: save the scene before playing and load
it afterwards, which goes through the same serializer with the loss made
visible.
"""

from __future__ import annotations

from typing import Any

from imgui_bundle import imgui

from pyguara.editor.panels.base import EditorPanel, PanelContext
from pyguara.log import get_logger

logger = get_logger(__name__)

MAX_TIME_SCALE = 4.0
"""Fastest the panel will run the game.

Past this, a fixed-timestep loop spends the whole frame in
`_fixed_update` catching up and the display stops responding -- the
spiral `physics.max_frame_time` exists to clamp, reached deliberately
from the editor instead of accidentally from a lag spike.
"""

_STEP_FRAMES = 1
"""How many frames a single step advances."""


class PlayControlsPanel(EditorPanel):
    """Pause, resume, single-step and slow down the running game."""

    def __init__(self, application: Any, *, visible: bool = True) -> None:
        """Initialize the panel.

        Args:
            application: The `Application` to drive.
            visible: Whether it draws from the first frame.
        """
        super().__init__("Play", visible=visible)
        self._application = application
        self._pending_steps = 0

    @property
    def paused(self) -> bool:
        """Whether the game is paused."""
        return bool(getattr(self._application, "paused", False))

    def toggle_pause(self) -> None:
        """Pause a running game, or resume a paused one."""
        self._application.paused = not self.paused

    def request_step(self, frames: int = _STEP_FRAMES) -> None:
        """Advance `frames` frames and then pause again.

        Implemented by **unpausing for that many frames**, not by calling
        `Application.step()`. This runs inside the editor's frame, which
        is inside the application's frame, so stepping here would re-enter
        the loop and run a frame inside a frame -- double-integrating
        physics and drawing the editor from inside itself.

        Letting the application's own loop run the frame costs nothing and
        cannot re-enter.

        Args:
            frames: How many frames to advance.
        """
        if frames <= 0:
            return
        self._pending_steps = frames
        self._application.paused = False

    @property
    def pending_steps(self) -> int:
        """How many single-step frames are still owed."""
        return self._pending_steps

    def _advance_pending(self) -> None:
        """Count down a single-step request, re-pausing when it is spent.

        Called once per frame from `draw`, so it needs nothing of its
        host. The decrement happens on the frame *after* the request,
        which is the frame the request let run.
        """
        if self._pending_steps <= 0:
            return
        self._pending_steps -= 1
        if self._pending_steps <= 0:
            self._application.paused = True

    def draw(self, context: PanelContext) -> None:
        """Draw the transport controls.

        Args:
            context: The world and selection to read. Unused: these drive
                the application, not the scene.
        """
        self._advance_pending()

        imgui.begin(self.title)
        try:
            paused = self.paused

            if imgui.button("Resume" if paused else "Pause"):
                self.toggle_pause()

            imgui.same_line()
            # Stepping an already-running game would be a no-op the user
            # could not see, so it is offered only while paused.
            imgui.begin_disabled(not paused)
            if imgui.button("Step"):
                self.request_step()
            imgui.end_disabled()

            imgui.same_line()
            imgui.text_disabled("paused" if paused else "running")

            scale = float(getattr(self._application, "time_scale", 1.0))
            imgui.set_next_item_width(160)
            changed, new_scale = imgui.slider_float("Speed", scale, 0.0, MAX_TIME_SCALE)
            if changed:
                self._application.time_scale = max(0.0, new_scale)

            imgui.same_line()
            if imgui.button("1x"):
                self._application.time_scale = 1.0

            if paused:
                imgui.text_disabled(
                    "Paused. Gizmo drags are not re-solved by physics while "
                    "the game is stopped."
                )
        finally:
            # Dear ImGui owes an End for every Begin, collapsed or not.
            imgui.end()
