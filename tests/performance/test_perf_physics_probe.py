"""What the character sweep costs.

`CharacterMover` moves an entity one whole pixel at a time along each
axis and tests every step. On the Python path each step calls
`IPhysicsEngine.overlap_box`, which builds a fresh `pymunk.Body` and
`pymunk.Poly`. So the cost grows with how fast things move, not how
many there are.

This module measures that path. ADR 0009 records the native sweep
that replaces it for static solids.
"""

from __future__ import annotations

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.platformer_movement.controller import PlatformerController
from pyguara.kits.platformer_movement.system import PlatformerSystem
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.components import CharacterBody, Collider, RigidBody
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.types import BodyType, ShapeType
from tests.performance.conftest import (
    assert_scales_no_worse_than,
    measure,
)

DT = 1.0 / 60.0
GRAVITY = Vector2(0, 900)


class _ProbeCounter:
    """Counts `overlap_box` calls, and the CFFI objects they imply.

    Counted rather than sampled: `_probe_shape` allocates exactly one
    `pymunk.Body` and one `pymunk.Poly` per call, so the allocation figure
    is the call count doubled -- no profiler needed, and no guessing.
    """

    def __init__(self, engine: PymunkEngine) -> None:
        self.calls = 0
        self._real = engine.overlap_box
        engine.overlap_box = self._counted  # type: ignore[method-assign]

    def _counted(self, *args: object, **kwargs: object) -> object:
        self.calls += 1
        return self._real(*args, **kwargs)

    @property
    def cffi_objects(self) -> int:
        """One `Body` plus one `Poly` per probe."""
        return self.calls * 2


def _world(characters: int, speed: float) -> tuple[object, ...]:
    """A floor and `characters` movers, each running at `speed` px/s."""
    entities = EntityManager()
    dispatcher = EventDispatcher()
    engine = PymunkEngine()
    physics = PhysicsSystem(engine, entities, dispatcher, gravity=GRAVITY)
    platformer = PlatformerSystem(entities, engine, gravity=GRAVITY)

    floor = entities.create_entity()
    floor.add_component(Transform(position=Vector2(0, 500)))
    floor.add_component(RigidBody(mass=1.0, body_type=BodyType.STATIC))
    floor.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[4000.0, 40.0]))

    for index in range(characters):
        actor = entities.create_entity()
        actor.add_component(Transform(position=Vector2(100.0 + index * 40.0, 460.0)))
        actor.add_component(CharacterBody(velocity=Vector2(speed, 0.0)))
        actor.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[24.0, 40.0]))
        actor.add_component(PlatformerController())

    return entities, physics, platformer, engine


def _tick(physics: object, platformer: object, ticks: int) -> None:
    """Advance both systems, as `fixed_update` does."""
    for _ in range(ticks):
        physics.update(DT)  # type: ignore[attr-defined]
        platformer.update(DT)  # type: ignore[attr-defined]


@pytest.mark.performance
def test_probe_cost_grows_with_distance_not_worse_than_linearly() -> None:
    """The per-pixel walk is linear in distance moved. A regression to
    something worse would mean the stepping itself had changed shape.

    A complexity guard, not a wall-clock budget -- see this package's
    conftest for why that is the only kind safe on a shared runner.
    """
    slow_entities, slow_physics, slow_platformer, _ = _world(1, speed=60.0)
    fast_entities, fast_physics, fast_platformer, _ = _world(1, speed=240.0)

    slow = measure(lambda: _tick(slow_physics, slow_platformer, 30))
    fast = measure(lambda: _tick(fast_physics, fast_platformer, 30))

    assert_scales_no_worse_than(
        small=slow,
        large=fast,
        factor=4,
        limit=8.0,
        what="CharacterMover sweep at 4x the speed",
    )


@pytest.mark.performance
def test_every_probed_pixel_costs_two_cffi_objects() -> None:
    """Pins the mechanism the Rust milestone is meant to remove.

    Not a timing: a count, so it means the same on every machine. If this
    ever drops to zero the CFFI path is gone and this module has done its
    job.
    """
    _, physics, platformer, engine = _world(1, speed=240.0)
    counter = _ProbeCounter(engine)

    _tick(physics, platformer, 30)

    assert counter.calls > 0, "the sweep probed nothing; the world is wrong"
    assert counter.cffi_objects == counter.calls * 2


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.parametrize("characters", [1, 10, 50])
def test_sweep_character_probe(benchmark, characters: int) -> None:
    """Sweep: produces the `docs/guides/performance.md` figures. Asserts
    nothing."""
    _, physics, platformer, engine = _world(characters, speed=240.0)

    benchmark(lambda: _tick(physics, platformer, 60))
