"""Run the wgpu pixel suite in a process of its own, every time.

`test_wgpu_pixels.py` skips when no device can be opened, and inside a full
test run that is the usual case on Linux without Vulkan: wgpu falls back to
its GL backend, and the ModernGL tests earlier in the same process have
left an OpenGL context current, so a second one cannot be made. A suite
that skips itself whenever it runs with the others would report green
having drawn nothing -- the failure `AGENTS.md` warns about for the parity
suites.

So this runs that file in a fresh interpreter and asserts on what happened
there. It skips only when the *clean* process also had no adapter, which is
a machine with no GPU and no software rasteriser.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_SUITE = Path(__file__).with_name("test_wgpu_pixels.py")


@pytest.mark.integration
def test_the_pixel_suite_passes_in_a_clean_process() -> None:
    completed = subprocess.run(  # noqa: S603 - our own interpreter and test file
        [sys.executable, "-m", "pytest", str(_SUITE), "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        timeout=600,
        env={**os.environ, "SDL_VIDEODRIVER": "dummy"},
        check=False,
    )
    summary = completed.stdout.strip().splitlines()[-1] if completed.stdout else ""
    passed = re.search(r"(\d+) passed", summary)

    if passed is None and "skipped" in summary and completed.returncode == 0:
        pytest.skip(f"no graphics adapter even in a clean process: {summary}")
    assert completed.returncode == 0, (
        completed.stdout[-4000:] + completed.stderr[-2000:]
    )
    assert passed is not None and int(passed.group(1)) >= 40, summary
