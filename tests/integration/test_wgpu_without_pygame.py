"""A game on the wgpu backend runs without pygame ever being imported.

What workstream 3 set out to make true (`next_engine_plan.md`). Checked in a
fresh interpreter where `import pygame` raises, so whatever tries names
itself in the failure.

Two pieces still use pygame on every backend: SDL's joysticks (replaced in
increment 3b) and the audio system (4b). `test_..._with_those_stood_in`
replaces them and holds everything else to the promise today; the plain test
is a strict xfail, so it fails the suite the moment it starts passing and
the marker has to come off.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = Path(__file__).with_name("_without_pygame.py")
FRAMES = 30

# Demos on the render graph, which select wgpu themselves.
DEMOS = ["guara_falcao", "quintal_cerrado", "true_coral"]


def _run(demo: str, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - our own interpreter and script
        [sys.executable, str(RUNNER), demo, str(FRAMES), *flags],
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "PYGUARA_WINDOW": "offscreen", "PYTHONHASHSEED": "0"},
        check=False,
    )


def _ran(completed: subprocess.CompletedProcess[str]) -> bool:
    if "graphics device could not be opened" in completed.stderr:
        pytest.skip("no graphics adapter for wgpu")
    return f"RAN {FRAMES}" in completed.stdout


@pytest.mark.integration
@pytest.mark.parametrize("demo", DEMOS)
def test_a_wgpu_demo_runs_without_pygame_with_those_stood_in(demo: str) -> None:
    completed = _run(demo, "--stand-in-pending")
    assert _ran(completed), completed.stderr[-2000:]


@pytest.mark.integration
@pytest.mark.xfail(
    strict=True, reason="joysticks (3b) and audio (4b) still import pygame"
)
def test_a_wgpu_demo_runs_without_pygame() -> None:
    completed = _run("guara_falcao")
    assert _ran(completed), completed.stderr[-2000:]
