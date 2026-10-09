"""The `pyguara.graphics` package root: what it exports, and what it must not import."""

import subprocess
import sys

import pyguara.graphics as graphics


def test_every_exported_name_resolves():
    """An `__all__` entry with no attribute behind it is a broken import
    waiting for the first person to try it."""
    missing = [name for name in graphics.__all__ if not hasattr(graphics, name)]

    assert missing == []


def test_the_names_the_issue_named_are_reachable():
    """`from pyguara.graphics import Sprite, Camera2D, RenderSystem` used to
    find nothing at all (#71)."""
    for name in ("Sprite", "Camera2D", "RenderSystem", "IRenderer", "Layer"):
        assert name in graphics.__all__


def test_all_is_sorted_within_its_groups_and_has_no_duplicates():
    assert len(set(graphics.__all__)) == len(graphics.__all__)


def test_importing_the_package_pulls_in_no_rendering_backend():
    """Importing the protocol surface must not require a display library.
    Run in a fresh interpreter, because by this point in a test session
    something else has already imported pygame."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import pyguara.graphics; "
            "print(int('pygame' in sys.modules), int('moderngl' in sys.modules))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "0 0", (
        f"pyguara.graphics imported a backend: {result.stdout!r}"
    )
