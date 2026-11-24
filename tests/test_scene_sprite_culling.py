"""`Scene.render` skips sprites wholly outside the camera's view.

A sprite is drawn with its box's top-left at its position, and a turned
sprite's box is the one bounding the turned image. So anything that could
reach the view must still be submitted, whatever its turn and scale.
"""

from __future__ import annotations

from typing import Any

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.resources.types import Texture
from pyguara.scene.base import Scene

WIDTH, HEIGHT = 200, 100


class _Texture(Texture):
    def __init__(self, width: int = 20, height: int = 10) -> None:
        super().__init__("square")
        self._width, self._height = width, height

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def native_handle(self) -> object:
        return None


class _RenderSystem:
    def __init__(self) -> None:
        self.submitted: list[Vector2] = []

    def submit(self, item: Any, position: Vector2 | None = None) -> None:
        assert position is not None
        self.submitted.append(position)

    def flush(self, camera: Camera2D) -> None:
        pass


class _Scene(Scene):
    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def update(self, dt: float) -> None:
        pass


def _scene(zoom: float = 1.0) -> tuple[_Scene, _RenderSystem]:
    scene = _Scene("culling", EventDispatcher())
    camera = Camera2D(WIDTH, HEIGHT)
    camera.position = Vector2(WIDTH / 2, HEIGHT / 2)
    camera.zoom = zoom
    scene.camera = camera
    system = _RenderSystem()
    scene.render_system = system  # type: ignore[assignment]
    return scene, system


def _sprite(scene: Scene, x: float, y: float, **fields: Any) -> None:
    entity = scene.entity_manager.create_entity()
    entity.add_component(Transform(position=Vector2(x, y)))
    texture = fields.pop("texture", _Texture())
    entity.add_component(Sprite(texture=texture, **fields))


def _drawn(scene: Scene, system: _RenderSystem) -> set[tuple[float, float]]:
    scene.render(None, None)  # type: ignore[arg-type]
    return {(p.x, p.y) for p in system.submitted}


def test_a_sprite_on_screen_is_drawn_and_one_far_off_is_not() -> None:
    scene, system = _scene()
    _sprite(scene, 50, 50)
    _sprite(scene, 900, 50)
    _sprite(scene, 50, -900)

    assert _drawn(scene, system) == {(50, 50)}


@pytest.mark.parametrize(
    ("x", "y"),
    [(-19, 50), (-15, -9), (199, 99), (100, -9)],
    ids=["left edge", "top-left corner", "bottom-right corner", "top edge"],
)
def test_a_sprite_partly_on_screen_is_drawn(x: float, y: float) -> None:
    scene, system = _scene()
    _sprite(scene, x, y)

    assert _drawn(scene, system) == {(x, y)}


@pytest.mark.parametrize(("x", "y"), [(-30, 50), (100, -30), (205, 50), (100, 105)])
def test_a_sprite_just_past_an_edge_is_skipped(x: float, y: float) -> None:
    scene, system = _scene()
    _sprite(scene, x, y)

    assert _drawn(scene, system) == set()


def test_a_turned_sprite_whose_box_reaches_the_view_is_drawn() -> None:
    """Turned 45 degrees, a 20x10 image's box is about 21.2 wide.

    At x = -22 its width alone would end short of the view; the turned box
    reaches into it.
    """
    scene, system = _scene()
    _sprite(scene, -22, 50, rotation=45.0)

    assert _drawn(scene, system) == {(-22, 50)}


def test_a_scaled_sprite_is_bounded_by_its_drawn_size() -> None:
    scene, system = _scene()
    _sprite(scene, -50, 50, scale=Vector2(3, 3))  # 60 wide, reaching x = 10
    _sprite(scene, -50, 20, scale=Vector2(-3, 3))  # flipped: the same box

    assert _drawn(scene, system) == {(-50, 50), (-50, 20)}


def test_a_zoomed_out_camera_sees_further() -> None:
    scene, system = _scene(zoom=0.5)  # sees x from -100 to 300
    _sprite(scene, 280, 50)
    _sprite(scene, 320, 50)

    assert _drawn(scene, system) == {(280, 50)}


def test_with_culling_off_every_sprite_is_drawn() -> None:
    scene, system = _scene()
    scene.cull_sprites = False
    _sprite(scene, 900, 50)
    _sprite(scene, 50, 50)

    assert _drawn(scene, system) == {(900, 50), (50, 50)}
