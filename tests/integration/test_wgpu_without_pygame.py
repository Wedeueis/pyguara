"""A game on the wgpu backend runs without pygame ever being imported.

What workstream 3 set out to make true (`next_engine_plan.md`): the window
and input (winit), gamepads (gilrs), images, text, the clock and -- with
the native audio backend, the default -- the sound all run without it.
Checked in a fresh interpreter where `import pygame` raises, so whatever
tries names itself in the failure.

pygame is still a dependency: the software renderer is pygame, and it is
the reference the wgpu renderer is held to.
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


@pytest.mark.integration
@pytest.mark.parametrize("demo", DEMOS)
def test_a_wgpu_demo_runs_without_pygame(demo: str) -> None:
    completed = subprocess.run(  # noqa: S603 - our own interpreter and script
        [sys.executable, str(RUNNER), demo, str(FRAMES)],
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "PYGUARA_WINDOW": "offscreen", "PYTHONHASHSEED": "0"},
        check=False,
    )
    if "graphics device could not be opened" in completed.stderr:
        pytest.skip("no graphics adapter for wgpu")
    assert f"RAN {FRAMES}" in completed.stdout, completed.stderr[-2000:]
