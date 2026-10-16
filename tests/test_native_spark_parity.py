"""The two spark stores must agree, or the accelerator is a bug factory.

The sibling of `tests/test_native_particle_parity.py`, and the same trade:
keeping a native pool alongside the Python one buys an installable
pure-Python engine and costs two implementations that have to behave the
same.

Sparks need more of this than particles did, because the native path has
two render routes rather than one. A renderer that implements
`ShapeBatchRenderer` receives packed instance rows; anything else receives
one `draw_circle` or `draw_line` per spark. Both must draw what the Python
pool would have drawn, so both are compared here.

Skipped wholesale when the extension is not built, which is the normal
state for a contributor without a Rust toolchain -- `cargo build --release`
makes these run.

Floats are compared with a tolerance because the native pool stores f32
where Python uses f64; `tests/test_native_particle_parity.py` argues why
that trade is acceptable for a visual effect.
"""

from __future__ import annotations

import math

import pytest

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Vector2
from pyguara.graphics.types import ShapeBatch, ShapeKind
from pyguara.graphics.vfx.sparks import Sparks

CAPACITY = 64
DT = 1.0 / 60.0
AMBER = Color(255, 180, 60)


def _available() -> bool:
    """Whether the native extension is present."""
    return Sparks(capacity=1).accelerated


pytestmark = pytest.mark.skipif(
    not _available(), reason="native extension not built; `cargo build --release`"
)


def _pair(capacity: int = CAPACITY, seed: int = 99) -> tuple[Sparks, Sparks]:
    """A Python pool and a native pool on identical seeded streams.

    The same seed matters: `burst` takes three draws per spark, so two
    pools on different streams spawn different sparks and nothing can be
    compared.
    """
    return (
        Sparks(capacity, RandomStream(seed), accelerate=False),
        Sparks(capacity, RandomStream(seed), accelerate=True),
    )


class _Recorder:
    """A renderer that records primitives and cannot take a batch.

    Deliberately not a `MagicMock`: a mock satisfies every
    `runtime_checkable` protocol, including `ShapeBatchRenderer`, so a
    mocked renderer would silently take the batched route and these tests
    would never exercise the fallback.
    """

    def __init__(self) -> None:
        self.circles: list[tuple[float, float, float, Color]] = []
        self.lines: list[tuple[float, float, float, float, int, Color]] = []

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Record a circle."""
        self.circles.append((center.x, center.y, radius, color))

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Record a line."""
        self.lines.append((start.x, start.y, end.x, end.y, width, color))


class _BatchRecorder(_Recorder):
    """A renderer that can take a batch, and records those instead."""

    def __init__(self) -> None:
        super().__init__()
        self.batches: list[ShapeBatch] = []

    def render_shapes(self, batch: ShapeBatch) -> None:
        """Record a batch."""
        self.batches.append(batch)


def test_the_same_seed_spawns_the_same_count() -> None:
    python_pool, native_pool = _pair()

    for pool in (python_pool, native_pool):
        pool.burst(Vector2(10.0, 20.0), AMBER, count=12, life=2.0)

    assert python_pool.live_count == native_pool.live_count == 12


def test_a_burst_larger_than_the_pool_fills_it_and_stops() -> None:
    """Both drop the remainder rather than evicting a live spark."""
    python_pool, native_pool = _pair(capacity=8)

    for pool in (python_pool, native_pool):
        pool.burst(Vector2.zero(), AMBER, count=40, life=5.0)

    assert python_pool.live_count == native_pool.live_count == 8


def test_an_overflowing_burst_leaves_both_streams_in_step() -> None:
    """The subtle one, and the reason `_burst_native` counts free slots.

    The Python pool asks for a slot before it draws, so a burst that
    overflows consumes nothing for the sparks it drops. A native path that
    drew `count` sets regardless would come out of the burst with its
    stream further along -- and then *every later burst* would differ,
    while the burst that caused it looked perfectly fine. This asserts on a
    later burst for exactly that reason.
    """
    python_pool, native_pool = _pair(capacity=8)

    for pool in (python_pool, native_pool):
        pool.burst(Vector2.zero(), AMBER, count=40, life=0.05)
        pool.update(1.0)  # retire the lot, freeing the pool
        assert pool.live_count == 0
        pool.burst(Vector2.zero(), AMBER, count=4, speed=100.0, life=5.0)

    expected = sorted(
        (spark.velocity.x, spark.velocity.y)
        for spark in python_pool._pool
        if spark.active
    )
    got = sorted(
        native_pool._native.slot(i)[2:4]
        for i in range(8)
        if native_pool._native.slot(i)[6]
    )

    assert len(expected) == len(got) == 4
    for (ex, ey), (gx, gy) in zip(expected, got, strict=True):
        assert gx == pytest.approx(ex, abs=0.01)
        assert gy == pytest.approx(ey, abs=0.01)


def test_positions_agree_after_a_hundred_ticks() -> None:
    """The integration, compared where it has had time to diverge."""
    python_pool, native_pool = _pair()
    for pool in (python_pool, native_pool):
        pool.burst(
            Vector2.zero(),
            AMBER,
            count=8,
            speed=120.0,
            life=100.0,
            gravity=220.0,
            drag=0.92,
        )

    for _ in range(100):
        python_pool.update(DT)
        native_pool.update(DT)

    expected = sorted(
        (spark.position.x, spark.position.y)
        for spark in python_pool._pool
        if spark.active
    )
    got = sorted(
        native_pool._native.slot(i)[:2]
        for i in range(CAPACITY)
        if native_pool._native.slot(i)[6]
    )

    assert len(expected) == len(got) == 8
    for (ex, ey), (gx, gy) in zip(expected, got, strict=True):
        assert gx == pytest.approx(ex, abs=0.05)
        assert gy == pytest.approx(ey, abs=0.05)


def test_sparks_expire_on_the_same_tick() -> None:
    python_pool, native_pool = _pair()
    for pool in (python_pool, native_pool):
        pool.burst(Vector2.zero(), AMBER, count=5, speed=10.0, life=0.1)

    counts: list[tuple[int, int]] = []
    for _ in range(20):
        python_pool.update(DT)
        native_pool.update(DT)
        counts.append((python_pool.live_count, native_pool.live_count))

    assert all(python == native for python, native in counts), counts
    assert counts[-1] == (0, 0)


@pytest.mark.parametrize("streak", [False, True], ids=["dots", "streaks"])
def test_the_fallback_draws_what_python_draws(streak: bool) -> None:
    """A renderer that cannot batch must see the same primitives.

    Aged a third of the way through, not halfway: the fade is a straight
    multiply, so a path that got `remaining` backwards would still agree at
    the midpoint of a symmetric life -- the trap
    `tests/test_native_particle_parity.py` fell into.
    """
    python_pool, native_pool = _pair()
    for pool in (python_pool, native_pool):
        pool.burst(
            Vector2(40.0, 15.0),
            AMBER,
            count=6,
            speed=80.0,
            life=1.0,
            streak=streak,
        )
    for _ in range(20):
        python_pool.update(DT)
        native_pool.update(DT)

    offset = Vector2(7.0, -3.0)
    python_recorder, native_recorder = _Recorder(), _Recorder()
    python_pool.render(python_recorder, offset)
    native_pool.render(native_recorder, offset)

    if streak:
        assert python_recorder.circles == native_recorder.circles == []
        expected = sorted(python_recorder.lines)
        got = sorted(native_recorder.lines)
    else:
        assert python_recorder.lines == native_recorder.lines == []
        expected = sorted(python_recorder.circles)  # type: ignore[arg-type]
        got = sorted(native_recorder.circles)  # type: ignore[arg-type]

    assert len(expected) == len(got) == 6
    for expected_call, got_call in zip(expected, got, strict=True):
        *expected_numbers, expected_color = expected_call
        *got_numbers, got_color = got_call
        for ex, go in zip(expected_numbers, got_numbers, strict=True):
            assert go == pytest.approx(ex, abs=0.05)
        for channel_expected, channel_got in zip(
            expected_color, got_color, strict=True
        ):
            assert abs(channel_expected - channel_got) <= 1


@pytest.mark.parametrize("streak", [False, True], ids=["dots", "streaks"])
def test_the_batched_rows_describe_the_same_primitives(streak: bool) -> None:
    """The packed rows must mean what the draw calls mean.

    The row layout is derived -- a capsule's centre, half length and angle
    rather than its two endpoints -- so this reverses the derivation and
    compares against the fallback's endpoints. The ModernGL renderer's own
    packing is checked against a real context in
    `tests/integration/test_moderngl_pixels.py`; this checks the two native
    routes cannot drift apart.
    """
    _, native_pool = _pair()
    native_pool.burst(
        Vector2(40.0, 15.0), AMBER, count=6, speed=80.0, life=1.0, streak=streak
    )
    for _ in range(20):
        native_pool.update(DT)

    offset = Vector2(7.0, -3.0)
    batched, direct = _BatchRecorder(), _Recorder()
    native_pool.render(batched, offset)
    native_pool.render(direct, offset)

    assert [batch.kind for batch in batched.batches] == [
        ShapeKind.LINE if streak else ShapeKind.CIRCLE
    ]
    rows = batched.batches[0].instances
    assert len(rows) == 6

    if not streak:
        for row, (x, y, radius, color) in zip(rows, direct.circles, strict=True):
            assert row[0] == pytest.approx(x)
            assert row[1] == pytest.approx(y)
            assert row[2] == pytest.approx(radius, abs=1e-5)
            assert row[3] == pytest.approx(radius, abs=1e-5)
            assert row[10] == float(ShapeKind.CIRCLE)
            for column, channel in zip(range(5, 9), color, strict=True):
                assert row[column] == pytest.approx(channel / 255.0, abs=1e-3)
        return

    for row, (sx, sy, ex, ey, width, color) in zip(rows, direct.lines, strict=True):
        half_width = row[3]
        half_length = row[2] - half_width
        assert half_width * 2.0 == pytest.approx(width, abs=1e-5)
        assert row[0] == pytest.approx((sx + ex) / 2.0, abs=1e-4)
        assert row[1] == pytest.approx((sy + ey) / 2.0, abs=1e-4)
        assert half_length * 2.0 == pytest.approx(
            math.hypot(ex - sx, ey - sy), abs=1e-3
        )
        assert row[4] == pytest.approx(math.atan2(ey - sy, ex - sx), abs=1e-5)
        assert row[10] == float(ShapeKind.LINE)
        for column, channel in zip(range(5, 9), color, strict=True):
            assert row[column] == pytest.approx(channel / 255.0, abs=1e-3)


def test_an_empty_pool_sends_no_batches() -> None:
    """An idle effect layer should cost nothing, not an empty draw call."""
    _, native_pool = _pair()
    recorder = _BatchRecorder()

    native_pool.render(recorder, Vector2.zero())

    assert recorder.batches == []
