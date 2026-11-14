"""Does the native mirror of static solids answer exactly as Chipmunk does?

`PymunkEngine` may answer box overlaps, whole swept moves and ray misses
from `NativeSolids` instead of building probe shapes for Chipmunk. This
suite holds an engine with the mirror off beside one with it on, over the
same geometry, and compares with `==` -- including the *types* of the
numbers, because a position that was an int in one path and a float in the
other encodes differently on the wire.

There is no tolerance to state, and the reason is the mirror's contract
rather than luck: it answers only when it is certain and defers to
Chipmunk for anything within a millionth of a pixel of touching, and for
which of several overlapping boxes to name. So a disagreement here is
never a rounding difference. It is a bug.

**The geometry is built to be awkward.** Uniform random boxes almost never
touch a probe edge-on, and would leave the deferral path untested. Half
the worlds here are tile grids whose edges land exactly where a skinned
probe's edges do, and `TestTheFastPathIsActuallyTaken` counts deferrals so
that a mirror declining everything -- which would pass every comparison --
fails.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.native import native_module
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.character_mover import SKIN, CharacterMover, MoveResult
from pyguara.physics.types import (
    BodyType,
    CollisionLayer,
    PhysicsMaterial,
    ShapeType,
)

pytestmark = pytest.mark.skipif(
    native_module() is None or not hasattr(native_module(), "NativeSolids"),
    reason="native extension not built; `make native`",
)

Box = tuple[float, float, float, float]


def _add_box(
    engine: PymunkEngine,
    name: str,
    box: Box,
    *,
    body_type: BodyType = BodyType.STATIC,
    sensor: bool = False,
    layer: CollisionLayer | None = None,
    shape: ShapeType = ShapeType.BOX,
) -> Any:
    x, y, width, height = box
    body = engine.create_body(name, body_type, Vector2(x, y))
    dimensions = [width / 2] if shape is ShapeType.CIRCLE else [width, height]
    engine.add_shape(
        body,
        shape,
        dimensions,
        Vector2(0, 0),
        PhysicsMaterial(),
        layer or CollisionLayer(),
        sensor,
    )
    return body


def _pair(boxes: list[Box]) -> tuple[PymunkEngine, PymunkEngine]:
    """The same static boxes in a Chipmunk-only engine and a mirrored one."""
    engines = (PymunkEngine(accelerate=False), PymunkEngine(accelerate=True))
    for engine in engines:
        engine.initialize(Vector2(0, 0))
        for number, box in enumerate(boxes):
            _add_box(engine, f"wall{number}", box)
    return engines


def _scattered(stream: RandomStream, count: int) -> list[Box]:
    """Boxes anywhere, any size, freely overlapping one another."""
    return [
        (
            stream.uniform(-300, 300),
            stream.uniform(-300, 300),
            stream.uniform(4, 120),
            stream.uniform(4, 120),
        )
        for _ in range(count)
    ]


def _tiles(stream: RandomStream, size: float) -> list[Box]:
    """A grid of abutting tiles with holes: every wall is several boxes."""
    return [
        (column * size, row * size, size, size)
        for row in range(-6, 7)
        for column in range(-6, 7)
        if stream.random() < 0.3
    ]


def _shaved(stream: RandomStream) -> list[Box]:
    """Tiles whose edges sit exactly a skin's width off the pixel grid.

    A mover of half extent 10 probes with 9.95, so its edges fall on
    `n + 0.05` and `n + 0.95`. These walls have edges there too, which is
    where a probe exactly touches a wall and the mirror has to defer.
    """
    boxes: list[Box] = []
    for row in range(-4, 5):
        for column in range(-4, 5):
            if stream.random() < 0.3:
                boxes.append((column * 40 + 0.05, row * 40 - 0.05, 39.9, 39.9))
    return boxes


WORLDS = [
    pytest.param(lambda s: _scattered(s, 6), id="few-scattered"),
    pytest.param(lambda s: _scattered(s, 80), id="many-scattered"),
    pytest.param(lambda s: _tiles(s, 32.0), id="tiles"),
    pytest.param(lambda s: _tiles(s, 20.0), id="small-tiles"),
    pytest.param(_shaved, id="edges-on-the-skin"),
    pytest.param(lambda s: [], id="empty"),
]


def _hit(result: Any) -> str:
    """A ray's result as text, so two NaNs compare equal.

    A ray that starts inside a box comes back from Chipmunk with a
    `(nan, nan)` normal, and NaN is not equal to itself: `==` on two
    identical hits would fail. `repr` round-trips every float exactly, so
    this is no looser.
    """
    return repr(result)


def _exact(result: MoveResult) -> tuple[Any, ...]:
    """A move's result with every number's type beside its value."""
    numbers = (*result.position, *result.remainder)
    return (
        numbers,
        tuple(type(number) for number in numbers),
        result.hit_x,
        result.hit_y,
        result.blocking_x,
        result.blocking_y,
        result.grounded,
    )


@pytest.mark.parametrize("build", WORLDS)
@pytest.mark.parametrize("seed", range(4))
class TestSweptMoves:
    def test_a_walk_ends_in_the_same_place(self, build: Any, seed: int) -> None:
        # A walk rather than independent moves: each move starts where the
        # last one ended, pressed against whatever stopped it, which is
        # where a character spends its time and where the edge cases are.
        stream = RandomStream(seed)
        slow, fast = (CharacterMover(engine) for engine in _pair(build(stream)))
        half = Vector2(stream.choice([6.0, 10.0, 12.5]), stream.choice([6.0, 10.0]))
        position = Vector2(stream.uniform(-200, 200), stream.uniform(-200, 200))
        remainder = Vector2(0.0, 0.0)
        heading = stream.uniform(0, math.tau)

        for _ in range(250):
            if stream.random() < 0.1:
                heading = stream.uniform(0, math.tau)
            speed = stream.choice([0.3, 2.5, 7.0, 40.0])
            delta = Vector2(math.cos(heading) * speed, math.sin(heading) * speed)

            expected = slow.move(position, half, delta, remainder, "mover")
            actual = fast.move(position, half, delta, remainder, "mover")

            assert _exact(actual) == _exact(expected)
            position, remainder = expected.position, expected.remainder

    def test_whole_pixel_positions_stay_whole(self, build: Any, seed: int) -> None:
        # Integer inputs: the Python loop keeps them integers, and so must
        # the native path, which computes in floats.
        stream = RandomStream(1000 + seed)
        slow, fast = (CharacterMover(engine) for engine in _pair(build(stream)))
        position = Vector2(stream.randint(-200, 200), stream.randint(-200, 200))

        for _ in range(150):
            delta = Vector2(stream.randint(-9, 9), stream.randint(-9, 9))
            remainder = Vector2(0, 0)

            expected = slow.move(position, Vector2(10, 10), delta, remainder, "m")
            actual = fast.move(position, Vector2(10, 10), delta, remainder, "m")

            assert _exact(actual) == _exact(expected)
            position = expected.position

    def test_probes_agree(self, build: Any, seed: int) -> None:
        stream = RandomStream(2000 + seed)
        slow, fast = (CharacterMover(engine) for engine in _pair(build(stream)))

        for _ in range(300):
            position = Vector2(
                float(stream.randint(-250, 250)), float(stream.randint(-250, 250))
            )
            direction = Vector2(stream.choice([-1, 0, 1]), stream.choice([-1, 0, 1]))

            assert fast.probe(position, Vector2(10, 10), direction) == slow.probe(
                position, Vector2(10, 10), direction
            )


@pytest.mark.parametrize("build", WORLDS)
@pytest.mark.parametrize("seed", range(3))
class TestQueries:
    def test_box_overlaps_agree(self, build: Any, seed: int) -> None:
        stream = RandomStream(3000 + seed)
        slow, fast = _pair(build(stream))

        for _ in range(600):
            centre = Vector2(stream.uniform(-320, 320), stream.uniform(-320, 320))
            half = Vector2(stream.uniform(0.01, 30), stream.uniform(0.01, 30))
            ignore = stream.choice([None, "wall0", "wall3", "nobody"])

            assert fast.overlap_box(
                centre, half, ignore_entity_id=ignore
            ) == slow.overlap_box(centre, half, ignore_entity_id=ignore)

    def test_rays_agree(self, build: Any, seed: int) -> None:
        stream = RandomStream(4000 + seed)
        slow, fast = _pair(build(stream))

        for _ in range(600):
            start = Vector2(stream.uniform(-320, 320), stream.uniform(-320, 320))
            end = Vector2(stream.uniform(-320, 320), stream.uniform(-320, 320))
            ignore = stream.choice([None, None, "wall1"])

            assert _hit(fast.raycast(start, end, ignore_entity_id=ignore)) == _hit(
                slow.raycast(start, end, ignore_entity_id=ignore)
            )

    def test_axis_aligned_rays_agree(self, build: Any, seed: int) -> None:
        # A ray along a wall's face is the graze a slab test can get wrong.
        stream = RandomStream(5000 + seed)
        slow, fast = _pair(build(stream))

        for _ in range(300):
            fixed = float(stream.randint(-200, 200)) + stream.choice([0.0, 0.5, 1.0])
            low, high = stream.uniform(-320, 0), stream.uniform(0, 320)
            for start, end in (
                (Vector2(low, fixed), Vector2(high, fixed)),
                (Vector2(fixed, low), Vector2(fixed, high)),
            ):
                assert _hit(fast.raycast(start, end)) == _hit(slow.raycast(start, end))


class TestWhatSabotageFound:
    """Each of these was missing, and a deliberately broken build passed.

    Rounding ties away from zero instead of to even, and ignoring a ray's
    radius, both left all 146 other tests green. A random float almost
    never lands on a tie or within a pixel of a face, so neither is
    reachable by the sweeps above; they have to be aimed at.
    """

    @pytest.mark.parametrize("distance", [0.5, -0.5, 1.5, 2.5, -2.5, 3.5, 6.5])
    def test_a_half_pixel_rounds_as_python_rounds(self, distance: float) -> None:
        # `round(0.5)` is 0 and `round(2.5)` is 2 in Python: ties go to
        # even. Rounding half away from zero moves a pixel further.
        slow, fast = (CharacterMover(engine) for engine in _pair([]))

        for delta in (Vector2(distance, 0.0), Vector2(0.0, distance)):
            assert _exact(fast.move(Vector2(0.0, 0.0), Vector2(8, 8), delta)) == (
                _exact(slow.move(Vector2(0.0, 0.0), Vector2(8, 8), delta))
            )

    def test_a_banked_remainder_reaching_a_tie_rounds_the_same(self) -> None:
        slow, fast = (CharacterMover(engine) for engine in _pair([]))
        position, remainder = Vector2(0.0, 0.0), Vector2(0.0, 0.0)

        for _ in range(40):
            expected = slow.move(
                position, Vector2(8, 8), Vector2(0.25, -0.125), remainder
            )
            actual = fast.move(
                position, Vector2(8, 8), Vector2(0.25, -0.125), remainder
            )
            assert _exact(actual) == _exact(expected)
            position, remainder = expected.position, expected.remainder

    @pytest.mark.parametrize("offset", [0.25, 0.5, 0.9, 0.999, 1.0, 1.001, 1.5])
    def test_a_ray_has_a_radius(self, offset: float) -> None:
        # A ray is a swept circle of radius 1 in Chipmunk, so one passing
        # half a pixel outside a wall still hits it.
        slow, fast = _pair([(0.0, 0.0, 40.0, 40.0)])
        rays = [
            (Vector2(20.0 + offset, -100.0), Vector2(20.0 + offset, 100.0)),
            (Vector2(-20.0 - offset, -100.0), Vector2(-20.0 - offset, 100.0)),
            (Vector2(-100.0, 20.0 + offset), Vector2(100.0, 20.0 + offset)),
            (Vector2(-100.0, -20.0 - offset), Vector2(100.0, -20.0 - offset)),
            # Stopping short of the face, by less than the radius or more.
            (Vector2(-100.0, 0.0), Vector2(-20.0 - offset, 0.0)),
        ]

        for start, end in rays:
            assert _hit(fast.raycast(start, end)) == _hit(slow.raycast(start, end))

    def test_a_ray_past_a_corner_is_still_within_reach_of_it(self) -> None:
        slow, fast = _pair([(0.0, 0.0, 40.0, 40.0)])

        for nudge in (0.2, 0.6, 0.7, 0.8, 1.2):
            start = Vector2(20.0 + nudge, 60.0)
            end = Vector2(60.0, 20.0 + nudge)
            assert _hit(fast.raycast(start, end)) == _hit(slow.raycast(start, end))


class TestFilters:
    def test_masks_and_categories_are_honoured_alike(self) -> None:
        engines = (PymunkEngine(accelerate=False), PymunkEngine(accelerate=True))
        layers = [
            CollisionLayer(category=0b0001, mask=0xFFFFFFFF),
            CollisionLayer(category=0b0010, mask=0xFFFFFFFF),
            CollisionLayer(category=0b0100, mask=0),
            CollisionLayer(category=0b1000, mask=0b0001),
        ]
        for engine in engines:
            engine.initialize(Vector2(0, 0))
            for number, layer in enumerate(layers):
                _add_box(engine, f"w{number}", (number * 100.0, 0, 40, 40), layer=layer)
        slow, fast = engines

        for mask in (0xFFFFFFFF, 0b0001, 0b0010, 0b0110, 0b1000, 0):
            for number in range(len(layers)):
                centre = Vector2(number * 100.0, 0)
                assert fast.overlap_box(
                    centre, Vector2(5, 5), mask=mask
                ) == slow.overlap_box(centre, Vector2(5, 5), mask=mask)
                start, end = Vector2(number * 100.0 - 50, 0), Vector2(number * 100.0, 0)
                assert _hit(fast.raycast(start, end, mask=mask)) == _hit(
                    slow.raycast(start, end, mask=mask)
                )

    def test_a_sensor_does_not_block_and_is_not_mirrored(self) -> None:
        slow, fast = _pair([(100.0, 0.0, 40.0, 40.0)])
        for engine in (slow, fast):
            _add_box(engine, "zone", (0.0, 0.0, 60.0, 60.0), sensor=True)

        assert fast.overlap_box(Vector2(0, 0), Vector2(5, 5)) is None
        assert slow.overlap_box(Vector2(0, 0), Vector2(5, 5)) is None
        # With a sensor in the space a ray is Chipmunk's to answer, since
        # the mirror does not hold it. Either way the answers match.
        for end in (Vector2(0, 0), Vector2(100, 0), Vector2(-200, 0)):
            assert _hit(fast.raycast(Vector2(-100, 0), end)) == _hit(
                slow.raycast(Vector2(-100, 0), end)
            )


class TestTheMirrorStepsAside:
    """Anything it cannot hold exactly switches it off, rather than bending it."""

    @pytest.mark.parametrize(
        "extra",
        [
            pytest.param({"body_type": BodyType.DYNAMIC}, id="a-dynamic-body"),
            pytest.param({"body_type": BodyType.KINEMATIC}, id="a-kinematic-body"),
            pytest.param({"shape": ShapeType.CIRCLE}, id="a-circle"),
        ],
    )
    def test_a_solid_it_cannot_mirror(self, extra: dict[str, Any]) -> None:
        slow, fast = _pair([(100.0, 0.0, 40.0, 40.0)])
        for engine in (slow, fast):
            _add_box(engine, "odd", (0.0, 100.0, 30.0, 30.0), **extra)

        assert fast._static_solids() is None
        for centre in (Vector2(100, 0), Vector2(0, 100), Vector2(-200, -200)):
            assert fast.overlap_box(centre, Vector2(8, 8)) == slow.overlap_box(
                centre, Vector2(8, 8)
            )

    def test_a_rotated_wall(self) -> None:
        slow, fast = _pair([])
        for engine in (slow, fast):
            _add_box(engine, "tilted", (0.0, 0.0, 100.0, 10.0)).rotation = 30.0

        assert fast._static_solids() is None
        # Inside the wall's bounding box but outside the wall itself.
        corner = Vector2(40, -20)
        assert fast.overlap_box(corner, Vector2(2, 2)) == slow.overlap_box(
            corner, Vector2(2, 2)
        )

    def test_switched_off(self) -> None:
        slow, _ = _pair([(0.0, 0.0, 40.0, 40.0)])

        assert slow._static_solids() is None


class TestTheMirrorKeepsUp:
    def test_a_wall_added_later_blocks(self) -> None:
        slow, fast = _pair([(0.0, 0.0, 40.0, 40.0)])
        assert fast.overlap_box(Vector2(200, 0), Vector2(5, 5)) is None

        for engine in (slow, fast):
            _add_box(engine, "late", (200.0, 0.0, 40.0, 40.0))

        assert fast.overlap_box(Vector2(200, 0), Vector2(5, 5)) == "late"
        assert slow.overlap_box(Vector2(200, 0), Vector2(5, 5)) == "late"

    def test_a_destroyed_wall_stops_blocking(self) -> None:
        slow, fast = _pair([(0.0, 0.0, 40.0, 40.0)])
        assert fast.overlap_box(Vector2(0, 0), Vector2(5, 5)) == "wall0"

        for engine in (slow, fast):
            engine.destroy_body(engine._bodies["wall0"])

        assert fast.overlap_box(Vector2(0, 0), Vector2(5, 5)) is None
        assert slow.overlap_box(Vector2(0, 0), Vector2(5, 5)) is None

    def test_a_moved_static_wall_is_where_chipmunk_thinks_it_is(self) -> None:
        # Chipmunk does not reindex a static body that is repositioned, so
        # its queries keep answering from the old place. That is an engine
        # quirk and not this suite's to judge: the mirror must share it.
        slow, fast = _pair([(0.0, 0.0, 40.0, 40.0)])
        assert fast.overlap_box(Vector2(0, 0), Vector2(5, 5)) == "wall0"

        for engine in (slow, fast):
            engine._bodies["wall0"].position = Vector2(300, 0)

        for centre in (Vector2(0, 0), Vector2(300, 0)):
            assert fast.overlap_box(centre, Vector2(5, 5)) == slow.overlap_box(
                centre, Vector2(5, 5)
            )

    def test_a_cleaned_up_engine_answers_nothing(self) -> None:
        _, fast = _pair([(0.0, 0.0, 40.0, 40.0)])
        assert fast.overlap_box(Vector2(0, 0), Vector2(5, 5)) == "wall0"

        fast.cleanup()

        assert fast.overlap_box(Vector2(0, 0), Vector2(5, 5)) is None
        assert fast.raycast(Vector2(-50, 0), Vector2(50, 0)) is None


class TestItAddsNoWayIntoTheEngine:
    def test_a_body_handle_can_be_deep_copied_without_reaching_the_engine(
        self,
    ) -> None:
        # Studio deep-copies a scene to snapshot it, `RigidBody` handles
        # included. The first version of the mirror gave each handle a
        # bound method of the engine, and the copy followed it into the
        # engine, its bodies and their entities.
        import copy

        _, fast = _pair([(0.0, 0.0, 40.0, 40.0)])
        handle = fast._bodies["wall0"]

        for value in vars(handle).values():
            assert getattr(value, "__self__", None) is not fast
        twin_flag = copy.deepcopy(handle._static_moved)
        assert twin_flag == handle._static_moved


class TestOddInputs:
    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_a_non_finite_move_fails_the_same_way(self, bad: float) -> None:
        slow, fast = (
            CharacterMover(engine) for engine in _pair([(50.0, 0.0, 20.0, 20.0)])
        )
        outcomes = []
        for mover in (slow, fast):
            try:
                outcomes.append(
                    _exact(
                        mover.move(Vector2(0.0, 0.0), Vector2(5, 5), Vector2(bad, 0.0))
                    )
                )
            except (ValueError, OverflowError) as error:
                outcomes.append(type(error))

        assert outcomes[0] == outcomes[1]

    def test_a_non_finite_probe_is_left_to_chipmunk(self) -> None:
        slow, fast = _pair([(0.0, 0.0, 40.0, 40.0)])

        assert fast.overlap_box(Vector2(math.nan, 0), Vector2(5, 5)) == (
            slow.overlap_box(Vector2(math.nan, 0), Vector2(5, 5))
        )

    def test_a_mask_chipmunk_refuses_is_refused_the_same_way(self) -> None:
        # Chipmunk's filter is unsigned; the mirror must not quietly accept
        # a mask the slow path raises on.
        slow, fast = _pair([(0.0, 0.0, 40.0, 40.0)])

        for engine in (slow, fast):
            with pytest.raises(OverflowError):
                engine.overlap_box(Vector2(500, 500), Vector2(5, 5), mask=-1)


class TestTheFastPathIsActuallyTaken:
    """A mirror that declined everything would pass every comparison above."""

    def _count(self, engine: PymunkEngine) -> list[int]:
        calls: list[int] = []
        exact, cast = engine._overlap_box_exact, engine.space.segment_query_first  # type: ignore[union-attr]
        engine._overlap_box_exact = lambda *a: calls.append(1) or exact(*a)  # type: ignore[method-assign]
        engine.space.segment_query_first = lambda *a: calls.append(1) or cast(*a)  # type: ignore[union-attr,method-assign]
        return calls

    def test_open_ground_never_reaches_chipmunk(self) -> None:
        _, fast = _pair(_scattered(RandomStream(7), 40))
        calls = self._count(fast)
        mover = CharacterMover(fast)

        for step in range(200):
            mover.move(
                Vector2(2000.0 + step, 2000.0), Vector2(10, 10), Vector2(3.3, 1.1)
            )
            fast.raycast(Vector2(2000.0, 2000.0 + step), Vector2(2400.0, 2100.0))

        assert calls == []

    def test_a_single_wall_is_named_without_chipmunk(self) -> None:
        _, fast = _pair([(100.0, 0.0, 40.0, 40.0)])
        calls = self._count(fast)

        result = CharacterMover(fast).move(
            Vector2(50.0, 0.0), Vector2(10, 10), Vector2(60.0, 0.0)
        )

        assert result.blocking_x == "wall0" and result.position == Vector2(70.0, 0.0)
        assert calls == []

    def test_two_walls_at_once_cost_one_question(self) -> None:
        # Abutting tiles: the blocked pixel overlaps both, and only
        # Chipmunk knows which it would name. One query for that pixel,
        # not one per pixel travelled.
        _, fast = _pair([(100.0, -16.0, 32.0, 32.0), (100.0, 16.0, 32.0, 32.0)])
        calls = self._count(fast)

        result = CharacterMover(fast).move(
            Vector2(20.0, 0.0), Vector2(10, 10), Vector2(90.0, 0.0)
        )

        assert result.hit_x and result.blocking_x in {"wall0", "wall1"}
        assert len(calls) == 1

    def test_an_exact_touch_is_deferred_not_guessed(self) -> None:
        # The probe's right edge is 30 + 9.95 = 39.95, the wall's left
        # edge is 39.95: touching. Chipmunk counts a touch as an overlap;
        # the mirror must not decide that for itself.
        slow, fast = _pair([(59.95, 0.0, 40.0, 40.0)])
        calls = self._count(fast)
        half = Vector2(10 - SKIN, 10 - SKIN)

        assert fast.overlap_box(Vector2(30.0, 0.0), half) == slow.overlap_box(
            Vector2(30.0, 0.0), half
        )
        assert len(calls) == 1
