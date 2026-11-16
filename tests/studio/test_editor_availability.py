"""The editor must not be able to disable itself silently.

A dev install that cannot import ImGui, or an editor that grows an
undeclared dependency, fails here. An availability flag that no test
asserts on can be false in every install without anyone noticing.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from pyguara.studio import availability


@pytest.mark.unit
class TestImGuiIsActuallyAvailable:
    def test_imgui_is_importable_in_a_dev_install(self) -> None:
        """The exact assertion whose absence hid the last editor's death."""
        assert availability.IMGUI_AVAILABLE is True, (
            "Dear ImGui is not importable, so the editor is disabled. "
            f"{availability.IMGUI_IMPORT_ERROR}"
        )

    def test_no_import_error_is_recorded_when_available(self) -> None:
        assert availability.IMGUI_IMPORT_ERROR is None

    def test_require_imgui_passes(self) -> None:
        availability.require_imgui()  # must not raise


@pytest.mark.unit
class TestNoHiddenGLDependency:
    """The old editor died of an undeclared PyOpenGL import. The editor's
    draw path goes through `moderngl` -- already a hard dependency -- so
    importing it must not pull PyOpenGL in at all."""

    def test_importing_the_editor_does_not_import_pyopengl(self) -> None:
        # A subprocess, because PyOpenGL may already be in this process's
        # modules via some other import and the check would pass vacuously.
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys;"
                    "import pyguara.studio;"
                    "import pyguara.studio.wgpu_renderer;"
                    "import pyguara.studio.layer;"
                    "print('OpenGL' in sys.modules or "
                    "any(m.startswith('OpenGL.') for m in sys.modules))"
                ),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "False", (
            "Importing the editor pulled in PyOpenGL, the undeclared "
            "dependency that made the previous ImGui editor dead code."
        )

    def test_require_imgui_raises_when_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Raising beats the old behaviour: a no-op that looked like a
        working editor drawing nothing."""
        monkeypatch.setattr(availability, "IMGUI_AVAILABLE", False)
        monkeypatch.setattr(availability, "IMGUI_IMPORT_ERROR", "no module")
        with pytest.raises(RuntimeError, match="needs Dear ImGui"):
            availability.require_imgui()
