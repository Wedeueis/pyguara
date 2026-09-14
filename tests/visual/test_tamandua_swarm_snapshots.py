"""Snapshot the batch the Revoada draws itself in.

Tamanduá runs on ModernGL, so it is excluded from `DEMOS_THAT_DRAW` --
SDL's dummy video driver provides no OpenGL and the scene cannot boot
headlessly at all. The per-instance tint is the capability the whole demo
exists to prove, and without something like this it would ship covered by
a manual smoke test and nothing else.

`build_batch()` is pure precisely so that this is possible (GDD §4.2).
Nothing here rasterises: the snapshot is the batch's own contents --
instance count, `colors_enabled`, and the actual tint values -- which is
data, not pixels, and therefore deterministic on any machine.

**Read the diff when one of these changes.** A changed snapshot here is a
changed swarm: a different tint curve, a layer that stopped being tinted,
or a batch that quietly split.
"""

from __future__ import annotations

import pytest

from games.tamandua_murundus.swarm import (
    SwarmBatchInput,
    build_batch,
)
from pyguara.graphics.types import RenderBatch

pytestmark = pytest.mark.integration


class FakeTexture:
    """A texture with a name and a size, and no pixels behind it."""

    width = 8
    height = 8
    path = "insect.png"


def summarise(batch: RenderBatch) -> list[str]:
    """Render the batch as the lines a snapshot compares."""
    lines = [
        f"texture={batch.texture.path}",
        f"instances={len(batch.destinations)}",
        f"colors_enabled={batch.colors_enabled}",
        f"transforms_enabled={batch.transforms_enabled}",
    ]
    for index, (destination, color, scale) in enumerate(
        zip(batch.destinations, batch.colors, batch.scales, strict=True)
    ):
        lines.append(
            f"[{index}] at=({destination[0]:.3f},{destination[1]:.3f}) "
            f"rgba={color} scale=({scale[0]:.3f},{scale[1]:.3f})"
        )
    return lines


def swarm_at(glow: float) -> list[str]:
    """Three interactive insects and two motes, at one glow level."""
    return summarise(
        build_batch(
            SwarmBatchInput(
                texture=FakeTexture(),
                interactive=[(120.0, 240.0), (128.5, 236.0), (140.0, 250.25)],
                decorative=[(400.0, 300.0), (410.75, 290.5)],
                glow=glow,
            )
        )
    )


def test_the_swarm_is_dull_brown_by_day(snapshot) -> None:
    """Dusk: one batch, tinted, and nothing glowing yet."""
    assert swarm_at(0.0) == snapshot


def test_the_swarm_is_bioluminescent_at_night(snapshot) -> None:
    """Midnight. Same texture, same batch, same instance count -- only the
    tint column differs from the frame above. That is the demo's claim,
    written down as data."""
    assert swarm_at(1.0) == snapshot


def test_the_swarm_is_mid_curve_at_dusk(snapshot) -> None:
    """The interesting case: a tint that is neither end of the curve, so a
    change to the interpolation itself shows up here."""
    assert swarm_at(0.5) == snapshot
