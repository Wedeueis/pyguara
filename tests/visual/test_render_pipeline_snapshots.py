"""Snapshot the whole backend call stream a frame produces.

The pipeline already has unit tests: the batcher's grouping, the viewport's
letterbox maths, the queue's ordering. Each asserts its own slice. None
captures what a *frame* actually turns into -- the ordered sequence of calls
`RenderSystem.flush()` makes on the backend, with the world-to-screen
transform already applied.

That sequence is where a refactor's cross-cutting mistakes show up: a sort
that stops being stable, a camera transform that drifts by half a pixel, a
batch that silently splits in two, a viewport recomputed when it should be
reused. A unit test asserting `len(batches) == 1` sails past most of those.

The recording backend below implements `IRenderer` structurally, so these
also fail if the protocol and the pipeline drift apart.

Why this is deterministic, and safe to snapshot: nothing here rasterises.
There is no font, no SDL surface, no GPU -- only Python float arithmetic on
fixed inputs. Positions are rounded to three decimals so a last-bit
difference cannot flip a snapshot red on its own.
"""

from __future__ import annotations

import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.render_system import RenderSystem
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.types import Layer, RenderBatch
from pyguara.resources.types import Texture

pytestmark = pytest.mark.integration


class FakeTexture(Texture):
    """A texture with a name and a size, and no pixels behind it."""

    def __init__(self, name: str, width: int = 64, height: int = 64) -> None:
        """Create a named texture of a fixed size."""
        super().__init__(f"{name}.png")
        self._width = width
        self._height = height

    @property
    def width(self) -> int:
        """Width in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Height in pixels."""
        return self._height

    @property
    def native_handle(self) -> None:
        """No backend object exists for a fake texture."""
        return None


class Sprite:
    """The minimum a thing needs to satisfy `Renderable`."""

    def __init__(
        self,
        texture: Texture,
        position: Vector2,
        layer: int,
        z_index: float,
        rotation: float = 0.0,
        scale: Vector2 | None = None,
    ) -> None:
        """Create a renderable at a world position on a layer."""
        self.texture = texture
        self.position = position
        self.layer = layer
        self.z_index = z_index
        self.rotation = rotation
        self.scale = scale if scale is not None else Vector2(1, 1)
        self.material = None


def _f(value: float) -> str:
    """Format a float for the snapshot.

    Three decimals: enough to catch a real transform change, coarse enough
    that float noise cannot fail a run on its own.
    """
    return f"{value:.3f}"


class RecordingRenderer:
    """An `IRenderer` that writes down every call instead of drawing it."""

    def __init__(self, width: int = 800, height: int = 600) -> None:
        """Create a recorder reporting a fixed surface size."""
        self._width = width
        self._height = height
        self.calls: list[str] = []

    @property
    def width(self) -> int:
        """Surface width in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Surface height in pixels."""
        return self._height

    def clear(self, color: Color) -> None:
        """Record a clear."""
        self.calls.append(f"clear rgba=({color.r},{color.g},{color.b},{color.a})")

    def set_viewport(self, viewport: Rect) -> None:
        """Record a viewport change."""
        self.calls.append(
            f"set_viewport x={viewport.x} y={viewport.y} "
            f"w={viewport.width} h={viewport.height}"
        )

    def reset_viewport(self) -> None:
        """Record a viewport reset."""
        self.calls.append("reset_viewport")

    def begin_frame(self) -> None:
        """Record the start of a frame."""
        self.calls.append("begin_frame")

    def end_frame(self) -> None:
        """Record the end of a frame."""
        self.calls.append("end_frame")

    def present(self) -> None:
        """Record a present."""
        self.calls.append("present")

    def draw_texture(
        self,
        texture: Texture,
        destination: Vector2,
        rotation: float = 0.0,
        scale: Vector2 = Vector2(1, 1),
    ) -> None:
        """Record a single texture draw."""
        self.calls.append(
            f"draw_texture {texture.path} at=({_f(destination.x)},"
            f"{_f(destination.y)}) rot={_f(rotation)}"
        )

    def draw_rect(self, rect: Rect, color: Color, width: int = 0) -> None:
        """Record a rectangle draw."""
        self.calls.append(f"draw_rect {rect.x},{rect.y},{rect.width},{rect.height}")

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Record a circle draw."""
        self.calls.append(f"draw_circle at=({_f(center.x)},{_f(center.y)})")

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Record a line draw."""
        self.calls.append("draw_line")

    def render_batch(self, batch: RenderBatch) -> None:
        """Record a batch, including where every instance landed on screen."""
        destinations = ", ".join(f"({_f(x)},{_f(y)})" for x, y in batch.destinations)
        line = (
            f"render_batch {batch.texture.path} n={len(batch.destinations)} "
            f"transforms={'on' if batch.transforms_enabled else 'off'} "
            f"dest=[{destinations}]"
        )
        if batch.transforms_enabled:
            rotations = ", ".join(_f(r) for r in batch.rotations)
            scales = ", ".join(f"({_f(x)},{_f(y)})" for x, y in batch.scales)
            line += f" rot=[{rotations}] scale=[{scales}]"
        self.calls.append(line)


def render(
    sprites: list[Sprite],
    camera: Camera2D | None = None,
    viewport: Viewport | None = None,
) -> list[str]:
    """Submit sprites, flush one frame, and return the recorded call stream.

    Args:
        sprites: Renderables to submit, in submission order.
        camera: Active camera. Defaults to an unmoved 800x600 camera.
        viewport: Optional explicit viewport.

    Returns:
        Every call the pipeline made on the backend, in order.
    """
    backend = RecordingRenderer()
    system = RenderSystem(backend)
    for sprite in sprites:
        system.submit(sprite)
    system.flush(camera or Camera2D(800, 600), viewport)
    return backend.calls


HERO = FakeTexture("hero")
TILE = FakeTexture("tile")


def test_an_empty_frame_still_sets_up_and_tears_down(snapshot) -> None:
    """A frame with nothing in it still clears and brackets itself."""
    assert render([]) == snapshot


def test_sprites_are_drawn_back_to_front(snapshot) -> None:
    """Submission order must not survive; layer then z_index decides.

    The sprites go in deliberately worst-first: UI before background, and a
    high z before a low one within the same layer.
    """
    sprites = [
        Sprite(HERO, Vector2(0, 0), Layer.UI, z_index=0),
        Sprite(TILE, Vector2(0, 0), Layer.BACKGROUND, z_index=0),
        Sprite(HERO, Vector2(0, 0), Layer.ENTITIES, z_index=99),
        Sprite(TILE, Vector2(0, 0), Layer.ENTITIES, z_index=1),
    ]
    assert render(sprites) == snapshot


def test_the_camera_transform_reaches_the_batch(snapshot) -> None:
    """A moved, zoomed camera must show up in the screen positions."""
    camera = Camera2D(800, 600)
    camera.position = Vector2(100, 50)
    camera.zoom = 2.0
    sprites = [
        Sprite(HERO, Vector2(100, 50), Layer.ENTITIES, z_index=0),
        Sprite(HERO, Vector2(200, 50), Layer.ENTITIES, z_index=1),
        Sprite(HERO, Vector2(100, 150), Layer.ENTITIES, z_index=2),
    ]
    assert render(sprites, camera=camera) == snapshot


def test_one_texture_makes_one_batch(snapshot) -> None:
    """Four sprites sharing a texture must not become four draw calls."""
    sprites = [
        Sprite(HERO, Vector2(i * 32, 0), Layer.ENTITIES, z_index=i) for i in range(4)
    ]
    assert render(sprites) == snapshot


def test_interleaved_textures_split_into_separate_batches(snapshot) -> None:
    """Alternating textures cannot be merged without reordering them.

    This is the case where a batching change is most likely to go wrong:
    merging these would be faster and visibly incorrect.
    """
    sprites = [
        Sprite(HERO if i % 2 == 0 else TILE, Vector2(i * 32, 0), Layer.ENTITIES, i)
        for i in range(4)
    ]
    assert render(sprites) == snapshot


def test_rotation_and_scale_switch_the_batch_to_the_transform_path(snapshot) -> None:
    """A rotated or scaled sprite carries its transform through to the batch."""
    sprites = [
        Sprite(HERO, Vector2(0, 0), Layer.ENTITIES, 0, rotation=45.0),
        Sprite(HERO, Vector2(64, 0), Layer.ENTITIES, 1, scale=Vector2(2, 0.5)),
    ]
    assert render(sprites) == snapshot


def test_a_letterboxed_viewport_is_passed_through_verbatim(snapshot) -> None:
    """An explicit viewport reaches the backend, and content centres in it.

    The sprite sits at the camera's position, so it must land at the centre
    of the letterboxed band -- (400, 300) here -- not offset by the band's
    origin. Generating this snapshot is what exposed that it used to be
    (400, 360); see `test_the_camera_lands_on_the_viewport_centre`.
    """
    viewport = Viewport(0, 60, 800, 480)
    sprites = [Sprite(HERO, Vector2(0, 0), Layer.ENTITIES, z_index=0)]
    assert render(sprites, viewport=viewport) == snapshot
