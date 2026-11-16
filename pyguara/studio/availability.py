"""Whether Dear ImGui is importable, resolved once here.

`imgui_bundle.imgui` needs no OpenGL binding to create a context or
build a frame; the draw data is rasterised by `WgpuImGuiRenderer`. The
test suite asserts the flag is true on a dev install, so the editor
cannot switch itself off unnoticed.

Importing this module imports `imgui_bundle` when it is installed, so
it is not a cheap probe. Anything the agent transport loads must
import it inside a function; see `pyguara/studio/attach.py`.
"""

from __future__ import annotations

from pyguara.log import get_logger

logger = get_logger(__name__)

IMGUI_AVAILABLE: bool
"""True when `imgui_bundle` could be imported."""

IMGUI_IMPORT_ERROR: str | None
"""Why the import failed, or None when it succeeded."""

try:
    from imgui_bundle import imgui  # noqa: F401

    IMGUI_AVAILABLE = True
    IMGUI_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover - the dev extra installs it
    IMGUI_AVAILABLE = False
    IMGUI_IMPORT_ERROR = str(exc)


def require_imgui() -> None:
    """Raise if ImGui is missing, naming the install that provides it.

    Called by everything that would otherwise fail deeper in with an
    `AttributeError` on a module that was never bound. Raising beats the
    old behaviour -- an early-returning no-op that looked like a working
    editor drawing nothing.

    Raises:
        RuntimeError: If `imgui_bundle` is not importable.
    """
    if not IMGUI_AVAILABLE:
        raise RuntimeError(
            "The PyGuara editor needs Dear ImGui, which is not installed: "
            f"{IMGUI_IMPORT_ERROR}. Install the dev extra -- "
            "`uv sync --extra dev` or `pip install -e .[dev]`."
        )
