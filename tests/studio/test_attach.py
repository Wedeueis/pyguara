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
once already, when the default dock layout was first wired up, and the
surface for it grew when the ImGui editor layer moved into this same
package: `pyguara.studio.layer` is now one unguarded import away from
every module the transport loads.

**Both halves of that are asserted in a subprocess, and the reason is
worth reading before changing it.** This file used to install an
`importlib` meta-path finder that raised on `imgui_bundle`, pop
`pyguara.studio*` out of `sys.modules`, and re-import. A meta-path finder
is consulted only on a `sys.modules` miss, and by the time any test runs,
`imgui_bundle` is already cached -- imported by another test module, or,
under exactly the regression this guards, by this file's own
collection-time `from pyguara.studio.attach import ...`. So the blocker
was never reached and the test passed either way. It was verified
vacuous: adding `from pyguara.studio.layer import EditorLayer` to
`pyguara/studio/__init__.py` left it green. A fresh interpreter has
nothing cached, which is the only place either property can be tested at
all.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "offscreen")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pytest

from pyguara.studio.attach import (
    DEFAULT_LAYOUT_REGIONS,
)


class TestImgulIndependence:
    """The agent surface must work with no ImGui installed.

    Each test is a fresh interpreter; see the module docstring for why
    in-process is not an option here.
    """

    _TRANSPORT_IMPORTS = (
        "import pyguara.studio\n"
        "import pyguara.studio.ops.stdio\n"
        "import pyguara.studio.session\n"
    )

    @staticmethod
    def _run(code: str) -> str:
        """Run `code` in a fresh interpreter and return its stdout.

        Args:
            code: The program to run.

        Returns:
            Its stripped standard output.
        """
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def test_the_ops_transport_does_not_import_imgui(self) -> None:
        """The stronger of the two, and the one that catches a slip.

        Not "it still works without ImGui" but "it never asked for
        ImGui" -- which is also the only form that catches a module-scope
        `pyguara.studio.availability` import, since that one *handles*
        the absence and would satisfy the weaker property while still
        loading the extension on every `pyguara studio ops`.
        """
        loaded = self._run(
            "import sys\n"
            + self._TRANSPORT_IMPORTS
            + "print(sorted(m for m in sys.modules if m.startswith('imgui')))\n"
        )
        assert loaded == "[]", (
            f"importing the agent transport pulled in {loaded} -- some module "
            "the transport loads now imports Dear ImGui at module scope"
        )

    def test_the_ops_transport_imports_with_imgui_unavailable(self) -> None:
        """And it works when ImGui is genuinely not installed.

        Blocked with a meta-path finder installed before anything else is
        imported, so the finder is actually reached.
        """
        assert (
            self._run(
                "import sys\n"
                "from importlib.abc import MetaPathFinder\n"
                "class Blocker(MetaPathFinder):\n"
                "    def find_spec(self, name, path=None, target=None):\n"
                "        if name.partition('.')[0] == 'imgui_bundle':\n"
                "            raise ImportError('No module named imgui_bundle')\n"
                "        return None\n"
                "sys.meta_path.insert(0, Blocker())\n"
                + self._TRANSPORT_IMPORTS
                + "print('imported')\n"
            )
            == "imported"
        )

    def test_the_blocker_would_be_reached(self) -> None:
        """The control for the test above: with the finder installed, the
        import it blocks really does fail. Without this, a finder that
        silently stopped matching would make that test vacuous in the
        same way the in-process version was."""
        assert (
            self._run(
                "import sys\n"
                "from importlib.abc import MetaPathFinder\n"
                "class Blocker(MetaPathFinder):\n"
                "    def find_spec(self, name, path=None, target=None):\n"
                "        if name.partition('.')[0] == 'imgui_bundle':\n"
                "            raise ImportError('No module named imgui_bundle')\n"
                "        return None\n"
                "sys.meta_path.insert(0, Blocker())\n"
                "try:\n"
                "    import pyguara.studio.layer\n"
                "except ImportError:\n"
                "    print('blocked')\n"
                "else:\n"
                "    print('not blocked')\n"
            )
            == "blocked"
        )

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
        [
            "attaches",
            "session_follows_the_scene",
            "frames_and_operations",
            "panels_install_under_the_real_loop",
            "studio_owns_the_screen",
            "the_layout_follows_the_window",
            "the_menus_are_studios_own",
            "the_editor_gets_the_whole_window",
            "the_edit_lifecycle_works",
            "editing_and_playing_are_separate",
        ],
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
