"""The demos built on the render graph draw their approved frames.

Lighting, bloom, storms, heat haze, pulse rings, sparks: each is held to its
golden image pass by pass in `test_wgpu_graph.py`. This holds whole frames
of the six demos that use them, which is where a pass wired up wrongly, or
left out, would show. The frames were approved when each demo's wgpu frame
matched its ModernGL one, within the bounds that edge rasterisation allows,
before ModernGL was retired.
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

_SCRIPT = Path(__file__).with_name("_graph_demo_frame.py")


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
            "SDL_VIDEODRIVER": "dummy",
        },
        check=False,
    )
    frames = sorted(out.glob("*.png"))
    if completed.returncode != 0 or not frames:
        tail = completed.stderr[-3000:] + completed.stdout[-1000:]
        if "could not be opened" in tail:
            pytest.skip(f"no {backend} device here")
        raise AssertionError(f"{demo} on {backend} failed:\n{tail}")
    return frames[-1]


# Against its own approved frame, a demo should be the same image; these
# leave room only for another GPU's rounding of the procedural shaders.
GOLDEN_FRACTION = 0.005
GOLDEN_MEAN = 0.5


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize("demo", GRAPH_DEMOS)
def test_the_demo_matches_its_golden(
    demo: str, tmp_path: Path, update_golden: bool
) -> None:
    """The wgpu frame against the one approved when it matched ModernGL."""
    import numpy as np
    import pygame

    from tests.integration import golden

    surface = pygame.image.load(str(_capture("wgpu", demo, tmp_path / "wgpu")))
    width, height = surface.get_size()
    image = np.frombuffer(
        pygame.image.tobytes(surface, "RGBA"), dtype=np.uint8
    ).reshape(height, width, 4)
    if update_golden:
        golden.save("demos", demo, image)
        return
    stored = golden.load("demos", demo, hdr=False)
    assert stored is not None, golden.missing("demos", demo, False)
    assert stored.shape == image.shape
    gap = np.abs(stored[..., :3].astype(np.int16) - image[..., :3].astype(np.int16))
    off = float((gap.max(axis=2) > 8).mean())
    mean = float(gap.mean())
    assert off <= GOLDEN_FRACTION and mean <= GOLDEN_MEAN, (
        f"{demo}: {off:.2%} of pixels differ from the golden frame by more than "
        f"8, mean {mean:.2f}. If intended, rerun with --update-golden and review "
        f"{golden.path_for('demos', demo, False)}"
    )
