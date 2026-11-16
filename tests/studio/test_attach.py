"""`attach_studio`: putting the whole thing into a running application.

The session follows the scene: each scene owns its `EntityManager`, so
the session, and its undo history, is rebuilt on a scene switch.

Importing Studio must not import Dear ImGui, because the JSON-lines
transport loads `pyguara/studio/__init__.py`. That is asserted in a
subprocess: in this process `imgui_bundle` is already in
`sys.modules`, so an import blocker would never be consulted and the
test would pass either way.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
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

    Run in a subprocess, one per scenario: each boots a whole application,
    window and native frame, and none of that should outlive it into the
    suite. A scenario that finds no graphics adapter skips -- and fails
    instead under `PYGUARA_REQUIRE_GPU=1`, where a skip would read as a
    pass.

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

        from tests.conftest import REQUIRE_GPU

        environment = dict(os.environ)
        environment["SDL_VIDEODRIVER"] = "dummy"
        environment["SDL_AUDIODRIVER"] = "dummy"
        environment["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
        # A native crash (#405) otherwise ends the process with -11 and an
        # empty stderr; these make it print the Python and Rust stacks.
        environment["RUST_BACKTRACE"] = "1"

        completed = subprocess.run(
            [
                sys.executable,
                "-X",
                "faulthandler",
                "-m",
                "tests.studio._attach_scenarios",
                scenario,
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
        )

        if completed.returncode != 0 and _is_missing_gpu(completed.stderr):
            if REQUIRE_GPU:
                pytest.fail(
                    "PYGUARA_REQUIRE_GPU is set and no graphics adapter was "
                    f"available, so this would have skipped silently.\n"
                    f"{completed.stderr}"
                )
            pytest.skip(f"no graphics adapter:\n{completed.stderr[-400:]}")

        assert completed.returncode == 0, (
            f"scenario '{scenario}' failed:\n{completed.stderr}"
        )


def _is_missing_gpu(stderr: str) -> bool:
    """Whether a failure is the machine having no graphics adapter for wgpu."""
    return "the graphics device could not be opened" in stderr or (
        "no graphics adapter is available" in stderr
    )
