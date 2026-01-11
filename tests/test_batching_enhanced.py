"""Tests for enhanced sprite batching with transforms."""

import pytest
from pyguara.graphics.pipeline.batch import Batcher
from pyguara.graphics.types import RenderCommand
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.common.types import Vector2
from pyguara.resources.types import Texture

# Check if pytest-benchmark is available
try:
    # import pytest_benchmark
    BENCHMARK_AVAILABLE = True
except ImportError:
    BENCHMARK_AVAILABLE = False


class MockTexture(Texture):
    """Mock texture for testing."""

    def __init__(self, name: str = "mock"):
        super().__init__(f"{name}.png")

    @property
    def width(self) -> int:
        return 64

    @property
    def height(self) -> int:
        return 64

    @property
    def native_handle(self):
        return None


def test_batch_without_transforms():
    """Batches without rotation/scale should use fast path."""
    batcher = Batcher()
    camera = Camera2D(800, 600)
    viewport = Viewport.create_fullscreen(800, 600)

    texture = MockTexture("test")
    commands = [
        RenderCommand(
            texture=texture,
            world_position=Vector2(i * 10, 0),
            layer=0,
            z_index=0,
            rotation=0.0,
            scale=Vector2(1, 1),
        )
        for i in range(5)
    ]

    batches = batcher.create_batches(commands, camera, viewport)

    assert len(batches) == 1
    batch = batches[0]
    assert batch.texture == texture
    assert len(batch.destinations) == 5
    assert not batch.transforms_enabled
    assert len(batch.rotations) == 0
    assert len(batch.scales) == 0


def test_batch_with_rotation():
    """Batches with rotation should enable transforms."""
    batcher = Batcher()
    camera = Camera2D(800, 600)
    viewport = Viewport.create_fullscreen(800, 600)

    texture = MockTexture("test")
    commands = [
        RenderCommand(
            texture=texture,
            world_position=Vector2(i * 10, 0),
            layer=0,
            z_index=0,
            rotation=45.0,  # Rotated
            scale=Vector2(1, 1),
        )
        for i in range(5)
    ]

    batches = batcher.create_batches(commands, camera, viewport)

    assert len(batches) == 1
    batch = batches[0]
    assert batch.transforms_enabled
    assert len(batch.rotations) == 5
    assert all(r == 45.0 for r in batch.rotations)
    assert len(batch.scales) == 5


def test_batch_with_scale():
    """Batches with scale should enable transforms."""
    batcher = Batcher()
    camera = Camera2D(800, 600)
    viewport = Viewport.create_fullscreen(800, 600)

    texture = MockTexture("test")
    commands = [
        RenderCommand(
            texture=texture,
            world_position=Vector2(i * 10, 0),
            layer=0,
            z_index=0,
            rotation=0.0,
            scale=Vector2(2, 2),  # Scaled
        )
        for i in range(5)
    ]

    batches = batcher.create_batches(commands, camera, viewport)

    assert len(batches) == 1
    batch = batches[0]
    assert batch.transforms_enabled
    assert len(batch.scales) == 5
    assert all(s == (2.0, 2.0) for s in batch.scales)


def test_batch_mixed_transforms():
    """Batch with some transformed and some non-transformed sprites."""
    batcher = Batcher()
    camera = Camera2D(800, 600)
    viewport = Viewport.create_fullscreen(800, 600)

    texture = MockTexture("test")
    commands = [
        RenderCommand(
            texture=texture,
            world_position=Vector2(0, 0),
            layer=0,
            z_index=0,
            rotation=0.0,
            scale=Vector2(1, 1),
        ),
        RenderCommand(
            texture=texture,
            world_position=Vector2(10, 0),
            layer=0,
            z_index=0,
            rotation=45.0,  # Rotated
            scale=Vector2(1, 1),
        ),
        RenderCommand(
            texture=texture,
            world_position=Vector2(20, 0),
            layer=0,
            z_index=0,
            rotation=0.0,
            scale=Vector2(2, 2),  # Scaled
        ),
    ]

    batches = batcher.create_batches(commands, camera, viewport)

    assert len(batches) == 1
    batch = batches[0]
    assert batch.transforms_enabled
    assert len(batch.rotations) == 3
    assert batch.rotations[0] == 0.0
    assert batch.rotations[1] == 45.0
    assert batch.rotations[2] == 0.0
    assert len(batch.scales) == 3
    assert batch.scales[0] == (1.0, 1.0)
    assert batch.scales[1] == (1.0, 1.0)
    assert batch.scales[2] == (2.0, 2.0)


def test_multiple_textures_create_separate_batches():
    """Different textures should create separate batches."""
    batcher = Batcher()
    camera = Camera2D(800, 600)
    viewport = Viewport.create_fullscreen(800, 600)

    texture1 = MockTexture("tex1")
    texture2 = MockTexture("tex2")

    commands = [
        RenderCommand(
            texture=texture1,
            world_position=Vector2(0, 0),
            layer=0,
            z_index=0,
        ),
        RenderCommand(
            texture=texture1,
            world_position=Vector2(10, 0),
            layer=0,
            z_index=0,
        ),
        RenderCommand(
            texture=texture2,
            world_position=Vector2(20, 0),
            layer=0,
            z_index=0,
        ),
        RenderCommand(
            texture=texture1,
            world_position=Vector2(30, 0),
            layer=0,
            z_index=0,
        ),
    ]

    batches = batcher.create_batches(commands, camera, viewport)

    # Should create 3 batches: tex1, tex2, tex1
    assert len(batches) == 3
    assert batches[0].texture == texture1
    assert len(batches[0].destinations) == 2
    assert batches[1].texture == texture2
    assert len(batches[1].destinations) == 1
    assert batches[2].texture == texture1
    assert len(batches[2].destinations) == 1


def test_empty_command_list_returns_static_batches_only():
    """Empty commands should return only static batches."""
    batcher = Batcher()
    camera = Camera2D(800, 600)
    viewport = Viewport.create_fullscreen(800, 600)

    batches = batcher.create_batches([], camera, viewport)

    # Should return empty list (no static batches registered)
    assert len(batches) == 0


@pytest.mark.skipif(not BENCHMARK_AVAILABLE, reason="pytest-benchmark not installed")
@pytest.mark.benchmark
def test_batching_performance_simple_sprites(benchmark):
    """Benchmark batching performance for simple sprites (fast path)."""
    batcher = Batcher()
    camera = Camera2D(800, 600)
    viewport = Viewport.create_fullscreen(800, 600)

    texture = MockTexture("test")
    commands = [
        RenderCommand(
            texture=texture,
            world_position=Vector2(i * 10, i * 10),
            layer=0,
            z_index=0,
            rotation=0.0,
            scale=Vector2(1, 1),
        )
        for i in range(1000)
    ]

    def batch_all():
        return batcher.create_batches(commands, camera, viewport)

    result = benchmark(batch_all)

    # Should create 1 batch efficiently
    assert len(result) == 1
    assert not result[0].transforms_enabled


@pytest.mark.skipif(not BENCHMARK_AVAILABLE, reason="pytest-benchmark not installed")
@pytest.mark.benchmark
def test_batching_performance_transformed_sprites(benchmark):
    """Benchmark batching performance for transformed sprites."""
    batcher = Batcher()
    camera = Camera2D(800, 600)
    viewport = Viewport.create_fullscreen(800, 600)

    texture = MockTexture("test")
    commands = [
        RenderCommand(
            texture=texture,
            world_position=Vector2(i * 10, i * 10),
            layer=0,
            z_index=0,
            rotation=i * 1.0,
            scale=Vector2(1 + i * 0.01, 1),
        )
        for i in range(1000)
    ]

    def batch_all():
        return batcher.create_batches(commands, camera, viewport)

    result = benchmark(batch_all)

    # Should create 1 batch with transforms
    assert len(result) == 1
    assert result[0].transforms_enabled
    assert len(result[0].rotations) == 1000
    assert len(result[0].scales) == 1000
