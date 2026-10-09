"""Depth ordering in the render queue: y-sort, sorting groups, and material."""

from dataclasses import dataclass

from pyguara.common.types import Color, Vector2
from pyguara.graphics.pipeline.queue import RenderQueue
from pyguara.graphics.pipeline.render_system import RenderSystem
from pyguara.graphics.types import Layer, RenderCommand
from pyguara.resources.types import Texture


class FakeTexture(Texture):
    """A texture that never touches a backend."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def width(self) -> int:
        return 16

    @property
    def height(self) -> int:
        return 16

    @property
    def native_handle(self) -> None:
        return None

    def __repr__(self) -> str:
        return self._name


TILE = FakeTexture("tile")


@dataclass
class FakeMaterial:
    """Stands in for a `Material`; only `id` matters to the sort."""

    id: int


class Renderable:
    """The minimum a thing needs to be submitted and sorted."""

    def __init__(
        self,
        name: str,
        position: Vector2,
        layer: int = Layer.ENTITIES,
        z_index: float = 0.0,
        y_sort: bool = False,
        sort_offset: float = 0.0,
        sort_group: int = 0,
        material: object = None,
    ) -> None:
        self.name = name
        self.texture = TILE
        self.position = position
        self.layer = layer
        self.z_index = z_index
        self.y_sort = y_sort
        self.sort_offset = sort_offset
        self.sort_group = sort_group
        self.rotation = 0.0
        self.scale = Vector2(1, 1)
        self.material = material
        self.color = Color(255, 255, 255, 255)


class StubBackend:
    """Captures nothing; `submit` is all these tests exercise."""

    width = 800
    height = 600


def _depths(*items: Renderable, positions: dict[str, Vector2] | None = None):
    """Submit items and return the queue's commands in sorted order."""
    system = RenderSystem(StubBackend())  # type: ignore[arg-type]
    for item in items:
        override = (positions or {}).get(item.name)
        system.submit(item, position=override)
    queue = system._queue
    queue.sort()
    return queue.commands


# -- y-sort --


def test_without_y_sort_the_depth_is_the_z_index():
    commands = _depths(
        Renderable("far", Vector2(0, 900), z_index=0),
        Renderable("near", Vector2(0, 100), z_index=5),
    )
    assert [c.z_index for c in commands] == [0, 5]


def test_y_sort_makes_world_y_the_depth():
    """A character walking down past a tree ends up in front of it, with
    nobody maintaining a z_index."""
    commands = _depths(
        Renderable("tree", Vector2(0, 300), y_sort=True),
        Renderable("hero", Vector2(0, 100), y_sort=True),
    )
    assert [c.z_index for c in commands] == [100, 300]


def test_sort_offset_moves_the_depth_to_the_contact_point():
    """A tall tree's centre sits above a short character's, so without the
    offset the tree draws behind a character standing in front of its trunk."""
    tree = Renderable("tree", Vector2(0, 200), y_sort=True, sort_offset=64.0)
    hero = Renderable("hero", Vector2(0, 240), y_sort=True, sort_offset=16.0)

    commands = _depths(tree, hero)

    assert [c.z_index for c in commands] == [256, 264]


def test_the_submitted_position_decides_depth_not_the_items_own():
    """`Scene.render` submits a sprite at its Transform plus its own offset,
    and depth has to come from where the sprite is actually drawn."""
    sprite = Renderable("hero", Vector2(0, 0), y_sort=True)

    commands = _depths(sprite, positions={"hero": Vector2(0, 450)})

    assert commands[0].z_index == 450


# -- Sorting groups --


def test_a_sort_group_outranks_depth_within_the_layer():
    """A character and the sword they hold sort as one unit against the
    scenery, however their own depths compare."""
    commands = _depths(
        Renderable("scenery", Vector2(0, 500), y_sort=True, sort_group=0),
        Renderable("hero", Vector2(0, 100), y_sort=True, sort_group=1),
        Renderable("sword", Vector2(0, 90), y_sort=True, sort_group=1),
    )
    assert [c.sort_group for c in commands] == [0, 1, 1]
    assert [c.z_index for c in commands] == [500, 90, 100]


def test_the_layer_still_outranks_everything():
    commands = _depths(
        Renderable("hud", Vector2(0, 0), layer=Layer.UI, sort_group=0),
        Renderable("deep", Vector2(0, 9999), layer=Layer.BACKGROUND, sort_group=99),
    )
    assert [c.layer for c in commands] == [Layer.BACKGROUND, Layer.UI]


# -- Material no longer outranks depth --


def test_depth_beats_material_so_y_sorting_works_with_more_than_one_shader():
    """Material used to be compared before depth, so two overlapping sprites
    with different materials drew in material order. Y-sorting could not
    have worked at all in a scene with more than one material."""
    queue = RenderQueue()
    queue.push(RenderCommand(TILE, Vector2(0, 0), Layer.ENTITIES, 300.0, material=None))
    queue.push(
        RenderCommand(
            TILE,
            Vector2(0, 0),
            Layer.ENTITIES,
            100.0,
            material=FakeMaterial(7),  # type: ignore[arg-type]
        )
    )

    queue.sort()

    assert [c.z_index for c in queue.commands] == [100.0, 300.0]


def test_material_still_breaks_ties_at_equal_depth():
    """Which is where the batching actually comes from -- a tilemap row at
    one depth, a crowd of identical particles."""
    queue = RenderQueue()
    for material_id in (3, 1, 3, 1):
        queue.push(
            RenderCommand(
                TILE,
                Vector2(0, 0),
                Layer.ENTITIES,
                0.0,
                material=FakeMaterial(material_id),  # type: ignore[arg-type]
            )
        )

    queue.sort()

    assert [c.material_id for c in queue.commands] == [1, 1, 3, 3]


def test_commands_equal_on_every_key_keep_their_submission_order():
    queue = RenderQueue()
    first = RenderCommand(TILE, Vector2(1, 0), Layer.ENTITIES, 0.0)
    second = RenderCommand(TILE, Vector2(2, 0), Layer.ENTITIES, 0.0)
    queue.push(first)
    queue.push(second)

    queue.sort()

    assert queue.commands == [first, second]
