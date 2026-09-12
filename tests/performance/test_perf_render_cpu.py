"""CPU-side render cost: sorting, batching, and what culling would save.

Everything here runs without a GPU, which makes these the **portable**
numbers -- the ones worth quoting as an engine limit. GL timings depend on
the driver underneath (see `test_perf_gl.py`), so they describe a machine
rather than the engine.

The culling probe at the bottom asserts nothing on purpose. `RenderSystem`
has no visibility rejection at all: every submitted command is sorted,
transformed and packed whether or not it is on screen. That is a
defensible trade for a game where everything is on screen anyway, and a
bad one for a large scrolling world. Rather than argue about it, this
records what the waste actually costs, so that whoever proposes culling
has a number to beat.
"""

from __future__ import annotations

import pytest

from pyguara.common.types import Color, Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.pipeline.batch import Batcher
from pyguara.graphics.pipeline.queue import RenderQueue
from pyguara.graphics.pipeline.render_system import RenderSystem
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.types import RenderCommand
from pyguara.resources.types import Texture
from tests.performance.conftest import assert_scales_no_worse_than, measure


class _FakeTexture(Texture):
    """A texture that exists only to be an identity for batch grouping."""

    def __init__(self, name: str = "bench") -> None:
        self._name = name

    @property
    def name(self) -> str:
        """Texture identity -- what the batcher groups on."""
        return self._name

    @property
    def width(self) -> int:
        """Nominal width; nothing here ever rasterises."""
        return 32

    @property
    def height(self) -> int:
        """Nominal height; nothing here ever rasterises."""
        return 32

    @property
    def native_handle(self) -> object:
        """No backend resource -- nothing here ever draws."""
        return None


def _commands(
    count: int,
    *,
    textures: int = 1,
    transformed: bool = False,
    tinted: bool = False,
    spread: float = 10_000.0,
) -> list[RenderCommand]:
    """Build `count` render commands.

    Args:
        count: How many commands.
        textures: How many distinct textures to cycle through. More
            textures means more batch breaks.
        transformed: Give each command a rotation and scale, which forces
            the batcher's transform path.
        tinted: Give each command a non-white colour, which forces the
            colour path.
        spread: Width and height of the area positions are spread over.

    Returns:
        The commands, ready to batch.
    """
    pool = [_FakeTexture(f"t{i}") for i in range(textures)]
    step = spread / max(count, 1)
    return [
        RenderCommand(
            texture=pool[i % textures],
            world_position=Vector2(i * step, i * step),
            layer=i % 4,
            z_index=float(i % 32),
            rotation=(i * 1.0) if transformed else 0.0,
            scale=Vector2(1 + i * 0.001, 1) if transformed else Vector2(1, 1),
            color=Color(255, i % 256, 128, 255)
            if tinted
            else Color(255, 255, 255, 255),
        )
        for i in range(count)
    ]


def _batch(commands: list[RenderCommand]) -> None:
    """Run the batcher over `commands` against a fullscreen camera."""
    batcher = Batcher()
    batcher.create_batches(
        commands, Camera2D(800, 600), Viewport.create_fullscreen(800, 600)
    )


def _sort(commands: list[RenderCommand]) -> None:
    """Push every command into a queue and sort it, as a frame would."""
    queue = RenderQueue()
    for command in commands:
        queue.push(command)
    queue.sort()


@pytest.mark.performance
def test_batching_is_linear_in_command_count() -> None:
    """4x the sprites should cost about 4x to batch."""
    small = _commands(500)
    large = _commands(2000)

    assert_scales_no_worse_than(
        small=measure(lambda: _batch(small)),
        large=measure(lambda: _batch(large)),
        factor=4,
        limit=8.0,
        what="Batcher.create_batches",
    )


@pytest.mark.performance
def test_sorting_is_near_linear_in_command_count() -> None:
    """Timsort over 4x the commands should stay well short of quadratic."""
    small = _commands(500)
    large = _commands(2000)

    assert_scales_no_worse_than(
        small=measure(lambda: _sort(small)),
        large=measure(lambda: _sort(large)),
        factor=4,
        limit=8.0,
        what="RenderQueue.sort",
    )


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("count", [1000, 5000, 20000])
def test_sweep_batch_one_texture(benchmark, count: int) -> None:
    """Report batching cost on the fast path -- one texture, no transforms."""
    commands = _commands(count)
    benchmark.pedantic(lambda: _batch(commands), rounds=5, iterations=1)


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("count", [1000, 5000, 20000])
def test_sweep_batch_transformed(benchmark, count: int) -> None:
    """Report batching cost on the transform path."""
    commands = _commands(count, transformed=True)
    benchmark.pedantic(lambda: _batch(commands), rounds=5, iterations=1)


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("count", [1000, 5000, 20000])
def test_sweep_batch_tinted(benchmark, count: int) -> None:
    """Report batching cost when every command carries a tint.

    Worth reporting separately: the colour path is collected on every
    frame regardless, and today the ModernGL backend discards it.
    """
    commands = _commands(count, tinted=True)
    benchmark.pedantic(lambda: _batch(commands), rounds=5, iterations=1)


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("textures", [1, 10, 50])
def test_sweep_batch_break_cost(benchmark, textures: int) -> None:
    """Report what texture switching costs at a fixed 8000 commands."""
    commands = _commands(8000, textures=textures)
    benchmark.pedantic(lambda: _batch(commands), rounds=5, iterations=1)


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("count", [2000, 8000])
def test_sweep_sort(benchmark, count: int) -> None:
    """Report sort cost by command count."""
    commands = _commands(count)
    benchmark.pedantic(lambda: _sort(commands), rounds=5, iterations=1)


@pytest.mark.performance
@pytest.mark.slow
def test_sweep_culling_headroom(benchmark) -> None:
    """Report the cost of sorting and batching 8000 mostly-offscreen commands.

    Asserts nothing. This is the number a visibility-culling change would
    have to beat: with roughly a tenth of these on screen, the difference
    between this figure and the same work at 800 commands is what culling
    could recover.
    """
    commands = _commands(8000, spread=100_000.0)

    def frame() -> None:
        _sort(commands)
        _batch(commands)

    benchmark.pedantic(frame, rounds=5, iterations=1)


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("count", [1000, 5000, 20000])
def test_sweep_render_submission(benchmark, count: int) -> None:
    """Report the cost of submitting `count` renderables to the queue.

    Headless on purpose. `RenderSystem.submit` builds a `RenderCommand` and
    pushes it -- it never touches the backend -- so the benchmark this
    replaces was standing up a real pygame display to measure code that
    could not observe one.
    """
    texture = _FakeTexture()
    sprites = [
        Sprite(
            texture=texture,
            position=Vector2(i * 1.0, i * 1.0),
            rotation=i * 0.1,
            scale=Vector2(1 + i * 0.0001, 1),
        )
        for i in range(count)
    ]
    system = RenderSystem(_FakeTexture())  # backend is never touched by submit

    def submit_all() -> None:
        for sprite in sprites:
            system.submit(sprite)

    benchmark.pedantic(submit_all, rounds=5, iterations=1)
