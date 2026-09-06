"""Tests for the procedural geometry components.

These shapes used to import pygame and construct `PygameTexture` directly, so
they silently produced the wrong texture type under ModernGL. They now
rasterise to plain RGBA bytes and hand them to an injected `TextureFactory`,
which is the abstraction `SpriteSheet` in this same package already used.

The tests are split accordingly: the rasterisation itself is checked against
raw bytes, backend-free, and the pygame path is checked separately to confirm
real pixels come out the far end.
"""

import pygame

from pyguara.common.types import Color, Vector2
from pyguara.graphics.backends.headless_renderer import HeadlessTextureFactory
from pyguara.graphics.backends.pygame.types import PygameTexture, PygameTextureFactory
from pyguara.graphics.components.geometry import Box, Circle
from pyguara.graphics.protocols import TextureFactory
from pyguara.resources.types import Texture

BYTES_PER_PIXEL = 4


class RecordingFactory:
    """A factory that keeps the raw bytes, so rasterisation can be asserted."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, int, int]] = []

    def create_from_bytes(
        self, path: str, data: bytes, width: int, height: int
    ) -> Texture:
        self.calls.append((path, data, width, height))
        return HeadlessTextureFactory().create_from_bytes(path, data, width, height)

    @property
    def last(self) -> tuple[str, bytes, int, int]:
        return self.calls[-1]

    def pixel_at(self, x: int, y: int) -> tuple[int, int, int, int]:
        _, data, width, _ = self.last
        offset = (y * width + x) * BYTES_PER_PIXEL
        return tuple(data[offset : offset + BYTES_PER_PIXEL])  # type: ignore[return-value]


class TestBackendIndependence:
    def test_the_module_imports_no_backend(self) -> None:
        """geometry.py importing pygame was the clearest instance of issue #9:
        an ECS-facing component hard-wired to one renderer."""
        source = (
            __import__("pathlib")
            .Path("pyguara/graphics/components/geometry.py")
            .read_text()
        )
        assert "pygame" not in source

    def test_a_shape_uses_whatever_factory_it_is_given(self) -> None:
        factory = RecordingFactory()
        _ = Box(10, 5, Color(1, 2, 3), factory).texture

        path, data, width, height = factory.last
        assert (width, height) == (10, 5)
        assert len(data) == 10 * 5 * BYTES_PER_PIXEL

    def test_a_shape_works_on_the_headless_backend(self) -> None:
        texture = Circle(4, Color(255, 0, 0), HeadlessTextureFactory()).texture

        assert (texture.width, texture.height) == (8, 8)

    def test_a_shape_works_on_the_pygame_backend(self) -> None:
        texture = Box(10, 5, Color(1, 2, 3), PygameTextureFactory()).texture

        assert isinstance(texture, PygameTexture)
        assert isinstance(texture.native_handle, pygame.Surface)


class TestBoxRasterisation:
    def test_every_pixel_is_the_fill_colour(self) -> None:
        factory = RecordingFactory()
        _ = Box(4, 3, Color(255, 0, 0, 255), factory).texture

        _, data, _, _ = factory.last
        assert data == bytes((255, 0, 0, 255)) * 12

    def test_alpha_is_preserved(self) -> None:
        factory = RecordingFactory()
        _ = Box(2, 2, Color(10, 20, 30, 40), factory).texture

        assert factory.pixel_at(0, 0) == (10, 20, 30, 40)

    def test_dimensions_reach_the_factory(self) -> None:
        factory = RecordingFactory()
        _ = Box(100, 50, Color(0, 0, 0), factory).texture

        assert factory.last[2:] == (100, 50)

    def test_pixels_are_correct_on_the_pygame_backend(self) -> None:
        texture = Box(10, 10, Color(255, 0, 0, 255), PygameTextureFactory()).texture

        assert texture.native_handle.get_at((0, 0)) == (255, 0, 0, 255)
        assert texture.native_handle.get_at((9, 9)) == (255, 0, 0, 255)


class TestCircleRasterisation:
    def test_the_centre_is_filled_and_the_corners_are_clear(self) -> None:
        factory = RecordingFactory()
        _ = Circle(10, Color(0, 255, 0), factory).texture

        assert factory.pixel_at(10, 10) == (0, 255, 0, 255)
        assert factory.pixel_at(0, 0) == (0, 0, 0, 0)
        assert factory.pixel_at(19, 19) == (0, 0, 0, 0)

    def test_the_texture_is_a_square_of_the_diameter(self) -> None:
        factory = RecordingFactory()
        _ = Circle(7, Color(0, 0, 0), factory).texture

        assert factory.last[2:] == (14, 14)

    def test_the_widest_row_spans_the_full_diameter(self) -> None:
        factory = RecordingFactory()
        radius = 8
        _ = Circle(radius, Color(1, 2, 3), factory).texture

        middle_row = [factory.pixel_at(x, radius)[3] for x in range(radius * 2)]
        assert middle_row[0] == 255
        assert middle_row[-1] == 255

    def test_the_shape_is_symmetric(self) -> None:
        factory = RecordingFactory()
        radius = 9
        _ = Circle(radius, Color(1, 2, 3), factory).texture

        for y in range(radius * 2):
            row = [factory.pixel_at(x, y)[3] for x in range(radius * 2)]
            assert row == row[::-1], f"row {y} is not mirror-symmetric"

    def test_pixels_are_correct_on_the_pygame_backend(self) -> None:
        texture = Circle(10, Color(0, 255, 0), PygameTextureFactory()).texture

        assert texture.native_handle.get_at((10, 10)) == (0, 255, 0, 255)
        assert texture.native_handle.get_at((0, 0)).a == 0


class TestCaching:
    def test_the_texture_is_generated_lazily(self) -> None:
        factory = RecordingFactory()
        box = Box(10, 10, Color(0, 0, 0), factory)

        assert factory.calls == []
        _ = box.texture
        assert len(factory.calls) == 1

    def test_repeated_reads_reuse_the_cached_texture(self) -> None:
        factory = RecordingFactory()
        box = Box(10, 10, Color(0, 0, 0), factory)

        first = box.texture
        assert box.texture is first
        assert len(factory.calls) == 1

    def test_resizing_regenerates(self) -> None:
        factory = RecordingFactory()
        box = Box(10, 10, Color(0, 0, 0), factory)
        _ = box.texture

        box.resize(20, 20)
        texture = box.texture

        assert (texture.width, texture.height) == (20, 20)
        assert len(factory.calls) == 2

    def test_recolouring_regenerates_a_box(self) -> None:
        factory = RecordingFactory()
        box = Box(4, 4, Color(255, 255, 255), factory)
        _ = box.texture

        box.set_color(Color(0, 0, 0))
        _ = box.texture

        assert factory.pixel_at(0, 0) == (0, 0, 0, 255)

    def test_changing_the_radius_regenerates(self) -> None:
        factory = RecordingFactory()
        circle = Circle(5, Color(255, 0, 0), factory)
        _ = circle.texture

        circle.radius = 10
        assert circle.texture.width == 20

    def test_recolouring_regenerates_a_circle(self) -> None:
        factory = RecordingFactory()
        circle = Circle(4, Color(255, 255, 255), factory)
        _ = circle.texture

        circle.set_color(Color(9, 8, 7))
        _ = circle.texture

        assert factory.pixel_at(4, 4) == (9, 8, 7, 255)


class TestRenderableSurface:
    def test_layer_z_index_and_position(self) -> None:
        box = Box(10, 10, Color(0, 0, 0), RecordingFactory(), layer=5, z_index=2.5)
        box.position = Vector2(100, 100)

        assert box.layer == 5
        assert box.z_index == 2.5
        assert box.position == Vector2(100, 100)

    def test_shapes_default_to_no_rotation_and_natural_scale(self) -> None:
        box = Box(10, 10, Color(0, 0, 0), RecordingFactory())

        assert box.rotation == 0.0
        assert box.scale == Vector2(1, 1)
        assert box.material is None

    def test_the_factory_satisfies_the_protocol(self) -> None:
        assert isinstance(PygameTextureFactory(), TextureFactory)
        assert isinstance(HeadlessTextureFactory(), TextureFactory)


class TestCameraZoomInvariant:
    """Camera zoom is a scale factor, so zero and negative are meaningless.

    Both used to be accepted and then handled three different ways:
    world_to_screen collapsed every point onto the screen centre,
    screen_to_world substituted 0.001 and returned coordinates six orders of
    magnitude out, and get_view_bounds raised ZeroDivisionError. A negative
    zoom silently mirrored the world.
    """

    def test_zero_zoom_is_rejected(self) -> None:
        import pytest

        from pyguara.graphics.components.camera import Camera2D

        camera = Camera2D(800, 600)
        with pytest.raises(ValueError, match="zoom must be positive"):
            camera.zoom = 0.0

    def test_negative_zoom_is_rejected(self) -> None:
        import pytest

        from pyguara.graphics.components.camera import Camera2D

        camera = Camera2D(800, 600)
        with pytest.raises(ValueError, match="zoom must be positive"):
            camera.zoom = -1.0

    def test_a_rejected_zoom_leaves_the_camera_usable(self) -> None:
        import pytest

        from pyguara.graphics.components.camera import Camera2D

        camera = Camera2D(800, 600)
        with pytest.raises(ValueError):
            camera.zoom = 0.0

        assert camera.zoom == 1.0
        assert camera.get_view_bounds() is not None

    def test_zoom_to_rejects_a_non_positive_target(self) -> None:
        """Checked at the call that supplied it, not when the transition
        lands, so the traceback points at the caller."""
        import pytest

        from pyguara.graphics.components.camera import Camera2D

        camera = Camera2D(800, 600)
        with pytest.raises(ValueError, match="zoom must be positive"):
            camera.zoom_to(0.0)

    def test_small_positive_zoom_is_the_way_to_zoom_out(self) -> None:
        from pyguara.graphics.components.camera import Camera2D

        camera = Camera2D(800, 600)
        camera.zoom = 0.25

        assert camera.zoom == 0.25
        assert camera.get_view_bounds() is not None

    def test_the_screen_world_round_trip_holds_at_every_valid_zoom(self) -> None:
        from pyguara.graphics.components.camera import Camera2D

        for zoom in (0.25, 1.0, 2.0, 10.0):
            camera = Camera2D(800, 600)
            camera.zoom = zoom
            camera.position = Vector2(50, 50)
            point = Vector2(123, 456)

            restored = camera.screen_to_world(camera.world_to_screen(point))

            assert abs(restored.x - point.x) < 1e-6, f"zoom {zoom}"
            assert abs(restored.y - point.y) < 1e-6, f"zoom {zoom}"
