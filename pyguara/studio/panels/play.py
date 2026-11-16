"""Play, pause and step the game without leaving the editor.

The panel drives `Application.paused`, `time_scale` and its frame
loop; it runs no loop of its own.

Play copies the whole world into a `WorldSnapshot` and lets the game
run, and Stop puts that copy back. While playing, an edit is refused.
Pause and Step are for watching a running game.
"""

from __future__ import annotations

from typing import Any

from imgui_bundle import imgui

from pyguara.log import get_logger
from pyguara.studio.panels.base import EditorPanel, PanelContext

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

    def __init__(
        self, application: Any, session_provider: Any = None, *, visible: bool = True
    ) -> None:
        """Initialize the panel.

        Args:
            application: The `Application` to drive.
            session_provider: Returns the `StudioSession`, or None. A
                callable rather than the session itself, because it is
                replaced on a scene switch and a held one would snapshot a
                world that is no longer on screen.
            visible: Whether it draws from the first frame.
        """
        super().__init__("Play", visible=visible)
        self._application = application
        self._session_provider = session_provider
        self._pending_steps = 0
        self._snapshot: Any = None

    @property
    def paused(self) -> bool:
        """Whether the game is paused."""
        return bool(getattr(self._application, "paused", False))

    def toggle_pause(self) -> None:
        """Pause a running game, or resume a paused one."""
        self._application.paused = not self.paused

    def request_step(self, frames: int = _STEP_FRAMES) -> None:
        """Advance `frames` frames and then pause again.

        Implemented by unpausing for that many frames, not by calling
        `Application.step()`: this runs inside the application's frame, and
        stepping here would run a frame inside a frame.

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

    @property
    def playing(self) -> bool:
        """Whether the game is being played rather than the scene edited."""
        return self._snapshot is not None

    def play(self) -> None:
        """Copy the scene, then let the game run.

        The copy is what makes Stop mean something. Taken before a single
        tick, so it is the scene as authored rather than the scene one
        frame into play.
        """
        if self.playing:
            return
        session = self._session()
        if session is None:
            self.report(
                "No Studio session, so the scene cannot be copied -- and "
                "without a copy, Stop could not put it back.",
                level="warning",
            )
            return

        from pyguara.studio.model.worldsnapshot import WorldSnapshot
        from pyguara.studio.session import EditorMode

        self._snapshot = WorldSnapshot.capture(session.world)
        session.set_mode(EditorMode.PLAY)
        self._application.paused = False
        self.report(f"Playing. {self._snapshot.count} entities copied.", level="info")

    def stop(self) -> None:
        """Put the scene back as it was, and make it editable again."""
        if not self.playing:
            return
        session = self._session()
        self._application.paused = True
        self._pending_steps = 0
        snapshot = self._snapshot
        self._snapshot = None

        if session is None:
            return

        from pyguara.studio.session import EditorMode

        session.set_mode(EditorMode.EDIT)
        snapshot.restore(session.world)
        # Nothing on the history describes this world any more: the
        # commands were applied to entities that have just been replaced,
        # so reverting one would apply its inverse to an entity it never
        # touched.
        session.stack.clear()
        self.report(f"Stopped. {snapshot.count} entities restored.", level="info")

    def _session(self) -> Any:
        """Return the live session, or None.

        Returns:
            The session, or None before a scene is open.
        """
        if self._session_provider is None:
            return None
        try:
            return self._session_provider()
        except Exception as exc:  # pragma: no cover - a torn-down container
            logger.debug(f"No session to play against: {exc}")
            return None

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
            playing = self.playing

            if not playing:
                if imgui.button("Play"):
                    self.play()
                if imgui.is_item_hovered():
                    imgui.set_tooltip(
                        "Copy the scene and run the game. Edits are refused "
                        "while it plays, and Stop puts the scene back."
                    )
            else:
                if imgui.button("Stop"):
                    self.stop()
                if imgui.is_item_hovered():
                    imgui.set_tooltip(
                        "Put the scene back exactly as it was when Play was "
                        "pressed, and make it editable again."
                    )

            imgui.same_line()
            imgui.begin_disabled(not playing)
            if imgui.button("Resume" if paused else "Pause"):
                self.toggle_pause()
            imgui.end_disabled()

            imgui.same_line()
            # Stepping an already-running game would be a no-op the user
            # could not see, so it is offered only while paused.
            imgui.begin_disabled(not paused)
            if imgui.button("Step"):
                self.request_step()
            imgui.end_disabled()

            # Everything on one row. A transport bar docked to a thin
            # strip has no second row to give: at any UI scale above 1 the
            # speed control fell off the bottom behind a scrollbar.
            imgui.same_line()
            scale = float(getattr(self._application, "time_scale", 1.0))
            imgui.set_next_item_width(140)
            changed, new_scale = imgui.slider_float(
                "##speed", scale, 0.0, MAX_TIME_SCALE, "%.2fx"
            )
            if changed:
                self._application.time_scale = max(0.0, new_scale)

            imgui.same_line()
            if imgui.button("1x"):
                self._application.time_scale = 1.0

            imgui.same_line()
            if not playing:
                imgui.push_style_color(
                    imgui.Col_.text, imgui.ImVec4(0.26, 0.59, 0.98, 1.0)
                )
                imgui.text("editing")
                imgui.pop_style_color()
            else:
                imgui.text_disabled("paused" if paused else "playing")
        finally:
            # Dear ImGui owes an End for every Begin, collapsed or not.
            imgui.end()
