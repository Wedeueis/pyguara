import pygame
from pyguara.common.types import Color, Vector2
from pyguara.graphics.components.geometry import Box, Circle
from pyguara.graphics.backends.pygame.types import PygameTexture


def test_box_texture_generation():
    """Test that Box generates a texture with correct dimensions and color."""
    # Ensure pygame is initialized or headless mode works (it does)

    color = Color(255, 0, 0, 255)
    box = Box(width=100, height=50, color=color)

    # 1. Texture should be None initially (lazy)
    assert box._texture is None
    assert box._dirty is True

    # 2. Accessing texture should generate it
    tex = box.texture
    assert tex is not None
    assert isinstance(tex, PygameTexture)
    assert tex.width == 100
    assert tex.height == 50
    assert box._dirty is False

    # 3. Verify content (basic check)
    surf = tex.native_handle
    assert isinstance(surf, pygame.Surface)
    assert surf.get_at((0, 0)) == (255, 0, 0, 255)


def test_box_resize():
    """Test that resizing Box flags it as dirty and updates texture."""
    box = Box(10, 10, Color(0, 0, 0))
    _ = box.texture  # Force gen

    old_tex_id = id(box.texture)

    # Resize
    box.resize(20, 20)
    assert box._dirty is True

    # Check new texture
    new_tex = box.texture
    assert new_tex.width == 20
    assert new_tex.height == 20
    assert id(new_tex) != old_tex_id


def test_box_set_color():
    """Test that changing Box color updates texture."""
    box = Box(10, 10, Color(255, 255, 255))
    _ = box.texture

    box.set_color(Color(0, 0, 0))
    assert box._dirty is True

    tex = box.texture
    assert tex.native_handle.get_at((5, 5)) == (0, 0, 0, 255)


def test_circle_texture_generation():
    """Test Circle texture generation."""
    radius = 10
    color = Color(0, 255, 0)
    circle = Circle(radius, color)

    tex = circle.texture
    # Diameter = 20
    assert tex.width == 20
    assert tex.height == 20

    # Center should be green
    center_color = tex.native_handle.get_at((10, 10))
    assert center_color == (0, 255, 0, 255)

    # Corner should be transparent (alpha 0)
    corner_color = tex.native_handle.get_at((0, 0))
    assert corner_color.a == 0


def test_circle_radius_change():
    """Test changing radius."""
    c = Circle(5, Color(255, 0, 0))
    _ = c.texture

    c.radius = 10
    assert c._dirty is True

    tex = c.texture
    assert tex.width == 20  # 10*2


def test_geometry_properties():
    """Test base class properties."""
    b = Box(10, 10, Color(0, 0, 0), layer=5, z_index=2.5)
    b.position = Vector2(100, 100)

    assert b.layer == 5
    assert b.z_index == 2.5
    assert b.position == Vector2(100, 100)
