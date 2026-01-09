import pygame
import pytest
from pyguara.graphics.spritesheet import SpriteSheet
from pyguara.graphics.backends.pygame.types import PygameTexture


@pytest.fixture
def sample_texture():
    """Creates a 64x64 texture with 4 distinct 32x32 colored quadrants."""
    surf = pygame.Surface((64, 64), flags=pygame.SRCALPHA)

    # Q1: Top-Left (Red)
    pygame.draw.rect(surf, (255, 0, 0), (0, 0, 32, 32))
    # Q2: Top-Right (Green)
    pygame.draw.rect(surf, (0, 255, 0), (32, 0, 32, 32))
    # Q3: Bottom-Left (Blue)
    pygame.draw.rect(surf, (0, 0, 255), (0, 32, 32, 32))
    # Q4: Bottom-Right (White)
    pygame.draw.rect(surf, (255, 255, 255), (32, 32, 32, 32))

    return PygameTexture("test_sheet.png", surf)


def test_spritesheet_slice_grid_full(sample_texture):
    """Test slicing the entire sheet."""
    sheet = SpriteSheet(sample_texture)

    frames = sheet.slice_grid(32, 32)

    # Should result in 4 frames
    assert len(frames) == 4

    # Check dimensions
    for f in frames:
        assert f.width == 32
        assert f.height == 32

    # Verify content of each frame
    # Frame 0: Red
    assert frames[0].native_handle.get_at((10, 10)) == (255, 0, 0, 255)
    # Frame 1: Green
    assert frames[1].native_handle.get_at((10, 10)) == (0, 255, 0, 255)
    # Frame 2: Blue
    assert frames[2].native_handle.get_at((10, 10)) == (0, 0, 255, 255)
    # Frame 3: White
    assert frames[3].native_handle.get_at((10, 10)) == (255, 255, 255, 255)


def test_spritesheet_slice_limited_count(sample_texture):
    """Test limiting the number of frames."""
    sheet = SpriteSheet(sample_texture)
    frames = sheet.slice_grid(32, 32, count=2)

    assert len(frames) == 2
    # Should have Red and Green
    assert frames[0].native_handle.get_at((0, 0)) == (255, 0, 0, 255)
    assert frames[1].native_handle.get_at((0, 0)) == (0, 255, 0, 255)


def test_spritesheet_uneven_dimensions():
    """Test slicing where sheet size isn't a perfect multiple (should truncate)."""
    surf = pygame.Surface((70, 70))
    tex = PygameTexture("uneven", surf)
    sheet = SpriteSheet(tex)

    # 32x32 frames.
    # Cols: 70 // 32 = 2
    # Rows: 70 // 32 = 2
    # Total: 4
    frames = sheet.slice_grid(32, 32)
    assert len(frames) == 4
