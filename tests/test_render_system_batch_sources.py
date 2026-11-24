"""`RenderSystem.submit_batches` slots ready-made batches into the sort order."""

from __future__ import annotations

from pyguara.common.types import Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.pipeline.render_system import RenderSystem
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.types import RenderBatch
from pyguara.resources.types import Texture


class _Texture(Texture):
    @property
    def width(self) -> int:
        return 8

    @property
    def height(self) -> int:
        return 8

    @property
    def native_handle(self) -> object:
        return None


class _Backend:
    width, height = 100, 100

    def __init__(self) -> None:
        self.drawn: list[RenderBatch] = []

    def set_viewport(self, viewport: Viewport) -> None:
        pass

    def begin_frame(self) -> None:
        pass

    def end_frame(self) -> None:
        pass

    def render_batch(self, batch: RenderBatch) -> None:
        self.drawn.append(batch)


def _setup() -> tuple[RenderSystem, _Backend, Camera2D]:
    backend = _Backend()
    system = RenderSystem(backend)  # type: ignore[arg-type]
    camera = Camera2D(100, 100)
    camera.position = Vector2(50, 50)
    return system, backend, camera


def _sprite(system: RenderSystem, texture: Texture, layer: int, z: int = 0) -> None:
    system.submit(Sprite(texture=texture, layer=layer, z_index=z), Vector2(10, 10))


def _ready(texture: Texture) -> RenderBatch:
    return RenderBatch(texture=texture, destinations=[(1.0, 2.0)])


def test_batches_draw_between_the_layers_around_them() -> None:
    system, backend, camera = _setup()
    below, ours, above = _Texture("below"), _Texture("ours"), _Texture("above")
    _sprite(system, above, layer=20)
    system.submit_batches(lambda c, v: [_ready(ours)], layer=10)
    _sprite(system, below, layer=0)
    system.flush(camera)
    assert [b.texture.path for b in backend.drawn] == ["below", "ours", "above"]


def test_batches_go_after_sprites_at_the_same_place_and_before_deeper_ones() -> None:
    system, backend, camera = _setup()
    same, deeper, ours = _Texture("same"), _Texture("deeper"), _Texture("ours")
    _sprite(system, deeper, layer=5, z=3)
    _sprite(system, same, layer=5, z=1)
    system.submit_batches(lambda c, v: [_ready(ours)], layer=5, z_index=1)
    system.flush(camera)
    assert [b.texture.path for b in backend.drawn] == ["same", "ours", "deeper"]


def test_sources_at_one_place_keep_their_order_and_their_batches_order() -> None:
    system, backend, camera = _setup()
    a, b, c = _Texture("a"), _Texture("b"), _Texture("c")
    system.submit_batches(lambda cam, v: [_ready(a), _ready(b)], layer=1)
    system.submit_batches(lambda cam, v: [_ready(c)], layer=1)
    system.flush(camera)
    assert [x.texture.path for x in backend.drawn] == ["a", "b", "c"]


def test_a_source_sees_the_frames_camera_and_viewport() -> None:
    system, _, camera = _setup()
    seen: list[tuple[Camera2D, Viewport]] = []
    system.submit_batches(lambda cam, view: seen.append((cam, view)) or [], layer=0)
    system.flush(camera)
    assert seen[0][0] is camera
    assert (seen[0][1].width, seen[0][1].height) == (100, 100)


def test_sources_last_one_frame() -> None:
    system, backend, camera = _setup()
    system.submit_batches(lambda c, v: [_ready(_Texture("once"))], layer=0)
    system.flush(camera)
    system.flush(camera)
    assert len(backend.drawn) == 1


def test_sprites_alone_batch_as_before() -> None:
    """Splitting around sources must not split sprites when there are none."""
    system, backend, camera = _setup()
    shared = _Texture("shared")
    for layer in (0, 0, 1):
        _sprite(system, shared, layer=layer)
    system.flush(camera)
    assert [len(b.destinations) for b in backend.drawn] == [3]
