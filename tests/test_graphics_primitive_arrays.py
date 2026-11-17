"""Arrays of primitives draw the same frame as one call per primitive.

On wgpu, `draw_rects`, `draw_circles` and `draw_lines` hand a whole array to
the GPU frame in one call. Each row has to cover exactly the pixels the
matching `draw_rect`, `draw_circle` or `draw_line` call does, so the two are
rendered on identical frames and compared byte for byte. Coordinates are
multiples of 0.25, which float32 holds exactly, so a difference is the
batch's and not the conversion's.

On a renderer without the capability, `pyguara.graphics.primitives` draws
the rows one call at a time, which is checked against a recorder.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics import primitives
from pyguara.graphics.protocols import PrimitiveArrayRenderer

WIDTH, HEIGHT = 160, 120


def _quarter(rng: RandomStream, low: float, high: float) -> float:
    return round(rng.uniform(low, high) * 4) / 4


def _colour(rng: RandomStream) -> list[float]:
    alpha = 0 if rng.uniform(0, 1) < 0.1 else int(rng.uniform(40, 255))
    return [int(rng.uniform(0, 255)) for _ in range(3)] + [alpha]


def _rect_rows(seed: int, count: int) -> np.ndarray:
    rng = RandomStream(seed)
    rows = []
    for _ in range(count):
        outline = 0 if rng.uniform(0, 1) < 0.5 else int(rng.uniform(1, 6))
        rows.append(
            [
                _quarter(rng, -20, WIDTH),
                _quarter(rng, -20, HEIGHT),
                _quarter(rng, -2, 50),
                _quarter(rng, -2, 40),
                *_colour(rng),
                outline,
            ]
        )
    return np.array(rows, dtype=np.float32)


def _circle_rows(seed: int, count: int) -> np.ndarray:
    rng = RandomStream(seed)
    rows = []
    for _ in range(count):
        outline = 0 if rng.uniform(0, 1) < 0.5 else int(rng.uniform(1, 8))
        rows.append(
            [
                _quarter(rng, -15, WIDTH + 15),
                _quarter(rng, -15, HEIGHT + 15),
                _quarter(rng, -1, 30),
                outline,
                *_colour(rng),
            ]
        )
    return np.array(rows, dtype=np.float32)


def _line_rows(seed: int, count: int) -> np.ndarray:
    rng = RandomStream(seed)
    rows = []
    for index in range(count):
        start = (_quarter(rng, -10, WIDTH), _quarter(rng, -10, HEIGHT))
        if index % 7 == 0:
            end = start  # a single point
        elif index % 5 == 0:
            end = (start[0], _quarter(rng, -10, HEIGHT))  # vertical
        else:
            end = (_quarter(rng, -10, WIDTH), _quarter(rng, -10, HEIGHT))
        rows.append([*start, *end, int(rng.uniform(0, 7)), *_colour(rng)])
    return np.array(rows, dtype=np.float32)


def _render(wgpu_frame: Any, draw: Any) -> bytes:
    from pyguara.graphics.backends.wgpu import WgpuRenderer

    frame = wgpu_frame(WIDTH, HEIGHT)
    frame.gpu.clear(12, 24, 36, 255)
    draw(WgpuRenderer(frame))
    frame.gpu.end_frame()
    frame.after_frame()
    return bytes(frame.gpu.read_pixels())


def _one_at_a_time(kind: str, rows: np.ndarray) -> Any:
    def draw(renderer: Any) -> None:
        for row in rows.tolist():
            if kind == "rects":
                x, y, w, h, r, g, b, a, outline = row
                renderer.draw_rect(
                    Rect(x, y, w, h),
                    Color(int(r), int(g), int(b), int(a)),
                    int(outline),
                )
            elif kind == "circles":
                x, y, radius, outline, r, g, b, a = row
                renderer.draw_circle(
                    Vector2(x, y),
                    radius,
                    Color(int(r), int(g), int(b), int(a)),
                    int(outline),
                )
            else:
                x1, y1, x2, y2, width, r, g, b, a = row
                renderer.draw_line(
                    Vector2(x1, y1),
                    Vector2(x2, y2),
                    Color(int(r), int(g), int(b), int(a)),
                    int(width),
                )

    return draw


_BUILDERS = {"rects": _rect_rows, "circles": _circle_rows, "lines": _line_rows}


@pytest.mark.parametrize("kind", ["rects", "circles", "lines"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_batch_draws_the_frame_one_call_per_primitive_draws(
    wgpu_frame: Any, kind: str, seed: int
) -> None:
    rows = _BUILDERS[kind](seed, 80)
    expected = _render(wgpu_frame, _one_at_a_time(kind, rows))
    batched = _render(
        wgpu_frame, lambda renderer: getattr(renderer, f"draw_{kind}")(rows)
    )

    assert expected != _render(wgpu_frame, lambda renderer: None), "nothing was drawn"
    differing = sum(
        1
        for at in range(0, len(expected), 4)
        if expected[at : at + 4] != batched[at : at + 4]
    )
    assert differing == 0, f"{differing} pixels differ"


def test_the_order_of_rows_is_the_drawing_order(wgpu_frame: Any) -> None:
    """Overlapping translucent rows composite in row order, as calls do."""
    rows = np.array(
        [
            [10, 10, 60, 60, 255, 0, 0, 128, 0],
            [30, 30, 60, 60, 0, 0, 255, 128, 0],
        ],
        dtype=np.float32,
    )
    forwards = _render(wgpu_frame, lambda renderer: renderer.draw_rects(rows))
    backwards = _render(wgpu_frame, lambda renderer: renderer.draw_rects(rows[::-1]))
    assert forwards != backwards


class TestTheWgpuRendererHasTheCapability:
    def test_it_satisfies_the_protocol(self, wgpu_frame: Any) -> None:
        from pyguara.graphics.backends.wgpu import WgpuRenderer

        assert isinstance(WgpuRenderer(wgpu_frame(8, 8)), PrimitiveArrayRenderer)

    def test_a_ragged_array_is_refused(self, wgpu_frame: Any) -> None:
        from pyguara.graphics.backends.wgpu import WgpuRenderer

        renderer = WgpuRenderer(wgpu_frame(8, 8))
        with pytest.raises(ValueError, match="9 columns"):
            renderer.draw_rects(np.zeros((3, 8), dtype=np.float32))

    def test_an_empty_array_draws_nothing(self, wgpu_frame: Any) -> None:
        from pyguara.graphics.backends.wgpu import WgpuRenderer

        WgpuRenderer(wgpu_frame(8, 8)).draw_lines([])


class _Recorder:
    """A renderer without the capability, recording its calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def draw_rect(self, rect: Rect, color: Color, width: int = 0) -> None:
        self.calls.append(
            ("rect", rect.x, rect.y, rect.width, rect.height, tuple(color), width)
        )

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        self.calls.append(("circle", center.x, center.y, radius, tuple(color), width))

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        self.calls.append(("line", start.x, start.y, end.x, end.y, tuple(color), width))


class TestTheFallbackDrawsOneCallPerRow:
    def test_the_recorder_lacks_the_capability(self) -> None:
        assert not isinstance(_Recorder(), PrimitiveArrayRenderer)

    def test_rects(self) -> None:
        recorder = _Recorder()
        primitives.draw_rects(recorder, [[1, 2, 3, 4, 10, 20, 30, 40, 2]])
        assert recorder.calls == [("rect", 1, 2, 3, 4, (10, 20, 30, 40), 2)]

    def test_circles(self) -> None:
        recorder = _Recorder()
        primitives.draw_circles(recorder, [[5.5, 6.25, 7, 1, 1, 2, 3, 4]])
        assert recorder.calls == [("circle", 5.5, 6.25, 7.0, (1, 2, 3, 4), 1)]

    def test_lines(self) -> None:
        recorder = _Recorder()
        primitives.draw_lines(recorder, [[0, 0, 9, 9, 3, 9, 8, 7, 6]])
        assert recorder.calls == [("line", 0.0, 0.0, 9.0, 9.0, (9, 8, 7, 6), 3)]

    def test_the_capability_is_used_when_present(self, wgpu_frame: Any) -> None:
        from pyguara.graphics.backends.wgpu import WgpuRenderer

        rows = _rect_rows(4, 30)
        expected = _render(wgpu_frame, lambda renderer: renderer.draw_rects(rows))
        helped = _render(
            wgpu_frame, lambda renderer: primitives.draw_rects(renderer, rows)
        )
        assert expected == helped
        assert isinstance(WgpuRenderer(wgpu_frame(8, 8)), PrimitiveArrayRenderer)
