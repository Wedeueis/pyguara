import pytest
from PIL import Image

from pyguara.graphics.spritesheet import SpriteSheet
from pyguara.graphics.backends.pygame.types import PygameTextureFactory


@pytest.fixture
def texture_factory():
    """Create a PygameTextureFactory for testing."""
    return PygameTextureFactory()


@pytest.fixture
def sample_image():
    """Creates a 64x64 PIL Image with 4 distinct 32x32 colored quadrants."""
    img = Image.new("RGBA", (64, 64))

    # Q1: Top-Left (Red)
    for y in range(32):
        for x in range(32):
            img.putpixel((x, y), (255, 0, 0, 255))

    # Q2: Top-Right (Green)
    for y in range(32):
        for x in range(32, 64):
            img.putpixel((x, y), (0, 255, 0, 255))

    # Q3: Bottom-Left (Blue)
    for y in range(32, 64):
        for x in range(32):
            img.putpixel((x, y), (0, 0, 255, 255))

    # Q4: Bottom-Right (White)
    for y in range(32, 64):
        for x in range(32, 64):
            img.putpixel((x, y), (255, 255, 255, 255))

    return img


def test_spritesheet_slice_grid_full(sample_image, texture_factory):
    """Test slicing the entire sheet."""
    sheet = SpriteSheet.from_image(sample_image, texture_factory, "test_sheet.png")

    frames = sheet.slice_grid(32, 32)

    # Should result in 4 frames
    assert len(frames) == 4

    # Check dimensions
    for f in frames:
        assert f.width == 32
        assert f.height == 32

    # Verify content of each frame by checking pixel colors
    # Frame 0: Red
    assert frames[0].native_handle.get_at((10, 10)) == (255, 0, 0, 255)
    # Frame 1: Green
    assert frames[1].native_handle.get_at((10, 10)) == (0, 255, 0, 255)
    # Frame 2: Blue
    assert frames[2].native_handle.get_at((10, 10)) == (0, 0, 255, 255)
    # Frame 3: White
    assert frames[3].native_handle.get_at((10, 10)) == (255, 255, 255, 255)


def test_spritesheet_slice_limited_count(sample_image, texture_factory):
    """Test limiting the number of frames."""
    sheet = SpriteSheet.from_image(sample_image, texture_factory, "test_sheet.png")
    frames = sheet.slice_grid(32, 32, count=2)

    assert len(frames) == 2
    # Should have Red and Green
    assert frames[0].native_handle.get_at((0, 0)) == (255, 0, 0, 255)
    assert frames[1].native_handle.get_at((0, 0)) == (0, 255, 0, 255)


def test_spritesheet_uneven_dimensions(texture_factory):
    """Test slicing where sheet size isn't a perfect multiple (should truncate)."""
    img = Image.new("RGBA", (70, 70), (128, 128, 128, 255))
    sheet = SpriteSheet.from_image(img, texture_factory, "uneven")

    # 32x32 frames.
    # Cols: 70 // 32 = 2
    # Rows: 70 // 32 = 2
    # Total: 4
    frames = sheet.slice_grid(32, 32)
    assert len(frames) == 4


def test_spritesheet_properties(sample_image, texture_factory):
    """Test sprite sheet width and height properties."""
    sheet = SpriteSheet.from_image(sample_image, texture_factory, "test_sheet.png")

    assert sheet.width == 64
    assert sheet.height == 64


def test_spritesheet_frames_property(sample_image, texture_factory):
    """Test that frames property returns sliced frames."""
    sheet = SpriteSheet.from_image(sample_image, texture_factory, "test_sheet.png")

    # Before slicing, frames should be empty
    assert sheet.frames == []

    # After slicing, frames should be populated
    sheet.slice_grid(32, 32)
    assert len(sheet.frames) == 4


def test_spritesheet_slice_regions(sample_image, texture_factory):
    """Test slicing specific regions from the sprite sheet."""
    sheet = SpriteSheet.from_image(sample_image, texture_factory, "test_sheet.png")

    # Define custom regions (x, y, width, height)
    regions = [
        (0, 0, 32, 32),  # Top-left (Red)
        (32, 32, 32, 32),  # Bottom-right (White)
    ]

    frames = sheet.slice_regions(regions)

    assert len(frames) == 2
    # First region is Red
    assert frames[0].native_handle.get_at((10, 10)) == (255, 0, 0, 255)
    # Second region is White
    assert frames[1].native_handle.get_at((10, 10)) == (255, 255, 255, 255)
