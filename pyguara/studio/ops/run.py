"""Operations that step the game loop and capture what it draws."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyguara.studio.ops._args import (
    schema,
)
from pyguara.studio.ops.registry import Operation, OperationError, RiskClass

if TYPE_CHECKING:
    from pyguara.studio.session import StudioSession


def _require_harness(session: StudioSession) -> Any:
    """Return the session's harness, or explain that there is none.

    Args:
        session: The session to read.

    Returns:
        The harness.

    Raises:
        OperationError: If no harness is attached -- which is the case in
            a live editor, where frames are driven by the application's
            own loop rather than by an operation.
    """
    harness = session.harness
    if harness is None:
        raise OperationError(
            "This session has no run harness, so frames cannot be stepped "
            "from here. Open one with `pyguara studio ops --scene ...` or "
            "`studio.agent.harness.open_headless()`; in a live editor the "
            "application drives its own loop."
        )
    return harness


def _run_frames(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Advance the game loop, then report what moved."""
    harness = _require_harness(session)
    frames = arguments.get("frames", 1)
    if not isinstance(frames, int) or frames < 0:
        raise OperationError(f"'frames' must be a count, got {frames!r}.")

    harness.mark()
    ran = harness.step(frames)
    return {
        "requested": frames,
        "ran": ran,
        "frame": harness.frame,
        # A short run that was not asked for means the application
        # stopped, which is the thing a caller most needs told.
        "stopped": ran < frames,
        "diff": harness.changes().to_dict(),
    }


def _capture_frame(session: StudioSession, arguments: dict[str, Any]) -> Any:
    """Write the current frame to a PNG and report what is in it."""
    harness = _require_harness(session)
    name = arguments.get("name")
    capture = harness.capture(None if name is None else str(name))
    if capture is None:
        raise OperationError(
            "Nothing to capture: this backend exposes neither a display "
            "surface nor a framebuffer."
        )

    result = capture.to_dict()
    # Said plainly rather than left for the caller to infer from two
    # booleans, because a blank capture is the usual way this silently
    # reports nothing.
    if capture.world_flat:
        result["warning"] = (
            "The world buffer is a single flat colour: the scene itself "
            "drew nothing this frame."
        )
    elif capture.blank:
        result["warning"] = (
            "The composed frame is a single flat colour. A capture proves "
            "the render path, not that a window appears on screen."
        )
    return result


OPERATIONS: tuple[Operation, ...] = (
    Operation(
        name="run_frames",
        summary="Advance the game loop and report what changed.",
        detail=(
            "Frames are a fixed sixtieth of a second each, so two runs of "
            "the same script produce the same result. The reply carries a "
            "diff of what the simulation moved."
        ),
        risk=RiskClass.RUN,
        parameters=schema(
            {
                "frames": {
                    "type": "integer",
                    "description": "How many frames to run. Defaults to 1.",
                }
            }
        ),
        handler=_run_frames,
    ),
    Operation(
        name="capture_frame",
        summary="Write the current frame to a PNG and describe it.",
        detail=(
            "The reply says whether the frame, and the world buffer behind "
            "it, is a single flat colour -- which is how a broken render "
            "path shows up. A capture proves the render path works; it "
            "does not prove a window appears on screen."
        ),
        risk=RiskClass.WRITE_DISK,
        parameters=schema(
            {
                "name": {
                    "type": "string",
                    "description": (
                        "File name without an extension. Defaults to the frame number."
                    ),
                }
            }
        ),
        handler=_capture_frame,
    ),
)
