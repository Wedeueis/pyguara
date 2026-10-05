"""Whether Dear ImGui is importable, resolved once here.

This module exists because of how the engine's *previous* ImGui editor
died. `pyguara/editor/layer.py` imported `imgui.integrations.pygame`, which
transitively ran `import OpenGL.GL`; PyOpenGL was a dependency nowhere, so
`HAS_IMGUI` was unconditionally `False` in **every** install configuration.
`initialize()` logged "ImGui not found. Editor disabled.", every panel and
drawer method early-returned, and the whole 705-line subsystem never
executed once before it was deleted (2026-09-08, `refactor/editor-audit`).

Two things stop that recurring, and both matter more than the flag itself:

1. **Nothing here reaches for a GL loader.** `imgui_bundle.imgui` is the
   C++ core; it needs no OpenGL binding to create a context or build a
   frame. The draw data is rasterised by `ModernGLImGuiRenderer` through
   the engine's own `moderngl` context -- already a hard dependency -- so
   there is no second, undeclared GL stack to go missing.
2. **A test asserts this flag is `True`.** `tests/test_editor_availability.py`
   fails if a dev install cannot import ImGui, so the editor cannot quietly
   switch itself off again. A flag nothing asserts on is how the last one
   hid.
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
