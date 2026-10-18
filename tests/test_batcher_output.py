"""What `Batcher.create_batches` must produce, pinned apart from how.

These assert the *output*, not the loop that builds it, and they exist
because the batcher is about to be rewritten for speed: at 20,000 sprites
it was the largest single Python cost in the engine, and almost all of it
was work it threw away. A rewrite like that is only safe if "the batches
are identical" is something a test can say, so this says it first.

Five properties carry it, and the last two are the ones sabotage had to
find -- every careless rewrite this file was tried against passed the
first three.

1. **Destinations are the camera transform, exactly.** `world * zoom +
   offset`, not approximately -- the batcher is the only place the engine
   applies it to a sprite, and `tests/test_batching_enhanced.py` already
   has the viewport cases that caught it double-counting the origin.
2. **An enabled column is parallel to `destinations`; a disabled one is
   empty.** Every backend indexes the optional lists by the same `i` it
   uses for a destination, so a short column is an `IndexError` in a
   renderer or, worse, a sprite wearing the next sprite's tint.
3. **A neutral command inside an enabled batch keeps the neutral value.**
   One rotated sprite among a thousand upright ones enables the whole
   batch's transform column, and the other thousand entries have to be
   zero rotation and unit scale. An implementation that fills the column
   lazily has to go back and fill in what it skipped, and getting that
   backfill wrong shifts every sprite's transform by one.
4. **Batches break exactly at a texture or material change**, and nowhere
   else -- a tint or a rotation mid-batch must not split the draw call,
   which is the whole reason the columns exist.
5. **A flag is on when, and only when, some command in that batch needs
   it.** Properties 2 and 3 both describe a column *once its flag is on*,
   so neither notices a command whose data is dropped because it never
   turned the flag on -- a sprite scaled but not rotated, or white but
   fading. It draws as though nobody had asked, and nothing complains.

`tests/test_batching_enhanced.py` holds the worked examples with
hand-written expectations; this holds the invariants over randomised
input, so a case nobody thought to write out is still covered.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.batch import Batcher
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.types import RenderBatch, RenderCommand
from pyguara.resources.types import Texture

_NEUTRAL_ROTATION = 0.0
_NEUTRAL_SCALE = (1.0, 1.0)
_OPAQUE_WHITE = (255, 255, 255, 255)


@dataclass
class _Material:
    """Stands in for a `Material`; only `id` reaches the batcher.

    The same stand-in `tests/test_render_sorting.py` uses, and for the
    same reason: a real `Material` needs a `Shader`, and the batcher
    reads nothing but the id.
    """

    id: int


class _Texture(Texture):
    """An identity to group on; nothing here rasterises."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        """What the batcher groups on, by identity."""
        return self._name

    @property
    def width(self) -> int:
        """Nominal."""
        return 16

    @property
    def height(self) -> int:
        """Nominal."""
        return 16

    @property
    def native_handle(self) -> object:
        """No backend resource."""
        return None


def _camera_and_viewport(
    *, zoom: float = 1.0, origin: tuple[int, int] = (0, 0)
) -> tuple[Camera2D, Viewport]:
    """A camera and a viewport that is deliberately not at the origin.

    A fullscreen viewport has offset `(0, 0)` in both axes, which hides an
    error in either term of the transform. These default to a
    letterboxed-and-pillarboxed region for that reason.
    """
    camera = Camera2D(800, 600)
    camera.zoom = zoom
    viewport = Viewport(origin[0], origin[1], 480, 360)
    return camera, viewport


def _random_commands(
    rng: random.Random,
    count: int,
    *,
    textures: int = 3,
    materials: int = 2,
    transformed_odds: float = 0.3,
    tinted_odds: float = 0.3,
    region_odds: float = 0.3,
) -> list[RenderCommand]:
    """A spread of commands covering every combination of the flags.

    Not sorted: `create_batches` is documented to group *consecutive*
    compatible commands, so unsorted input is the harder case and the one
    that produces many short batches.
    """
    texture_pool = [_Texture(f"t{i}") for i in range(textures)]
    material_pool: list[_Material | None] = [
        None,
        *(_Material(index + 1) for index in range(materials)),
    ]
    commands = []
    for _ in range(count):
        # Three ways to be transformed, not one: a sprite can be rotated
        # without being scaled and scaled without being rotated, and an
        # implementation that tests only `rotation != 0.0` drops the scale
        # of the second kind silently.
        transformed = rng.random() < transformed_odds
        kind = rng.choice(("both", "rotation", "scale")) if transformed else "none"
        tinted = rng.random() < tinted_odds
        region = rng.random() < region_odds
        commands.append(
            RenderCommand(
                texture=rng.choice(texture_pool),
                world_position=Vector2(rng.uniform(-500, 500), rng.uniform(-500, 500)),
                layer=rng.randrange(4),
                z_index=rng.uniform(0, 32),
                sort_group=rng.randrange(3),
                rotation=rng.uniform(1, 359) if kind in ("both", "rotation") else 0.0,
                scale=Vector2(rng.uniform(0.5, 2), rng.uniform(0.5, 2))
                if kind in ("both", "scale")
                else Vector2(1, 1),
                material=rng.choice(material_pool),  # type: ignore[arg-type]
                color=Color(rng.randrange(255), rng.randrange(255), 128, 255)
                if tinted
                else Color(255, 255, 255, 255),
                source_rect=Rect(rng.randrange(8), rng.randrange(8), 8, 8)
                if region
                else None,
            )
        )
    return commands


def _is_neutral_transform(command: RenderCommand) -> bool:
    """Whether this command would leave a transform column untouched."""
    return command.rotation == 0.0 and command.scale.x == 1.0 and command.scale.y == 1.0


def _commands_of(batches: list[RenderBatch]) -> list[int]:
    """How many destinations each batch holds, in order."""
    return [len(batch.destinations) for batch in batches]


@pytest.mark.unit
@pytest.mark.parametrize("zoom", [1.0, 0.5, 2.5])
@pytest.mark.parametrize("origin", [(0, 0), (160, 60)])
def test_destinations_are_the_camera_transform_exactly(
    zoom: float, origin: tuple[int, int]
) -> None:
    """`world * zoom + offset`, bit for bit, for every command in order."""
    rng = random.Random(1234)
    commands = _random_commands(rng, 200)
    camera, viewport = _camera_and_viewport(zoom=zoom, origin=origin)
    offset = camera.screen_offset(viewport)

    batches = Batcher().create_batches(commands, camera, viewport)

    produced = [dest for batch in batches for dest in batch.destinations]
    expected = [
        (
            command.world_position.x * zoom + offset.x,
            command.world_position.y * zoom + offset.y,
        )
        for command in commands
    ]
    assert produced == expected


@pytest.mark.unit
def test_every_command_appears_once_and_in_submission_order() -> None:
    """Batching regroups commands; it must not drop or reorder one."""
    rng = random.Random(99)
    commands = _random_commands(rng, 300)
    camera, viewport = _camera_and_viewport()

    batches = Batcher().create_batches(commands, camera, viewport)

    assert sum(_commands_of(batches)) == len(commands)
    textures = [batch.texture for batch in batches for _ in batch.destinations]
    assert textures == [command.texture for command in commands]


@pytest.mark.unit
def test_an_enabled_column_is_parallel_and_a_disabled_one_is_empty() -> None:
    """A column is either exactly as long as `destinations`, or absent.

    This is the invariant every backend relies on: `pack_sprite_instances`
    tests `len(batch.colors) == count` and silently broadcasts white when
    it fails, so a column that is merely *close* to the right length turns
    into a whole batch losing its tint rather than an error.
    """
    rng = random.Random(7)
    commands = _random_commands(rng, 400)
    camera, viewport = _camera_and_viewport()

    batches = Batcher().create_batches(commands, camera, viewport)

    assert batches
    for batch in batches:
        count = len(batch.destinations)
        assert count > 0
        for enabled, column in (
            (batch.transforms_enabled, batch.rotations),
            (batch.transforms_enabled, batch.scales),
            (batch.colors_enabled, batch.colors),
            (batch.source_rects_enabled, batch.source_rects),
        ):
            assert len(column) == (count if enabled else 0)


@pytest.mark.unit
def test_a_neutral_command_keeps_the_neutral_value_in_an_enabled_batch() -> None:
    """The backfill: an upright sprite in a rotated batch stays upright.

    Walks every command, so a column that is correct from the first
    non-neutral entry onwards and wrong before it is caught -- which is
    precisely the shape of a lazy fill that forgets what it skipped.
    """
    rng = random.Random(4242)
    commands = _random_commands(rng, 500)
    camera, viewport = _camera_and_viewport()

    batches = Batcher().create_batches(commands, camera, viewport)

    position = 0
    for batch in batches:
        for index in range(len(batch.destinations)):
            command = commands[position + index]
            if batch.transforms_enabled:
                if _is_neutral_transform(command):
                    assert batch.rotations[index] == _NEUTRAL_ROTATION
                    assert batch.scales[index] == _NEUTRAL_SCALE
                else:
                    assert batch.rotations[index] == command.rotation
                    assert batch.scales[index] == (
                        command.scale.x,
                        command.scale.y,
                    )
            if batch.colors_enabled:
                colour = command.color
                assert batch.colors[index] == (
                    colour.r,
                    colour.g,
                    colour.b,
                    colour.a,
                )
            if batch.source_rects_enabled:
                assert batch.source_rects[index] is command.source_rect
        position += len(batch.destinations)


@pytest.mark.unit
def test_an_all_neutral_batch_leaves_every_optional_column_off() -> None:
    """Nothing enables a column that no command in the batch needs."""
    texture = _Texture("one")
    commands = [
        RenderCommand(
            texture=texture,
            world_position=Vector2(index * 4.0, 0.0),
            layer=0,
            z_index=0.0,
        )
        for index in range(32)
    ]
    camera, viewport = _camera_and_viewport()

    batches = Batcher().create_batches(commands, camera, viewport)

    assert len(batches) == 1
    batch = batches[0]
    assert not batch.transforms_enabled
    assert not batch.colors_enabled
    assert not batch.source_rects_enabled
    assert batch.rotations == []
    assert batch.scales == []
    assert batch.colors == []
    assert batch.source_rects == []


@pytest.mark.unit
def test_the_last_command_can_be_the_one_that_enables_a_column() -> None:
    """The off-by-one a backfill gets wrong at the end of a batch."""
    texture = _Texture("one")
    plain = [
        RenderCommand(
            texture=texture,
            world_position=Vector2(index * 4.0, 0.0),
            layer=0,
            z_index=0.0,
        )
        for index in range(7)
    ]
    last = RenderCommand(
        texture=texture,
        world_position=Vector2(99.0, 0.0),
        layer=0,
        z_index=0.0,
        rotation=90.0,
        color=Color(1, 2, 3, 4),
        source_rect=Rect(1, 1, 2, 2),
    )
    camera, viewport = _camera_and_viewport()

    batches = Batcher().create_batches([*plain, last], camera, viewport)

    assert len(batches) == 1
    batch = batches[0]
    assert batch.rotations == [0.0] * 7 + [90.0]
    assert batch.scales == [_NEUTRAL_SCALE] * 8
    assert batch.colors == [_OPAQUE_WHITE] * 7 + [(1, 2, 3, 4)]
    assert batch.source_rects == [None] * 7 + [last.source_rect]


@pytest.mark.unit
def test_batches_break_at_a_texture_or_material_change_and_nowhere_else() -> None:
    """A tint or a rotation must not split a draw call.

    The batch boundaries are computed here from the commands alone and
    compared with the ones produced, so this fails both ways: a batcher
    that splits too eagerly loses the draw-call saving, and one that
    splits too rarely puts two textures in one batch and draws the wrong
    sprite.
    """
    rng = random.Random(31337)
    commands = _random_commands(rng, 400)
    camera, viewport = _camera_and_viewport()

    expected: list[int] = []
    run = 0
    for index, command in enumerate(commands):
        if index == 0:
            run = 1
            continue
        previous = commands[index - 1]
        if (
            command.texture is previous.texture
            and command.material_id == previous.material_id
        ):
            run += 1
        else:
            expected.append(run)
            run = 1
    expected.append(run)

    batches = Batcher().create_batches(commands, camera, viewport)

    assert _commands_of(batches) == expected


@pytest.mark.unit
def test_a_tint_or_a_rotation_does_not_split_one_texture() -> None:
    """The same claim as a single explicit case, for when the above fails."""
    texture = _Texture("one")
    commands = [
        RenderCommand(
            texture=texture,
            world_position=Vector2(0.0, 0.0),
            layer=0,
            z_index=0.0,
        ),
        RenderCommand(
            texture=texture,
            world_position=Vector2(1.0, 0.0),
            layer=0,
            z_index=0.0,
            rotation=45.0,
        ),
        RenderCommand(
            texture=texture,
            world_position=Vector2(2.0, 0.0),
            layer=0,
            z_index=0.0,
            color=Color(10, 20, 30, 40),
        ),
    ]
    camera, viewport = _camera_and_viewport()

    batches = Batcher().create_batches(commands, camera, viewport)

    assert _commands_of(batches) == [3]


@pytest.mark.unit
def test_two_materials_with_the_same_id_stay_in_one_batch() -> None:
    """Material grouping is by id, and two objects can share one.

    `Material.id` comes from a counter, so distinct instances normally
    differ -- but `_id` is an ordinary dataclass field, so a material
    built with an explicit id, copied or deserialised carries the id it
    was given. The batcher groups by that id, not by object identity, and
    this pins it: an implementation that compares `is` would split a
    batch that has no reason to split.
    """
    texture = _Texture("one")
    shared = _Material(7)
    twin = _Material(7)
    assert shared is not twin
    assert shared.id == twin.id

    commands = [
        RenderCommand(
            texture=texture,
            world_position=Vector2(float(index), 0.0),
            layer=0,
            z_index=0.0,
            material=material,  # type: ignore[arg-type]
        )
        for index, material in enumerate((shared, twin, shared))
    ]
    camera, viewport = _camera_and_viewport()

    batches = Batcher().create_batches(commands, camera, viewport)

    assert _commands_of(batches) == [3]


@pytest.mark.unit
def test_no_commands_produces_no_batches() -> None:
    """The empty frame, which the loop's first-command setup must survive."""
    camera, viewport = _camera_and_viewport()

    assert Batcher().create_batches([], camera, viewport) == []


@pytest.mark.unit
def test_one_command_produces_one_batch() -> None:
    """The other end of the same setup."""
    texture = _Texture("one")
    command = RenderCommand(
        texture=texture,
        world_position=Vector2(5.0, 7.0),
        layer=0,
        z_index=0.0,
    )
    camera, viewport = _camera_and_viewport()

    batches = Batcher().create_batches([command], camera, viewport)

    assert _commands_of(batches) == [1]
    assert batches[0].texture is texture


@pytest.mark.unit
def test_a_batch_flag_depends_only_on_that_batch_s_own_commands() -> None:
    """A transformed batch must not leave the next one on the slow path.

    Found by sabotage: not resetting `has_transforms` between batches
    produces columns that are the right length and hold the right neutral
    values, so every other assertion here passes. What it costs is the
    fast path -- `transforms_enabled` is what the ModernGL renderer reads
    to decide whether to pack rotation and scale at all, and a batch
    wrongly flagged pays for 20,000 rows of zeroes and ones.

    So this is a performance property with no visible symptom, which is
    exactly the kind that rots quietly.
    """
    rotated_texture = _Texture("rotated")
    plain_texture = _Texture("plain")
    tinted_texture = _Texture("tinted")
    region_texture = _Texture("region")
    camera, viewport = _camera_and_viewport()

    commands = [
        RenderCommand(
            texture=rotated_texture,
            world_position=Vector2(0.0, 0.0),
            layer=0,
            z_index=0.0,
            rotation=30.0,
        ),
        RenderCommand(
            texture=tinted_texture,
            world_position=Vector2(1.0, 0.0),
            layer=0,
            z_index=0.0,
            color=Color(1, 2, 3, 4),
        ),
        RenderCommand(
            texture=region_texture,
            world_position=Vector2(2.0, 0.0),
            layer=0,
            z_index=0.0,
            source_rect=Rect(0, 0, 4, 4),
        ),
        # Every flag has now been on in some earlier batch. This one needs
        # none of them.
        RenderCommand(
            texture=plain_texture,
            world_position=Vector2(3.0, 0.0),
            layer=0,
            z_index=0.0,
        ),
    ]

    batches = Batcher().create_batches(commands, camera, viewport)

    assert _commands_of(batches) == [1, 1, 1, 1]
    last = batches[-1]
    assert last.texture is plain_texture
    assert not last.transforms_enabled
    assert not last.colors_enabled
    assert not last.source_rects_enabled
    assert last.rotations == []
    assert last.scales == []
    assert last.colors == []
    assert last.source_rects == []


@pytest.mark.unit
def test_a_flag_is_on_exactly_when_some_command_in_the_batch_needs_it() -> None:
    """Both directions, which the assertions above only half cover.

    Everything else here says what a column holds *once its flag is on*,
    and what the flags are for an all-neutral batch. Neither notices a
    command whose data is quietly dropped because it failed to turn its
    flag on in the first place -- a sabotage that tested only
    `rotation != 0.0` survived every other test in this file, because a
    scaled-but-unrotated sprite then lands in a batch with
    `transforms_enabled` false and its scale discarded. It draws at 1:1
    and nothing says otherwise.

    So the claim has to be an equality: the flag is on when, and only
    when, a command in that batch needs it.
    """
    rng = random.Random(555)
    commands = _random_commands(rng, 600)
    camera, viewport = _camera_and_viewport()

    batches = Batcher().create_batches(commands, camera, viewport)

    position = 0
    for batch in batches:
        count = len(batch.destinations)
        mine = commands[position : position + count]
        assert batch.transforms_enabled == any(
            not _is_neutral_transform(command) for command in mine
        )
        assert batch.colors_enabled == any(
            (command.color.r, command.color.g, command.color.b, command.color.a)
            != _OPAQUE_WHITE
            for command in mine
        )
        assert batch.source_rects_enabled == any(
            command.source_rect is not None for command in mine
        )
        position += count


_SINGLE_DEVIATIONS: list[tuple[str, dict[str, object]]] = [
    ("rotation", {"rotation": 17.0}),
    ("scale x", {"scale": Vector2(2.0, 1.0)}),
    ("scale y", {"scale": Vector2(1.0, 2.0)}),
    ("red", {"color": Color(254, 255, 255, 255)}),
    ("green", {"color": Color(255, 254, 255, 255)}),
    ("blue", {"color": Color(255, 255, 254, 255)}),
    ("alpha", {"color": Color(255, 255, 255, 254)}),
    ("source rect", {"source_rect": Rect(2, 3, 4, 5)}),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("what", "override"), _SINGLE_DEVIATIONS, ids=[d[0] for d in _SINGLE_DEVIATIONS]
)
def test_one_channel_away_from_neutral_still_enables_its_column(
    what: str, override: dict[str, object]
) -> None:
    """Each field decides on its own, and a batch of one proves it.

    The neutral test has to be sensitive to every channel separately,
    because a command that differs in exactly one has no other command to
    turn the flag on for it. Two sabotages survived everything else in
    this file by collapsing one channel:

    - testing the tint as `red != 255 or green != 255 or blue != 255`
      drops the alpha, so a white sprite fading out draws fully opaque for
      its whole life;
    - testing the transform as `rotation != 0.0 or scale_x != 1.0` drops a
      scale that is only in y, so a sprite squashed vertically draws at
      full height.

    Neither has a loud failure. The sprite just renders as though nobody
    had asked, which is why this is parametrised over single channels
    rather than left to randomised commands that vary several at once.
    """
    texture = _Texture("one")
    command = RenderCommand(
        texture=texture,
        world_position=Vector2(1.0, 2.0),
        layer=0,
        z_index=0.0,
        **override,  # type: ignore[arg-type]
    )
    camera, viewport = _camera_and_viewport()

    batches = Batcher().create_batches([command], camera, viewport)

    assert len(batches) == 1
    batch = batches[0]
    if "rotation" in override or "scale" in override:
        assert batch.transforms_enabled, f"{what} did not enable the transform column"
        assert batch.rotations == [command.rotation]
        assert batch.scales == [(command.scale.x, command.scale.y)]
    if "color" in override:
        colour = command.color
        assert batch.colors_enabled, f"{what} did not enable the colour column"
        assert batch.colors == [(colour.r, colour.g, colour.b, colour.a)]
    if "source_rect" in override:
        assert batch.source_rects_enabled, f"{what} did not enable the rect column"
        assert batch.source_rects == [command.source_rect]
