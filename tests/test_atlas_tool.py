"""Tests for sprite atlas generation and loading."""

import pytest
import json
import tempfile
from pathlib import Path
import pygame

from pyguara.graphics.atlas import Atlas, AtlasRegion
from pyguara.common.types import Rect
from pyguara.resources.types import Texture


@pytest.fixture(scope="module")
def pygame_init():
    """Initialize pygame for tests that need it."""
    pygame.init()
    pygame.display.set_mode((1, 1))  # Minimal display for testing
    yield
    pygame.quit()

# Only run atlas generator tests if PIL is available
PIL_AVAILABLE = False
try:
    from PIL import Image
    from tools.atlas_generator import AtlasGenerator, Shelf, PackedSprite

    PIL_AVAILABLE = True
except ImportError:
    pass


class MockTexture(Texture):
    """Mock texture for testing."""

    def __init__(self, path: str = "mock.png", w: int = 64, h: int = 64):
        super().__init__(path)
        self._width = w
        self._height = h

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def native_handle(self):
        return None


# ===== Atlas Data Structure Tests =====


def test_atlas_region_creation():
    """AtlasRegion should store sprite metadata correctly."""
    rect = Rect(10, 20, 64, 64)
    region = AtlasRegion(name="player", rect=rect, original_size=(64, 64))

    assert region.name == "player"
    assert region.rect == rect
    assert region.original_size == (64, 64)


def test_atlas_creation():
    """Atlas should store texture and regions."""
    texture = MockTexture("atlas.png", 512, 512)
    regions = {
        "sprite1": AtlasRegion("sprite1", Rect(0, 0, 64, 64), (64, 64)),
        "sprite2": AtlasRegion("sprite2", Rect(64, 0, 32, 32), (32, 32)),
    }

    atlas = Atlas(texture, regions)

    assert atlas.texture == texture
    assert len(atlas.regions) == 2
    assert atlas.region_count == 2


def test_atlas_get_region():
    """Atlas should retrieve regions by name."""
    texture = MockTexture()
    region1 = AtlasRegion("player", Rect(0, 0, 64, 64), (64, 64))
    region2 = AtlasRegion("enemy", Rect(64, 0, 32, 32), (32, 32))
    atlas = Atlas(texture, {"player": region1, "enemy": region2})

    retrieved = atlas.get_region("player")
    assert retrieved == region1

    missing = atlas.get_region("nonexistent")
    assert missing is None


def test_atlas_get_rect():
    """Atlas should retrieve region rects by name."""
    texture = MockTexture()
    rect1 = Rect(10, 20, 64, 64)
    region1 = AtlasRegion("player", rect1, (64, 64))
    atlas = Atlas(texture, {"player": region1})

    retrieved_rect = atlas.get_rect("player")
    assert retrieved_rect == rect1

    missing_rect = atlas.get_rect("nonexistent")
    assert missing_rect is None


def test_atlas_has_region():
    """Atlas should check for region existence."""
    texture = MockTexture()
    region = AtlasRegion("player", Rect(0, 0, 64, 64), (64, 64))
    atlas = Atlas(texture, {"player": region})

    assert atlas.has_region("player") is True
    assert atlas.has_region("enemy") is False


def test_atlas_list_regions():
    """Atlas should list all region names."""
    texture = MockTexture()
    regions = {
        "sprite1": AtlasRegion("sprite1", Rect(0, 0, 64, 64), (64, 64)),
        "sprite2": AtlasRegion("sprite2", Rect(64, 0, 32, 32), (32, 32)),
        "sprite3": AtlasRegion("sprite3", Rect(96, 0, 16, 16), (16, 16)),
    }
    atlas = Atlas(texture, regions)

    names = atlas.list_regions()
    assert len(names) == 3
    assert "sprite1" in names
    assert "sprite2" in names
    assert "sprite3" in names


# ===== Atlas Generator Tests (require PIL) =====


@pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL not available")
def test_shelf_packing():
    """Shelf should pack sprites horizontally."""
    shelf = Shelf(y=0, height=64, max_width=256)

    assert shelf.can_fit(64, 64) is True
    assert shelf.can_fit(256, 64) is True
    assert shelf.can_fit(257, 64) is False  # Too wide
    assert shelf.can_fit(64, 65) is False  # Too tall

    x1 = shelf.add(64)
    assert x1 == 0

    x2 = shelf.add(64)
    assert x2 == 64

    assert shelf.can_fit(129, 64) is False  # Remaining space only 128


@pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL not available")
def test_atlas_generator_load_images():
    """Atlas generator should load images from directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create test images
        for i in range(3):
            img = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
            img.save(tmpdir_path / f"sprite{i}.png")

        # Also add an unsupported file
        (tmpdir_path / "readme.txt").write_text("test")

        generator = AtlasGenerator()
        images = generator.load_images(tmpdir_path)

        assert len(images) == 3
        assert images[0][0] == "sprite0"
        assert images[1][0] == "sprite1"
        assert images[2][0] == "sprite2"


@pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL not available")
def test_atlas_generator_load_images_empty_dir():
    """Atlas generator should raise error for empty directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        generator = AtlasGenerator()

        with pytest.raises(ValueError, match="No valid images found"):
            generator.load_images(Path(tmpdir))


@pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL not available")
def test_atlas_generator_load_images_invalid_path():
    """Atlas generator should raise error for invalid path."""
    generator = AtlasGenerator()

    with pytest.raises(ValueError, match="does not exist"):
        generator.load_images(Path("/nonexistent/path"))


@pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL not available")
def test_atlas_generator_pack():
    """Atlas generator should pack sprites into atlas."""
    # Create test images
    images = [
        ("sprite1", Image.new("RGBA", (64, 64), (255, 0, 0, 255))),
        ("sprite2", Image.new("RGBA", (32, 32), (0, 255, 0, 255))),
        ("sprite3", Image.new("RGBA", (16, 16), (0, 0, 255, 255))),
    ]

    generator = AtlasGenerator(atlas_size=256, padding=2)
    atlas_image, metadata = generator.pack(images)

    # Check atlas image
    assert atlas_image.size == (256, 256)
    assert atlas_image.mode == "RGBA"

    # Check metadata
    assert metadata["atlas_size"] == [256, 256]
    assert metadata["padding"] == 2
    assert metadata["sprite_count"] == 3
    assert "regions" in metadata

    # Check regions
    regions = metadata["regions"]
    assert "sprite1" in regions
    assert "sprite2" in regions
    assert "sprite3" in regions

    # Check region data
    sprite1 = regions["sprite1"]
    assert sprite1["width"] == 64
    assert sprite1["height"] == 64
    assert sprite1["original_size"] == [64, 64]


@pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL not available")
def test_atlas_generator_pack_too_large():
    """Atlas generator should raise error if sprites don't fit."""
    # Create an image that's too large for a 128x128 atlas
    images = [("huge", Image.new("RGBA", (256, 256), (255, 0, 0, 255)))]

    generator = AtlasGenerator(atlas_size=128, padding=0)

    with pytest.raises(ValueError, match="too small to fit all sprites"):
        generator.pack(images)


@pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL not available")
def test_atlas_generator_generate():
    """Atlas generator should create atlas and metadata files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create input directory with test images
        input_dir = tmpdir_path / "sprites"
        input_dir.mkdir()

        for i in range(3):
            img = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
            img.save(input_dir / f"sprite{i}.png")

        # Output paths
        output_image = tmpdir_path / "atlas.png"
        output_metadata = tmpdir_path / "atlas.json"

        # Generate atlas
        generator = AtlasGenerator(atlas_size=256, padding=2)
        generator.generate(input_dir, output_image, output_metadata)

        # Verify files were created
        assert output_image.exists()
        assert output_metadata.exists()

        # Verify image
        atlas_img = Image.open(output_image)
        assert atlas_img.size == (256, 256)

        # Verify metadata
        with open(output_metadata, "r") as f:
            metadata = json.load(f)

        assert metadata["sprite_count"] == 3
        assert len(metadata["regions"]) == 3


# ===== ResourceManager Atlas Loading Tests =====


def test_resource_manager_load_atlas_invalid_metadata(tmp_path):
    """ResourceManager should raise error for invalid metadata."""
    from pyguara.resources.manager import ResourceManager
    from pyguara.graphics.backends.pygame.loaders import PygameImageLoader

    # Create a temporary atlas image
    atlas_path = tmp_path / "atlas.png"

    # Create metadata with missing 'regions' key
    metadata_path = tmp_path / "atlas.json"
    metadata_path.write_text('{"atlas_size": [256, 256]}')

    manager = ResourceManager()
    manager.register_loader(PygameImageLoader())

    # Create a dummy image for testing
    if PIL_AVAILABLE:
        img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        img.save(atlas_path)

        with pytest.raises(ValueError, match="missing 'regions' key"):
            manager.load_atlas(str(atlas_path), str(metadata_path))


def test_resource_manager_load_atlas_missing_metadata():
    """ResourceManager should raise error for missing metadata file."""
    from pyguara.resources.manager import ResourceManager

    manager = ResourceManager()

    with pytest.raises(FileNotFoundError, match="Atlas metadata not found"):
        manager.load_atlas("atlas.png", "/nonexistent/metadata.json")


@pytest.mark.skipif(not PIL_AVAILABLE, reason="PIL not available")
def test_resource_manager_load_atlas_success(tmp_path, pygame_init):
    """ResourceManager should successfully load atlas with metadata."""
    from pyguara.resources.manager import ResourceManager
    from pyguara.graphics.backends.pygame.loaders import PygameImageLoader

    # Create atlas image
    atlas_path = tmp_path / "atlas.png"
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    img.save(atlas_path)

    # Create metadata
    metadata_path = tmp_path / "atlas.json"
    metadata = {
        "atlas_size": [256, 256],
        "padding": 2,
        "sprite_count": 2,
        "regions": {
            "sprite1": {
                "x": 0,
                "y": 0,
                "width": 64,
                "height": 64,
                "original_size": [64, 64],
            },
            "sprite2": {
                "x": 64,
                "y": 0,
                "width": 32,
                "height": 32,
                "original_size": [32, 32],
            },
        },
    }

    with open(metadata_path, "w") as f:
        json.dump(metadata, f)

    # Load atlas
    manager = ResourceManager()
    manager.register_loader(PygameImageLoader())

    atlas = manager.load_atlas(str(atlas_path), str(metadata_path))

    # Verify atlas
    assert atlas is not None
    assert atlas.region_count == 2
    assert atlas.has_region("sprite1")
    assert atlas.has_region("sprite2")

    # Verify regions
    region1 = atlas.get_region("sprite1")
    assert region1 is not None
    assert region1.name == "sprite1"
    assert region1.rect.x == 0
    assert region1.rect.y == 0
    assert region1.rect.width == 64
    assert region1.rect.height == 64
