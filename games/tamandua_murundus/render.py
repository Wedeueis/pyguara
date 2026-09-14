"""Every draw call the clearing makes, and the palette it makes them in.

Kept apart from the scene for the reason `protocolo_bandeira/render.py` is:
a scene that both decides what happens and decides what colour it is ends
up with the palette scattered through its update loop.

**Flush discipline.** The GL backend batches shapes by type and flushes
all of them at `end_frame()`, so within one frame a rect drawn after a
circle still lands in the rect bucket. Anything whose layering matters --
the ground under the mounds, the mounds under the insects -- is drawn in
its own explicit order here, and nothing relies on call order between
shape types.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import IRenderer

# --- palette -------------------------------------------------------
#
# Cerrado at night: burnt ochre earth going cold, dark scrub, and the
# insects carrying the only saturated colour on the field.

EARTH = Color(46, 30, 24)
EARTH_DARK = Color(30, 19, 16)
EARTH_CRACK = Color(62, 41, 31)
SCRUB = Color(38, 46, 32)
TUSSOCK = Color(64, 74, 46)

MURUNDU_BODY = Color(74, 52, 38)
MURUNDU_RIM = Color(112, 82, 58)
MURUNDU_GLOW = Color(255, 176, 92)
MURUNDU_BROKEN = Color(44, 33, 28)

TAMANDUA_BODY = Color(96, 84, 72)
TAMANDUA_STRIPE = Color(228, 224, 214)
TAMANDUA_SNOUT = Color(74, 64, 56)
TONGUE = Color(232, 118, 128)

INSECT_DULL = Color(126, 96, 62)
INSECT_LIT = Color(120, 255, 196)

HUD_TEXT = Color(226, 240, 220)
HUD_DIM = Color(128, 148, 132)


@dataclass(slots=True)
class MurunduView:
    """What the renderer needs to know about one mound."""

    position: Vector2
    radius: float
    health_fraction: float
    broken: bool
    glow: float


@dataclass(slots=True)
class InsectView:
    """What the renderer needs to know about one insect.

    `tint` is resolved by the caller rather than here, because from D3 it
    comes off the day/night curve and the renderer should not be the thing
    that knows what time it is.
    """

    position: Vector2
    angle: float
    tint: Color
    size: float


class Backdrop:
    """The generated clearing: earth, cracks, scrub and tussock.

    Scattered once at construction and never regenerated, so the ground is
    a fixed place the run happens in rather than a field that churns under
    it.
    """

    def __init__(
        self,
        width: int,
        height: int,
        arena: Rect,
        rng: RandomStream | None = None,
    ) -> None:
        """Scatter the clearing.

        Args:
            width: Window width.
            height: Window height.
            arena: The play area, in screen space.
            rng: Seeded stream, or None for an unseeded scatter.
        """
        self._width = width
        self._height = height
        self._arena = arena
        stream = rng if rng is not None else RandomStream()

        self._cracks: list[tuple[Vector2, Vector2]] = []
        for _ in range(70):
            start = Vector2(
                stream.uniform(arena.left, arena.right),
                stream.uniform(arena.top, arena.bottom),
            )
            angle = stream.uniform(0.0, math.tau)
            length = stream.uniform(14.0, 54.0)
            self._cracks.append(
                (
                    start,
                    Vector2(
                        start.x + math.cos(angle) * length,
                        start.y + math.sin(angle) * length,
                    ),
                )
            )

        self._scrub: list[tuple[Vector2, float]] = [
            (
                Vector2(
                    stream.uniform(arena.left, arena.right),
                    stream.uniform(arena.top, arena.bottom),
                ),
                stream.uniform(5.0, 16.0),
            )
            for _ in range(90)
        ]

        self._tussock: list[tuple[Vector2, float]] = [
            (
                Vector2(
                    stream.uniform(arena.left, arena.right),
                    stream.uniform(arena.top, arena.bottom),
                ),
                stream.uniform(3.0, 7.0),
            )
            for _ in range(60)
        ]

    def draw(self, renderer: IRenderer) -> None:
        """Paint the ground. Call before anything that stands on it."""
        renderer.draw_rect(Rect(0, 0, self._width, self._height), EARTH_DARK)
        renderer.draw_rect(self._arena, EARTH)

        for start, end in self._cracks:
            renderer.draw_line(start, end, EARTH_CRACK, width=1)
        for position, radius in self._scrub:
            renderer.draw_circle(position, radius, SCRUB)
        for position, radius in self._tussock:
            renderer.draw_circle(position, radius, TUSSOCK)


def draw_murundu(renderer: IRenderer, view: MurunduView) -> None:
    """Draw one mound, glowing if it is still feeding.

    A broken mound keeps its silhouette -- it is still a thing standing in
    the clearing -- but loses its rim light and its glow, which is the
    read the player needs at a glance.
    """
    if view.broken:
        renderer.draw_circle(view.position, view.radius * 0.82, MURUNDU_BROKEN)
        return

    renderer.draw_circle(view.position, view.radius, MURUNDU_BODY)
    renderer.draw_circle(view.position, view.radius, MURUNDU_RIM, width=2)

    # The vent at the top, brightening as the mound pulses. This is the
    # part the flickering LightSource sits over.
    vent = Vector2(view.position.x, view.position.y - view.radius * 0.45)
    renderer.draw_circle(vent, 4.0 + view.glow * 3.0, MURUNDU_GLOW)

    if view.health_fraction < 1.0:
        width = view.radius * 1.6
        bar = Rect(
            int(view.position.x - width / 2),
            int(view.position.y + view.radius + 6),
            int(width),
            3,
        )
        renderer.draw_rect(bar, EARTH_DARK)
        filled = Rect(bar.x, bar.y, int(width * view.health_fraction), bar.height)
        renderer.draw_rect(filled, MURUNDU_RIM)


def draw_tamandua(
    renderer: IRenderer, position: Vector2, facing: float, lash: float
) -> None:
    """Draw the anteater, snout first.

    Args:
        renderer: Where to draw.
        position: Body centre.
        facing: Heading in radians, clockwise from screen +x.
        lash: 0..1, how far through a tongue lash the animation is.
    """
    forward = Vector2(math.cos(facing), math.sin(facing))

    # Tail: a wedge behind the body, drawn first so the body overlaps it.
    tail = Vector2(position.x - forward.x * 26.0, position.y - forward.y * 26.0)
    renderer.draw_line(position, tail, TAMANDUA_BODY, width=13)
    renderer.draw_circle(tail, 9.0, TAMANDUA_BODY)

    renderer.draw_circle(position, 15.0, TAMANDUA_BODY)

    # The bandeira's diagonal stripe, the one feature that makes the
    # silhouette read as this animal and not a generic blob.
    side = Vector2(-forward.y, forward.x)
    stripe_a = Vector2(
        position.x - forward.x * 6.0 + side.x * 11.0,
        position.y - forward.y * 6.0 + side.y * 11.0,
    )
    stripe_b = Vector2(
        position.x + forward.x * 9.0 - side.x * 8.0,
        position.y + forward.y * 9.0 - side.y * 8.0,
    )
    renderer.draw_line(stripe_a, stripe_b, TAMANDUA_STRIPE, width=4)

    snout = Vector2(position.x + forward.x * 24.0, position.y + forward.y * 24.0)
    renderer.draw_line(position, snout, TAMANDUA_SNOUT, width=7)
    renderer.draw_circle(snout, 4.0, TAMANDUA_SNOUT)

    if lash > 0.0:
        tip = Vector2(
            snout.x + forward.x * 46.0 * lash,
            snout.y + forward.y * 46.0 * lash,
        )
        renderer.draw_line(snout, tip, TONGUE, width=3)
        renderer.draw_circle(tip, 3.0, TONGUE)


def draw_insects(renderer: IRenderer, views: list[InsectView]) -> None:
    """Draw the interactive insects.

    D1 draws them as shape primitives, which is honest about what this PR
    proves: the tongue and the mounds. **D2 replaces this with a single
    instanced, per-instance-tinted sprite batch**, which is the capability
    the demo exists to show -- and which is why `InsectView` already
    carries a resolved `tint` that nothing here is yet using per-instance.
    """
    for view in views:
        renderer.draw_circle(view.position, view.size, view.tint)


def draw_tongue_arc(
    renderer: IRenderer,
    position: Vector2,
    facing: float,
    reach: float,
    arc: float,
    strength: float,
) -> None:
    """Sketch the wedge the tongue can reach into.

    Drawn faintly and only while the tongue is ready, so the player can
    learn the range without a tutorial and without it becoming furniture.
    """
    if strength <= 0.0:
        return

    faded = Color(TONGUE.r, TONGUE.g, TONGUE.b, int(46 * strength))
    for side in (-0.5, 0.5):
        angle = facing + arc * side
        renderer.draw_line(
            position,
            Vector2(
                position.x + math.cos(angle) * reach,
                position.y + math.sin(angle) * reach,
            ),
            faded,
            width=1,
        )
