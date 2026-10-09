"""`attach_studio`: putting the whole thing into a running application.

Two properties get the most attention here.

The first is that **the session follows the scene**. Each scene owns its
own `EntityManager`, so a session built at attach time would be editing
the world of whichever scene happened to be active -- usually none, since
`attach_studio` runs before `app.run()`. It is also the only correct
answer for the undo history: one that spanned a scene switch would be
reverting commands into a world that never saw them applied.

The second is that **importing Studio must not import Dear ImGui**. The
dependency-free JSON-lines transport goes through `pyguara/studio/
__init__.py`, which imports this module, so a module-level ImGui import
here would make the transport need ImGui after all -- precisely the
coupling the optional MCP extra was kept out of. That regression happened
once already, when the default dock layout was first wired up.
"""

from __future__ import annotations

import os
import subprocess
import sys
from importlib.abc import MetaPathFinder
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "offscreen")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pytest

from pyguara.studio.attach import (
    DEFAULT_LAYOUT_REGIONS,
)


class TestImgulIndependence:
    """The agent surface must work with no ImGui installed."""

    def test_the_ops_transport_imports_without_imgui(self) -> None:
        """Asserted by blocking the import rather than by reading the
        source, because the coupling that broke this was three modules
        away -- `studio/__init__` imports `attach`, which imported the
        editor layer, which imports ImGui at module scope."""

        class _Blocker(MetaPathFinder):
            def find_spec(self, name, path=None, target=None):  # type: ignore[no-untyped-def]
                if name == "imgui_bundle" or name.startswith("imgui_bundle."):
                    raise ImportError("No module named imgui_bundle")
                return None

        blocker = _Blocker()
        removed = [
            name
            for name in list(sys.modules)
            if name.startswith(("pyguara.studio", "pyguara.editor"))
        ]
        saved = {name: sys.modules.pop(name) for name in removed}
        sys.meta_path.insert(0, blocker)
        try:
            import pyguara.studio  # noqa: F401
            import pyguara.studio.ops.stdio  # noqa: F401
            import pyguara.studio.session  # noqa: F401
        finally:
            sys.meta_path.remove(blocker)
            for name in list(sys.modules):
                if name.startswith(("pyguara.studio", "pyguara.editor")):
                    del sys.modules[name]
            sys.modules.update(saved)

    def test_the_default_layout_is_plain_data(self) -> None:
        """Titles rather than a `DockLayout`, so this module can be
        imported without ImGui."""
        assert DEFAULT_LAYOUT_REGIONS["centre"] == ("Viewport",)
        assert "Hierarchy" in DEFAULT_LAYOUT_REGIONS["left"]
        assert "Inspector" in DEFAULT_LAYOUT_REGIONS["right"]


@pytest.mark.integration
class TestAttachToARealApplication:
    """A whole engine, with Studio in it.

    Run in a subprocess, one per scenario. `attach_studio` needs a real
    SDL window with a GL context, and the suite's session-scoped `gl_ctx`
    fixture already holds a standalone EGL context current -- creating the
    second in the same process fails with `EGL_BAD_ACCESS`. Running these
    in-process made them pass alone and *skip* in the full suite, and a
    skip reads as a pass: the exact failure
    `tests/test_gl_fixture_guard.py` exists to prevent.

    Three scenarios rather than fourteen tests, because each costs a full
    engine boot. The assertions inside them carry their own messages, so a
    failure still says which one and why.
    """

    @pytest.mark.parametrize(
        "scenario",
        ["attaches", "session_follows_the_scene", "frames_and_operations"],
    )
    def test_scenario(self, scenario: str) -> None:
        pytest.importorskip("imgui_bundle")
        pytest.importorskip("moderngl")

        from tests.conftest import REQUIRE_GL

        environment = dict(os.environ)
        environment["SDL_VIDEODRIVER"] = "offscreen"
        environment["SDL_AUDIODRIVER"] = "dummy"
        environment["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

        completed = subprocess.run(
            [sys.executable, "-m", "tests.studio._attach_scenarios", scenario],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
        )

        if completed.returncode != 0 and _is_missing_gl(completed.stderr):
            if REQUIRE_GL:
                pytest.fail(
                    "PYGUARA_REQUIRE_GL is set and no GL context was "
                    f"available, so this would have skipped silently.\n"
                    f"{completed.stderr}"
                )
            pytest.skip(f"no GL context available:\n{completed.stderr[-400:]}")

        assert completed.returncode == 0, (
            f"scenario '{scenario}' failed:\n{completed.stderr}"
        )


def _is_missing_gl(stderr: str) -> bool:
    """Whether a failure is the machine having no usable GL.

    Distinguished from a real failure so that a broken attachment is a
    failure and an absent GPU is a skip. Matching on the driver's own
    words rather than on the exception type, because the failure surfaces
    as a plain `Exception` from deep inside SDL.

    Args:
        stderr: The subprocess's stderr.

    Returns:
        True when the failure looks like missing GL support.
    """
    markers = (
        "OpenGL support is either not configured",
        "Could not create GL context",
        "eglMakeCurrent",
        "EGL_BAD_ACCESS",
        "libGL",
    )
    return any(marker in stderr for marker in markers)
