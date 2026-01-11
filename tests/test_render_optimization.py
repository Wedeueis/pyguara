"""Tests for P2-001: RenderSystem hot-loop optimization."""

import dis
import pytest
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.components.geometry import Box, Circle
from pyguara.graphics.components.particles import Particle
from pyguara.graphics.pipeline.render_system import RenderSystem
from pyguara.graphics.protocols import Renderable
from pyguara.common.types import Vector2, Color
from pyguara.resources.types import Texture

# Check if pytest-benchmark is available
try:
    # import pytest_benchmark
    BENCHMARK_AVAILABLE = True
except ImportError:
    BENCHMARK_AVAILABLE = False


class MockTexture(Texture):
    """Mock texture for testing."""

    def __init__(self):
        super().__init__("mock_texture.png")
        self._width = 64
        self._height = 64

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def native_handle(self):
        """Mock native handle."""
        return None


def test_sprite_implements_renderable():
    """Sprite fully implements the Renderable protocol."""
    texture = MockTexture()
    sprite = Sprite(texture=texture)

    # Verify Sprite implements Renderable protocol
    assert isinstance(sprite, Renderable)

    # Verify all required attributes exist
    assert hasattr(sprite, "texture")
    assert hasattr(sprite, "position")
    assert hasattr(sprite, "layer")
    assert hasattr(sprite, "z_index")
    assert hasattr(sprite, "rotation")
    assert hasattr(sprite, "scale")

    # Verify default values
    assert sprite.position == Vector2.zero()
    assert sprite.rotation == 0.0
    assert sprite.scale == Vector2(1, 1)

    # Verify they can be set
    sprite.position = Vector2(100, 200)
    sprite.rotation = 45.0
    sprite.scale = Vector2(2, 2)
    assert sprite.position == Vector2(100, 200)
    assert sprite.rotation == 45.0
    assert sprite.scale == Vector2(2, 2)


def test_particle_has_rotation_and_scale():
    """Particle must have rotation and scale attributes (Renderable protocol)."""
    particle = Particle(
        position=Vector2(0, 0), velocity=Vector2(0, 0), life=1.0, texture=MockTexture()
    )

    # Verify attributes exist
    assert hasattr(particle, "rotation")
    assert hasattr(particle, "scale")

    # Verify default values
    assert particle.rotation == 0.0
    assert particle.scale == Vector2(1, 1)


def test_geometry_has_rotation_and_scale():
    """Geometry components must have rotation and scale attributes."""
    box = Box(width=100, height=100, color=Color(255, 0, 0))

    assert hasattr(box, "rotation")
    assert hasattr(box, "scale")

    circle = Circle(radius=50, color=Color(0, 255, 0))

    assert hasattr(circle, "rotation")
    assert hasattr(circle, "scale")


def test_render_system_submit_no_getattr():
    """Verify RenderSystem.submit() doesn't use getattr in hot path."""
    # Disassemble the submit method bytecode
    bytecode = dis.Bytecode(RenderSystem.submit)
    instructions = list(bytecode)

    # Check that no LOAD_GLOBAL 'getattr' exists
    getattr_found = any(
        instr.opname == "LOAD_GLOBAL" and instr.argval == "getattr"
        for instr in instructions
    )

    assert not getattr_found, (
        "RenderSystem.submit() should not use getattr for performance"
    )


def test_all_renderables_implement_protocol():
    """All visual classes (Sprite, Box, Circle) implement complete Renderable protocol."""
    texture = MockTexture()

    # Test all renderable types
    renderables = [
        Sprite(texture=texture, position=Vector2(10, 20)),
        Box(width=100, height=100, color=Color(255, 0, 0)),
        Circle(radius=50, color=Color(0, 255, 0)),
    ]

    for renderable in renderables:
        # Check structural subtyping (protocol compliance)
        assert isinstance(renderable, Renderable)

        # Verify all required properties exist
        assert hasattr(renderable, "texture")
        assert hasattr(renderable, "position")
        assert hasattr(renderable, "layer")
        assert hasattr(renderable, "z_index")
        assert hasattr(renderable, "rotation")
        assert hasattr(renderable, "scale")

        # Verify they're accessible (no exceptions)
        _ = renderable.texture
        _ = renderable.position
        _ = renderable.layer
        _ = renderable.z_index
        _ = renderable.rotation
        _ = renderable.scale


@pytest.mark.skipif(not BENCHMARK_AVAILABLE, reason="pytest-benchmark not installed")
@pytest.mark.benchmark
def test_render_submission_performance(benchmark):
    """Benchmark render submission with direct attribute access.

    This test verifies that P2-001 optimization (removing getattr) provides
    fast submission performance. Expected: < 1ms for 100 sprites.
    """
    from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
    import pygame

    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    backend = PygameBackend(screen)
    render_system = RenderSystem(backend)

    # Create test sprites (now fully Renderable!)
    texture = MockTexture()
    sprites = [
        Sprite(
            texture=texture,
            position=Vector2(i * 10, i * 10),
            rotation=i * 0.1,
            scale=Vector2(1 + i * 0.01, 1),
        )
        for i in range(100)
    ]

    # Benchmark submission
    def submit_all():
        for sprite in sprites:
            render_system.submit(sprite)

    # pytest-benchmark will run this multiple times and report stats
    benchmark(submit_all)

    pygame.quit()
