"""CPU-side render cost: sorting, batching, and what culling would save.

Everything here runs without a GPU, so these are the portable numbers.

`test_the_screen_transform_is_not_done_with_vectors` compares two
implementations in one process, which cancels machine speed. The
batcher's float arithmetic gives bit-identical output to `Vector2`
arithmetic, so only a timing can notice it being undone.

The culling probe at the bottom asserts nothing. It records what
sorting and packing off-screen commands costs.
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
from pyguara.graphics.types import RenderBatch, RenderCommand
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


def _batches_with_vector_arithmetic(
    sorted_commands: list[RenderCommand], camera: Camera2D, viewport: Viewport
) -> list[RenderBatch]:
    """The batcher's inner loop, written with `Vector2` arithmetic.

    The reference the shipped batcher must beat. It differs from
    `Batcher.create_batches` in two ways, both giving identical batches:
    the screen position is `(world * zoom) + offset`, and the optional
    columns are collected for every command and discarded if unused.

    It does not break batches: it is timed against the single-texture
    case, where the real batcher does not either.
    """
    offset = camera.screen_offset(viewport)
    zoom = camera.zoom
    opaque_white = Color(255, 255, 255, 255)

    destinations: list[tuple[float, float]] = []
    rotations: list[float] = []
    scales: list[tuple[float, float]] = []
    colors: list[tuple[int, int, int, int]] = []
    has_transforms = False
    has_colors = False

    for cmd in sorted_commands:
        screen_pos = (cmd.world_position * zoom) + offset
        destinations.append((screen_pos.x, screen_pos.y))
        rotations.append(cmd.rotation)
        scales.append((cmd.scale.x, cmd.scale.y))
        colors.append((cmd.color.r, cmd.color.g, cmd.color.b, cmd.color.a))
        if cmd.rotation != 0.0 or cmd.scale.x != 1.0 or cmd.scale.y != 1.0:
            has_transforms = True
        if cmd.color != opaque_white:
            has_colors = True

    return [
        RenderBatch(
            texture=sorted_commands[0].texture,
            destinations=destinations,
            rotations=rotations if has_transforms else [],
            scales=scales if has_transforms else [],
            transforms_enabled=has_transforms,
            colors=colors if has_colors else [],
            colors_enabled=has_colors,
        )
    ]


@pytest.mark.performance
def test_the_screen_transform_is_not_done_with_vectors() -> None:
    """The batcher's largest win, which its output cannot show.

    `(world_position * zoom) + offset` allocates two `Vector2` objects per
    command for four float operations. Doing it on the components gives
    bit-identical destinations, so every correctness test passes either
    way.

    Both loops run in this process on the same commands, so machine speed
    cancels. The bound is loose: it is here to notice the optimisation
    being removed, not to pin its size.
    """
    commands = _commands(4000)
    camera = Camera2D(800, 600)
    viewport = Viewport.create_fullscreen(800, 600)
    batcher = Batcher()

    shipped = measure(lambda: batcher.create_batches(commands, camera, viewport))
    naive = measure(lambda: _batches_with_vector_arithmetic(commands, camera, viewport))

    assert shipped < naive * 0.5, (
        f"the batcher took {shipped * 1e3:.2f}ms against "
        f"{naive * 1e3:.2f}ms for the same loop written with Vector2 "
        f"arithmetic and eager columns ({naive / shipped:.1f}x). Expected "
        "around 5x. Something has put the per-command allocations back."
    )


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("count", [1000, 5000, 20000])
def test_sweep_cpu_frame(benchmark, count: int) -> None:
    """Report the whole CPU-side frame: submit, sort, batch, pack.

    The number ADR 0004's item 4 is priced against, which is why it is
    one benchmark rather than four. A native render batcher would replace
    all four of these stages at once, so pricing the port needs the sum
    and not the pieces -- quoting the batcher alone would be the mistake
    Decision 7 names.

    Transformed and tinted, which is the shape that exercises every
    column, and one texture, which is the shape a batched frame is
    supposed to have.
    """
    commands = _commands(count, transformed=True, tinted=True)
    sprites = [
        Sprite(
            texture=command.texture,
            position=command.world_position,
            rotation=command.rotation,
            scale=command.scale,
            color=command.color,
        )
        for command in commands
    ]
    system = RenderSystem(_FakeTexture())  # backend is never touched by submit
    camera = Camera2D(1280, 720)
    viewport = Viewport.create_fullscreen(1280, 720)
    batcher = Batcher()

    def frame() -> None:
        system._queue.clear()
        for sprite in sprites:
            system.submit(sprite)
        system._queue.sort()
        batcher.create_batches(system._queue.commands, camera, viewport)

    benchmark.pedantic(frame, rounds=5, iterations=1)


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("textures", [1, 10])
@pytest.mark.parametrize("count", [1000, 5000, 20000])
def test_sweep_batch_by_texture_count(benchmark, count: int, textures: int) -> None:
    """Report batching cost against both command count and batch breaks.

    The existing break-cost sweep holds the command count at 8000. This
    one varies both, because the two interact: removing the per-command
    allocations is 5x at 20,000 commands in one batch and 1.7x across ten
    textures, where a break on nearly every command moves the cost into
    `RenderBatch` construction instead.
    """
    commands = _commands(count, textures=textures)
    benchmark.pedantic(lambda: _batch(commands), rounds=5, iterations=1)
