"""The capture tools boot demos from wherever `PYGUARA_EXAMPLES` points.

A copy of one demo, under another package name in a folder outside the
repository, is booted by `agent_view` run from a third directory. That is
the shape of running the engine's pixel tests against a separate checkout
of the examples.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tools import demo_list

ROOT = Path(__file__).resolve().parent.parent
DEMO = "ecs_mental_model"


def _relocated(tmp_path: Path) -> Path:
    """Copy `DEMO` to `<tmp>/checkout/showcase/`, imports renamed to match."""
    package = tmp_path / "checkout" / "showcase"
    shutil.copytree(
        demo_list.EXAMPLES_DIR / DEMO,
        package / DEMO,
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    (package / "__init__.py").write_text("")
    for source in (package / DEMO).glob("*.py"):
        source.write_text(source.read_text().replace("examples.", "showcase."))
    return package


def _run(code_or_args: list[str], package: Path, cwd: Path) -> str:
    completed = subprocess.run(  # noqa: S603 - our own interpreter
        [sys.executable, *code_or_args],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=cwd,
        env={
            **os.environ,
            "PYGUARA_EXAMPLES": str(package),
            "PYTHONPATH": str(ROOT),
            "SDL_VIDEODRIVER": "dummy",
            "SDL_AUDIODRIVER": "dummy",
            "PYGUARA_WINDOW": "offscreen",
        },
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    return completed.stdout


def test_the_demos_are_this_checkouts_examples_by_default() -> None:
    """With nothing set, the demos are `examples/` beside `tools/`."""
    if os.environ.get("PYGUARA_EXAMPLES"):
        pytest.skip("PYGUARA_EXAMPLES is set for this run")
    assert demo_list.EXAMPLES_DIR == ROOT / "examples"
    assert demo_list.DEMO_ROOT == ROOT
    assert demo_list.DEMOS[DEMO][0] == f"examples.{DEMO}.bootstrap"


def test_an_unknown_demo_names_the_known_ones() -> None:
    """A typo fails with the list rather than an import error."""
    with pytest.raises(KeyError, match=DEMO):
        demo_list.demo_module("ecs_mental_mode", "scenes")


@pytest.mark.integration
def test_a_demo_elsewhere_is_the_one_imported(tmp_path: Path) -> None:
    """The scene comes from the relocated copy, not the repository's."""
    package = _relocated(tmp_path)
    printed = _run(
        [
            "-c",
            "import sys; from tools.demo_list import load_demo; "
            f"_, scene = load_demo({DEMO!r}); "
            "print(sys.modules[scene.__module__].__file__)",
        ],
        package,
        cwd=tmp_path,
    )
    assert Path(printed.strip()) == package / DEMO / "scenes.py"


@pytest.mark.integration
def test_a_same_named_package_loaded_first_is_refused(tmp_path: Path) -> None:
    """The repository's `examples` already imported is not booted in its place."""
    package = tmp_path / "checkout" / "examples"
    shutil.copytree(
        demo_list.EXAMPLES_DIR / DEMO,
        package / DEMO,
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    (package / "__init__.py").write_text("")
    completed = subprocess.run(  # noqa: S603 - our own interpreter
        [
            sys.executable,
            "-c",
            f"import examples.{DEMO}.scenes; from tools.demo_list import load_demo; "
            f"load_demo({DEMO!r})",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=ROOT,
        env={**os.environ, "PYGUARA_EXAMPLES": str(package), "PYTHONPATH": str(ROOT)},
        check=False,
    )
    assert completed.returncode != 0
    assert "already loaded from another folder" in completed.stderr


@pytest.mark.integration
def test_agent_view_captures_a_demo_elsewhere(tmp_path: Path) -> None:
    """`agent_view`, run from another directory, boots it and saves a frame.

    It exits non-zero on a flat frame, so a pass is also a drawn one.
    """
    package = _relocated(tmp_path)
    out = tmp_path / "frames"
    _run(
        [
            str(ROOT / "tools" / "agent_view.py"),
            DEMO,
            "--frames",
            "5",
            "--out",
            str(out),
        ],
        package,
        cwd=tmp_path,
    )
    assert sorted(path.name for path in out.glob("*.png")), "no frame written"
