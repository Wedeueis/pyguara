"""A swarm draws its agents as the same sprites would be drawn.

`Swarm.submit` must produce, batch for batch, what `RenderSystem` makes of
`Sprite`s carrying the same texture, position, turn and scale. Culling
follows `Scene.render`'s rule, and each agent's clip starts when it spawns.
"""

from __future__ import annotations

import math

import pytest

from pyguara.ai.swarm import Swarm, SwarmKind, SwarmLook
from pyguara.common.types import Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.sprite import Sprite
from pyguara.graphics.pipeline.render_system import RenderSystem
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.types import RenderBatch
from pyguara.resources.types import Texture

WIDTH, HEIGHT = 200, 100


class _Texture(Texture):
    def __init__(self, name: str, width: int = 16, height: int = 12) -> None:
        super().__init__(name)
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


class _Backend:
    width, height = WIDTH, HEIGHT

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


FRAMES = (_Texture("f0"), _Texture("f1"), _Texture("f2"))


def _camera(zoom: float = 1.0) -> Camera2D:
    camera = Camera2D(WIDTH, HEIGHT)
    camera.position = Vector2(WIDTH / 2 + 7.5, HEIGHT / 2 - 3.25)
    camera.zoom = zoom
    return camera


def _draw(swarm: Swarm, camera: Camera2D) -> list[RenderBatch]:
    backend = _Backend()
    system = RenderSystem(backend)  # type: ignore[arg-type]
    swarm.submit(system)
    system.flush(camera)
    return backend.drawn


def _rows(batches: list[RenderBatch]) -> list[tuple[object, ...]]:
    return [
        (b.texture, b.destinations, b.rotations, b.scales, b.transforms_enabled)
        for b in batches
    ]


def _expected(
    swarm: Swarm, look: SwarmLook, camera: Camera2D
) -> list[tuple[object, ...]]:
    """What `RenderSystem` makes of one `Sprite` per visible agent."""
    view = camera.get_view_bounds()
    left, top = view.x - 1, view.y - 1
    right, bottom = view.x + view.width + 1, view.y + view.height + 1
    ids = swarm.ids()
    by_frame: dict[int, list[Sprite]] = {}
    positions: dict[int, list[Vector2]] = {}
    for agent, position, velocity in zip(
        ids, swarm.positions(ids), swarm.velocities(ids), strict=True
    ):
        at = position + look.offset
        extent = math.hypot(16 * look.scale.x, 12 * look.scale.y)
        if at.x > right or at.y > bottom:
            continue
        if (at.x < left or at.y < top) and (
            at.x + extent < left or at.y + extent < top
        ):
            continue
        frame = _frame_of(swarm, agent, look)
        rotation = (
            math.degrees(math.atan2(velocity.y, velocity.x))
            if look.face_heading
            else 0.0
        )
        by_frame.setdefault(frame, []).append(
            Sprite(texture=look.frames[frame], rotation=rotation, scale=look.scale)
        )
        positions.setdefault(frame, []).append(at)
    backend = _Backend()
    system = RenderSystem(backend)  # type: ignore[arg-type]
    for frame in sorted(by_frame):
        for sprite, at in zip(by_frame[frame], positions[frame], strict=True):
            system.submit(sprite, at)
    system.flush(camera)
    return _rows(backend.drawn)


SPAWN_TIMES: dict[int, float] = {}


def _frame_of(swarm: Swarm, agent: int, look: SwarmLook) -> int:
    if look.frame_rate == 0.0:
        return 0
    elapsed = swarm.time - SPAWN_TIMES[agent]
    return math.floor(elapsed * look.frame_rate) % len(look.frames)


def _crowd(look: SwarmLook, ticks: int = 20) -> Swarm:
    """Agents spread over and around the view, spawned at different times."""
    swarm = Swarm(cell_size=32.0)
    kind = swarm.add_kind(SwarmKind(max_speed=80.0))
    swarm.set_look(kind, look)
    for tick in range(ticks):
        points = [
            Vector2(-40 + (i * 37 + tick * 11) % 300, -40 + (i * 53 + tick * 7) % 190)
            for i in range(12)
        ]
        moving = [Vector2(30 - i * 5, i * 4 - 20) for i in range(12)]
        for agent in swarm.spawn(kind, points, moving):
            SPAWN_TIMES[agent] = swarm.time
        swarm.set_kind_seek(kind, Vector2(100, 50))
        swarm.update(1 / 60)
    return swarm


LOOKS = {
    "still": SwarmLook(frames=FRAMES[:1]),
    "animated": SwarmLook(frames=FRAMES, frame_rate=9.0),
    "turned": SwarmLook(frames=FRAMES, frame_rate=12.0, face_heading=True),
    "scaled-and-offset": SwarmLook(
        frames=FRAMES[:2],
        frame_rate=5.0,
        offset=Vector2(-8, -6),
        scale=Vector2(1.5, 0.75),
        face_heading=True,
    ),
}


@pytest.mark.parametrize("name", LOOKS)
@pytest.mark.parametrize("zoom", [1.0, 2.0, 0.5])
def test_the_swarm_draws_what_the_same_sprites_would(name: str, zoom: float) -> None:
    look = LOOKS[name]
    swarm, camera = _crowd(look), _camera(zoom)
    drawn = _draw(swarm, camera)
    assert drawn, "nothing visible: the scenario proves nothing"
    assert _rows(drawn) == _expected(swarm, look, camera)


def test_agents_off_screen_are_culled_and_ones_that_could_reach_it_are_not() -> None:
    look = SwarmLook(frames=FRAMES[:1], face_heading=True)
    swarm = Swarm(cell_size=32.0)
    kind = swarm.add_kind(SwarmKind())
    swarm.set_look(kind, look)
    camera = _camera()
    view = camera.get_view_bounds()
    # 20 px diagonal: a box starting 19 px left of the view can turn into it.
    reaching, gone, past = swarm.spawn(
        kind,
        [
            Vector2(view.x - 1 - 19, view.y + 10),
            Vector2(view.x - 1 - 21, view.y + 10),
            Vector2(view.x + view.width + 2, view.y + 10),
        ],
        [Vector2(1, 0)] * 3,
    )
    (batch,) = _draw(swarm, camera)
    offset = camera.screen_offset(Viewport(0, 0, WIDTH, HEIGHT))
    at = swarm.positions([reaching])[0]
    assert batch.destinations == [(at.x + offset.x, at.y + offset.y)]
    assert swarm.is_alive(gone) and swarm.is_alive(past)


def test_each_agents_clip_starts_when_it_spawns() -> None:
    look = SwarmLook(frames=FRAMES, frame_rate=10.0)
    swarm = Swarm(cell_size=32.0)
    kind = swarm.add_kind(SwarmKind(max_speed=0.0))
    swarm.set_look(kind, look)
    swarm.spawn(kind, [Vector2(50, 50)])
    for _ in range(6):  # 0.1 s: the first agent is on its second frame
        swarm.update(1 / 60 + 1e-9)
    swarm.spawn(kind, [Vector2(60, 50)])
    drawn = _draw(swarm, _camera())
    assert [(b.texture.path, len(b.destinations)) for b in drawn] == [
        ("f0", 1),
        ("f1", 1),
    ]


def test_a_kind_with_no_look_draws_nothing() -> None:
    swarm = Swarm(cell_size=32.0)
    kind = swarm.add_kind(SwarmKind())
    swarm.spawn(kind, [Vector2(50, 50)])
    assert _draw(swarm, _camera()) == []


def test_kinds_draw_on_their_own_layers_among_sprites() -> None:
    swarm = Swarm(cell_size=32.0)
    low = swarm.add_kind(SwarmKind())
    high = swarm.add_kind(SwarmKind())
    swarm.set_look(low, SwarmLook(frames=(_Texture("low"),), layer=1))
    swarm.set_look(high, SwarmLook(frames=(_Texture("high"),), layer=3))
    swarm.spawn(low, [Vector2(50, 50)])
    swarm.spawn(high, [Vector2(50, 50)])
    backend = _Backend()
    system = RenderSystem(backend)  # type: ignore[arg-type]
    system.submit(Sprite(texture=_Texture("ground"), layer=0), Vector2(0, 0))
    system.submit(Sprite(texture=_Texture("player"), layer=2), Vector2(0, 0))
    swarm.submit(system)
    system.flush(_camera())
    assert [b.texture.path for b in backend.drawn] == [
        "ground",
        "low",
        "player",
        "high",
    ]


@pytest.mark.parametrize(
    ("fields", "match"),
    [({"frames": ()}, "frame"), ({"frame_rate": -1.0}, "frame_rate")],
)
def test_an_unusable_look_is_refused(fields: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        SwarmLook(**{"frames": FRAMES, **fields})  # type: ignore[arg-type]


def test_a_look_for_an_unknown_kind_is_refused() -> None:
    swarm = Swarm(cell_size=32.0)
    with pytest.raises(ValueError, match="kind"):
        swarm.set_look(4, SwarmLook(frames=FRAMES))
