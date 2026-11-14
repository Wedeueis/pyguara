"""Golden images: the approved output of a render path, stored in the repo.

The wgpu render graph was held to ModernGL's frames while ModernGL existed
(stage D of `project/backlog/active/next_engine_plan.md`). Its outputs were
then frozen here, so that once ModernGL was retired a change that moves
pixels still has something to be measured against. Each image was the
wgpu output at the moment it matched ModernGL.

An 8-bit image is a PNG; an HDR buffer is its float16 RGBA as a `.npy`,
since a PNG cannot hold a value above 1.0. Rewrite them with
`pytest --update-golden`, and review the images before committing.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

GOLDEN = Path(__file__).with_name("golden")


def path_for(group: str, name: str, hdr: bool) -> Path:
    """Where a golden image lives."""
    return GOLDEN / group / f"{name}.{'npy' if hdr else 'png'}"


def save(group: str, name: str, image: np.ndarray) -> Path:
    """Store an image: (H, W, 4) uint8, or (H, W, 4) float16 for HDR."""
    import pygame

    hdr = image.dtype == np.float16
    path = path_for(group, name, hdr)
    path.parent.mkdir(parents=True, exist_ok=True)
    if hdr:
        np.save(path, image)
    else:
        height, width = image.shape[:2]
        surface = pygame.image.frombuffer(
            np.ascontiguousarray(image).tobytes(), (width, height), "RGBA"
        )
        pygame.image.save(surface, str(path))
    return path


def load(group: str, name: str, hdr: bool) -> np.ndarray | None:
    """Load a stored image, or None if there is none yet."""
    import pygame

    path = path_for(group, name, hdr)
    if not path.exists():
        return None
    if hdr:
        return np.load(path)
    surface = pygame.image.load(str(path))
    width, height = surface.get_size()
    rgba = pygame.image.tobytes(surface, "RGBA")
    return np.frombuffer(rgba, dtype=np.uint8).reshape(height, width, 4)


def missing(group: str, name: str, hdr: bool) -> str:
    """The failure message for an image with no golden yet."""
    return (
        f"no golden image at {path_for(group, name, hdr)}; run with "
        f"--update-golden to create it, and review it before committing"
    )
