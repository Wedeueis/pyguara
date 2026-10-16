#!/usr/bin/env python3
"""Marco 3's numbers: the native SoA pools against the Python ones.

RFC-0003's Marco 3 replaces `ParticleSystem`, `Sparks` and
`ProjectileSystem` with native structure-of-arrays pools and claims ~45x.
This measures a whole frame of each -- emission aside, the `update` and the
`render` a game actually pays per tick -- because `update` alone is not the
frame and the two pools divide their cost very differently:

    particles  84% update, 16% render  ->  the arithmetic is the frame
    sparks     45% update, 55% render  ->  the draw calls are the frame

which is why `Sparks` needed `ShapeBatch` and `ParticleSystem` did not.
See `docs/adr/0003-native-core-spike.md` and `docs/guides/performance.md`.

Needs the extension built first, which needs a Rust toolchain:

    cargo build --release
    uv run python tools/bench_native_pool.py

Parity is *not* checked here -- `tests/test_native_particle_parity.py` and
`tests/test_native_spark_parity.py` do that properly, and a benchmark that
also claimed to prove correctness proved neither.
"""

from __future__ import annotations

import math
import os
import sys
import timeit
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from pyguara.common.random import RandomStream  # noqa: E402
from pyguara.common.types import Color, Vector2  # noqa: E402
from pyguara.graphics.components.particles import ParticleSystem  # noqa: E402
from pyguara.graphics.types import ShapeBatch, ShapeKind  # noqa: E402
from pyguara.graphics.vfx.sparks import Sparks  # noqa: E402

DT = 1.0 / 60.0
LIFE = 1e6  # outlive the measurement
SEED = 2024


class _FakeTexture:
    """A texture the pool can hold without a GL context.

    A real class rather than a `MagicMock`, and that is not fussiness: the
    Python render path groups particles with `p.texture not in batches`, so
    it hashes the texture once per particle. A mock's `__hash__` goes
    through its call machinery, which made an early version of this
    benchmark report 325x.
    """

    @property
    def width(self) -> int:
        """Width in pixels."""
        return 8

    @property
    def height(self) -> int:
        """Height in pixels."""
        return 8

    @property
    def native_handle(self) -> object:
        """Never bound; the pool only stores it."""
        return self


class _Camera:
    """A camera with no zoom and no offset, so screen space is world space."""

    zoom = 1.0

    def screen_offset(self, _viewport: object) -> Vector2:
        """No offset."""
        return Vector2.zero()


class _SpriteSink:
    """Takes `RenderBatch`es and does what a renderer's bookkeeping costs.

    The batch is walked rather than dropped, because dropping it would
    measure a pool that packed into a void.
    """

    width = 1280
    height = 720

    def render_batch(self, batch: object) -> None:
        """Consume the batch's destinations."""
        len(batch.destinations)  # type: ignore[attr-defined]


class _ShapeSink:
    """Mimics the ModernGL shape buckets, without a GL context.

    `draw_circle` and `draw_line` reproduce `ModernGLRenderer`'s own bodies
    -- normalise the colour, derive the geometry, append eleven floats --
    because that per-call work *is* what the native path removes, and a
    renderer that merely counted calls would hide it.
    """

    width = 1280
    height = 720

    def __init__(self, batched: bool) -> None:
        self.batched = batched
        self.pending: dict[int, list[object]] = {
            int(ShapeKind.CIRCLE): [],
            int(ShapeKind.LINE): [],
        }

    def clear(self) -> None:
        """Drop a frame's queued primitives."""
        for rows in self.pending.values():
            rows.clear()

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Queue a circle, as the GL renderer packs one."""
        pad = width / 2.0 if width > 0 else 0.0
        r, g, b, a = color.normalized
        self.pending[int(ShapeKind.CIRCLE)].append(
            [
                center.x,
                center.y,
                radius + pad,
                radius + pad,
                0.0,
                r,
                g,
                b,
                a,
                float(width),
                float(ShapeKind.CIRCLE),
            ]
        )

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Queue a line, as the GL renderer packs one."""
        dx, dy = end.x - start.x, end.y - start.y
        half_width = max(width, 1) / 2.0
        r, g, b, a = color.normalized
        self.pending[int(ShapeKind.LINE)].append(
            [
                (start.x + end.x) / 2.0,
                (start.y + end.y) / 2.0,
                math.hypot(dx, dy) / 2.0 + half_width,
                half_width,
                math.atan2(dy, dx),
                r,
                g,
                b,
                a,
                0.0,
                float(ShapeKind.LINE),
            ]
        )


class _BatchingShapeSink(_ShapeSink):
    """A `_ShapeSink` that also satisfies `ShapeBatchRenderer`."""

    def render_shapes(self, batch: ShapeBatch) -> None:
        """Queue a whole batch, as the GL renderer does."""
        self.pending[int(batch.kind)].extend(batch.instances)


def _ms(fn: object, number: int = 100, repeat: int = 5) -> float:
    """Fastest run in milliseconds."""
    return min(timeit.repeat(fn, number=number, repeat=repeat)) / number * 1e3  # type: ignore[arg-type]


def _particles(live: int, accelerate: bool, *, tinted: bool) -> ParticleSystem:
    """A particle pool with `live` slots occupied.

    `tinted` matters more than it looks: a colour animation makes the
    Python render path build two `Color` objects and lerp them per
    particle, where the native path lerps four bytes. Both are measured
    because fire, smoke and every fading effect set one, and because the
    untinted row is the conservative figure to quote.
    """
    pool = ParticleSystem(live, RandomStream(SEED), accelerate=accelerate)
    pool.emit(
        _FakeTexture(),  # type: ignore[arg-type]
        Vector2(0.0, 0.0),
        count=live,
        speed=100.0,
        life=LIFE,
        color_start=(255, 200, 0, 255) if tinted else None,
        color_end=(255, 0, 0, 0) if tinted else None,
    )
    return pool


def _sparks(live: int, accelerate: bool, streak: bool) -> Sparks:
    """A spark pool with `live` slots occupied."""
    pool = Sparks(live, RandomStream(SEED), accelerate=accelerate)
    pool.burst(
        Vector2.zero(),
        Color(255, 180, 60),
        count=live,
        speed=160.0,
        life=LIFE,
        streak=streak,
    )
    return pool


def _report(
    label: str, python_frame: tuple[float, float], native: tuple[float, float]
) -> None:
    """Print one scenario's update, render and frame totals."""
    py_update, py_render = python_frame
    rs_update, rs_render = native
    py_total, rs_total = py_update + py_render, rs_update + rs_render
    print(
        f"{label:22} "
        f"{py_update:8.3f} {rs_update:8.3f} "
        f"{py_render:8.3f} {rs_render:8.3f} "
        f"{py_total:8.3f} {rs_total:8.3f} "
        f"{py_total / max(rs_total, 1e-9):7.1f}x"
    )


def main() -> int:
    """Measure both pools at two occupancies.

    Returns:
        0 on success, 1 if the extension is not built.
    """
    if not ParticleSystem(capacity=1).accelerated:
        print("extension not built -- run `cargo build --release` first")
        return 1

    header = (
        f"{'scenario':22} {'py upd':>8} {'rs upd':>8} "
        f"{'py rnd':>8} {'rs rnd':>8} {'py all':>8} {'rs all':>8} {'frame':>8}"
    )
    print(header)
    print("-" * len(header))

    camera = _Camera()
    for tinted in (False, True):
        fade = "fading" if tinted else "plain"
        for live in (1000, 4000):
            measured = []
            for accelerate in (False, True):
                pool = _particles(live, accelerate, tinted=tinted)
                sink = _SpriteSink()
                measured.append(
                    (
                        _ms(lambda p=pool: p.update(DT)),
                        _ms(lambda p=pool, s=sink, c=camera: p.render(s, c)),  # type: ignore[arg-type]
                    )
                )
            _report(f"{live} particles, {fade}", measured[0], measured[1])

    for streak in (False, True):
        kind = "streaks" if streak else "dots"
        for live in (1000, 4000):
            measured = []
            for accelerate in (False, True):
                pool = _sparks(live, accelerate, streak)
                # The Python pool draws one primitive at a time whatever it
                # is handed; only the native one can use a batch, so this is
                # the comparison a game on the GL backend actually sees.
                sink = (
                    _BatchingShapeSink(batched=True)
                    if accelerate
                    else _ShapeSink(batched=False)
                )

                def render(p: Sparks = pool, s: _ShapeSink = sink) -> None:
                    s.clear()
                    p.render(s)  # type: ignore[arg-type]

                measured.append((_ms(lambda p=pool: p.update(DT)), _ms(render)))
            _report(f"{live} sparks, {kind}", measured[0], measured[1])

    return 0


if __name__ == "__main__":
    sys.exit(main())
