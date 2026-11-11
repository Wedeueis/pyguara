"""The demos built on the render graph draw the same scene on wgpu as on ModernGL.

Lighting, bloom, storms, heat haze, pulse rings, sparks: each is held to
ModernGL pass by pass in `test_wgpu_graph.py`. This holds whole frames of
the six demos that use them, which is where a pass wired up wrongly, or
left out, would show.

**The bound is not exact, on purpose.** The two backends rasterise a
primitive's edge by different rules -- wgpu's `draw_circle`, `draw_line`
and `draw_rect` match pygame's pixels, ModernGL tests a distance at each
pixel centre, and a ModernGL line has rounded ends -- so the edges of
every shape differ by a pixel. Measured, that is up to 1% of pixels off by
more than 32, with a mean difference near 1. A missing light pass, a
skipped bloom or a storm drawn upside down moves the whole frame, and
fails both bounds by a wide margin.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

GRAPH_DEMOS = [
    "true_coral",
    "mourisco_ressonancia",
    "protocolo_bandeira",
    "tamandua_murundus",
    "quintal_cerrado",
    "guara_falcao",
]

_SCRIPT = Path(__file__).with_name("_gl_demo_frame.py")

# Pixels more than 32 apart, as a fraction of the frame: shape edges only.
EDGE_FRACTION = 0.015
# Mean absolute difference over every channel of every pixel.
MEAN_DIFFERENCE = 2.0


def _capture(backend: str, demo: str, out: Path) -> Path:
    completed = subprocess.run(  # noqa: S603 - our own interpreter and script
        [sys.executable, str(_SCRIPT), backend, demo, str(out)],
        capture_output=True,
        text=True,
        timeout=300,
        env={
            **os.environ,
            "SDL_AUDIODRIVER": "dummy",
            "PYTHONHASHSEED": "0",
            "SDL_VIDEODRIVER": "offscreen" if backend == "moderngl" else "dummy",
        },
        check=False,
    )
    frames = sorted(out.glob("*.png"))
    if completed.returncode != 0 or not frames:
        tail = completed.stderr[-3000:] + completed.stdout[-1000:]
        if "could not be opened" in tail or "OpenGL" in tail and backend == "moderngl":
            pytest.skip(f"no {backend} device here")
        raise AssertionError(f"{demo} on {backend} failed:\n{tail}")
    return frames[-1]


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("demo", GRAPH_DEMOS)
def test_the_demo_draws_the_same_scene_on_wgpu(demo: str, tmp_path: Path) -> None:
    import numpy as np
    import pygame

    gl = pygame.surfarray.array3d(
        pygame.image.load(str(_capture("moderngl", demo, tmp_path / "gl")))
    ).astype(np.int16)
    wgpu = pygame.surfarray.array3d(
        pygame.image.load(str(_capture("wgpu", demo, tmp_path / "wgpu")))
    ).astype(np.int16)

    assert gl.shape == wgpu.shape
    gap = np.abs(gl - wgpu)
    edges = float((gap.max(axis=2) > 32).mean())
    mean = float(gap.mean())
    assert edges <= EDGE_FRACTION and mean <= MEAN_DIFFERENCE, (
        f"{demo}: {edges:.2%} of pixels differ by more than 32, mean difference "
        f"{mean:.2f}; the bound is {EDGE_FRACTION:.1%} and {MEAN_DIFFERENCE}"
    )
