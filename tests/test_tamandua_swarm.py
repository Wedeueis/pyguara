"""Tests for the Revoada: the pool, the tint curve and the batch.

`build_batch()` is pure by design (GDD §4.2), and these are what that
design constraint buys: the demo cannot boot headlessly -- it is ModernGL
and SDL's dummy driver has no OpenGL -- so without a pure function from
swarm state to a `RenderBatch`, the tint showcase would ship covered by a
manual smoke test and nothing else.
"""

from __future__ import annotations

import pytest

from games.tamandua_murundus.components import Insect
from games.tamandua_murundus.swarm import (
    INSECT_DULL,
    INSECT_LIT,
    Swarm,
    SwarmBatchInput,
    build_batch,
    insect_tint,
)
from pyguara.ai.flocking_system import FlockingAgent
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.spatial.components import SpatialTracked

ARENA = Rect(0, 0, 800, 600)


class FakeTexture:
    """A texture with a size and no pixels behind it."""

    width = 8
    height = 8
    path = "<insect>"


def make_swarm(cap: int = 6, decorative: int = 4) -> tuple[Swarm, EntityManager]:
    """A small swarm over a fresh world."""
    entity_manager = EntityManager()
    swarm = Swarm(
        entity_manager,
        ARENA,
        RandomStream(seed=5),
        cap=cap,
        decorative=decorative,
    )
    return swarm, entity_manager


class TestTintCurve:
    def test_no_glow_is_the_daytime_brown(self) -> None:
        assert insect_tint(0.0) == INSECT_DULL

    def test_full_glow_is_bioluminescent(self) -> None:
        assert insect_tint(1.0) == INSECT_LIT

    def test_the_curve_is_continuous_between_them(self) -> None:
        midpoint = insect_tint(0.5)

        assert INSECT_DULL.g < midpoint.g < INSECT_LIT.g

    def test_glow_is_clamped_at_both_ends(self) -> None:
        """A caller driving this off an unclamped curve -- an ambient
        cycle's phase, from D3 -- must not be able to push the colour past
        either end."""
        assert insect_tint(-2.0) == INSECT_DULL
        assert insect_tint(9.0) == INSECT_LIT


class TestBuildBatch:
    def test_both_layers_land_in_one_batch(self) -> None:
        """The demo's whole claim: one texture, N colours, one draw call.
        Splitting the layers would be two draw calls proving half as much.
        """
        batch = build_batch(
            SwarmBatchInput(
                texture=FakeTexture(),
                interactive=[(1.0, 2.0), (3.0, 4.0)],
                decorative=[(5.0, 6.0)],
                glow=0.0,
            )
        )

        assert len(batch.destinations) == 3

    def test_the_batch_is_tinted(self) -> None:
        """`colors_enabled` is what makes the GL backend read the colours
        at all -- without it the swarm renders white."""
        batch = build_batch(
            SwarmBatchInput(
                texture=FakeTexture(),
                interactive=[(1.0, 2.0)],
                decorative=[],
                glow=1.0,
            )
        )

        assert batch.colors_enabled is True
        assert batch.colors[0][:3] == (INSECT_LIT.r, INSECT_LIT.g, INSECT_LIT.b)

    def test_every_instance_has_a_colour_and_a_scale(self) -> None:
        """The GL pack broadcasts white when the lengths do not match, so
        a short list is a silently untinted swarm."""
        batch = build_batch(
            SwarmBatchInput(
                texture=FakeTexture(),
                interactive=[(1.0, 2.0)] * 3,
                decorative=[(5.0, 6.0)] * 7,
                glow=0.5,
            )
        )

        assert len(batch.colors) == len(batch.destinations)
        assert len(batch.scales) == len(batch.destinations)
        assert len(batch.rotations) == len(batch.destinations)

    def test_the_decorative_layer_is_dimmer_not_a_different_colour(self) -> None:
        """It is the same insects further away; a second hue would read as
        a second species."""
        batch = build_batch(
            SwarmBatchInput(
                texture=FakeTexture(),
                interactive=[(1.0, 2.0)],
                decorative=[(5.0, 6.0)],
                glow=0.7,
            )
        )
        near, far = batch.colors[0], batch.colors[1]

        assert near[:3] == far[:3]
        assert far[3] < near[3]

    def test_the_decorative_layer_is_drawn_smaller(self) -> None:
        batch = build_batch(
            SwarmBatchInput(
                texture=FakeTexture(),
                interactive=[(1.0, 2.0)],
                decorative=[(5.0, 6.0)],
                glow=0.0,
            )
        )

        assert batch.scales[1][0] < batch.scales[0][0]

    def test_an_empty_swarm_produces_an_empty_batch(self) -> None:
        batch = build_batch(
            SwarmBatchInput(
                texture=FakeTexture(), interactive=[], decorative=[], glow=0.0
            )
        )

        assert batch.destinations == []

    def test_build_batch_is_pure(self) -> None:
        """The design constraint, made executable: same input, same batch,
        and the input is not mutated on the way through."""
        state = SwarmBatchInput(
            texture=FakeTexture(),
            interactive=[(1.0, 2.0), (3.0, 4.0)],
            decorative=[(5.0, 6.0)],
            glow=0.35,
        )
        before = (list(state.interactive), list(state.decorative), state.glow)

        first = build_batch(state)
        second = build_batch(state)

        assert first.destinations == second.destinations
        assert first.colors == second.colors
        assert (state.interactive, state.decorative, state.glow) == before


class TestPooling:
    def test_an_idle_insect_is_invisible_to_the_flocking_query(self) -> None:
        """The performance decision this module turns on. A pooled entity
        is never destroyed, so a `FlockingAgent` attached at construction
        would keep every insect in `FlockingSystem`'s query for the life
        of the scene -- measured at ~45 fps down to ~18.
        """
        swarm, entity_manager = make_swarm(cap=50)

        agents = sum(1 for _ in entity_manager.get_entities_with(FlockingAgent))

        assert swarm.active_count == 0
        assert agents == 0

    def test_an_idle_insect_is_invisible_to_the_spatial_index(self) -> None:
        """Same reason: `SpatialIndexSystem` re-inserts every tracked
        entity every tick, whether it is out of the pool or not."""
        _, entity_manager = make_swarm(cap=50)

        tracked = sum(1 for _ in entity_manager.get_entities_with(SpatialTracked))

        assert tracked == 0

    def test_releasing_an_insect_makes_it_visible_to_both(self) -> None:
        swarm, entity_manager = make_swarm()

        swarm.release_at(Vector2(100, 100), "mound")

        assert sum(1 for _ in entity_manager.get_entities_with(FlockingAgent)) == 1
        assert sum(1 for _ in entity_manager.get_entities_with(SpatialTracked)) == 1

    def test_killing_an_insect_takes_it_back_out_of_both(self) -> None:
        swarm, entity_manager = make_swarm()
        insect = swarm.release_at(Vector2(100, 100), "mound")
        assert insect is not None

        swarm.kill(insect)

        assert swarm.active_count == 0
        assert sum(1 for _ in entity_manager.get_entities_with(FlockingAgent)) == 0
        assert sum(1 for _ in entity_manager.get_entities_with(SpatialTracked)) == 0

    def test_a_recycled_insect_comes_back_whole(self) -> None:
        """A pooled insect is reused, so anything a kill left behind --
        zero health, a stale anchor -- has to be reset on the way out."""
        swarm, _ = make_swarm()
        first = swarm.release_at(Vector2(100, 100), "mound-a")
        assert first is not None
        first.get_component(Insect).health = 0.0
        swarm.kill(first)

        second = swarm.release_at(Vector2(300, 300), "mound-b")

        assert second is not None
        assert second.get_component(Insect).health == pytest.approx(1.0)
        assert second.get_component(Insect).anchor == "mound-b"

    def test_an_exhausted_pool_declines_rather_than_growing(self) -> None:
        """The cap doing its job, not an error -- `SWARM_CAP` is a
        measurement and the pool is what enforces it."""
        swarm, _ = make_swarm(cap=2)

        swarm.release_at(Vector2(1, 1), "m")
        swarm.release_at(Vector2(2, 2), "m")

        assert swarm.release_at(Vector2(3, 3), "m") is None

    def test_a_released_insect_starts_moving(self) -> None:
        """A boid with zero velocity and no seek target has nothing to
        steer away from and sits still."""
        swarm, _ = make_swarm()

        insect = swarm.release_at(Vector2(100, 100), "mound")

        assert insect is not None
        assert insect.get_component(FlockingAgent).velocity.magnitude > 0.0


class TestDecorativeLayer:
    def test_motes_drift(self) -> None:
        swarm, _ = make_swarm(decorative=5)
        before = [mote.position.x for mote in swarm.motes]

        swarm.update_motes(0.1)

        assert [mote.position.x for mote in swarm.motes] != before

    def test_motes_wrap_rather_than_pile_up_at_the_edge(self) -> None:
        """A mote has no flock to rejoin, so wrapping is what keeps the
        density even with no steering at all."""
        swarm, _ = make_swarm(decorative=1)
        mote = swarm.motes[0]
        mote.position = Vector2(ARENA.right - 1, 300)
        mote.velocity = Vector2(400.0, 0.0)

        swarm.update_motes(0.1)

        assert mote.position.x == pytest.approx(ARENA.left, abs=1.0)

    def test_motes_are_not_entities(self) -> None:
        """The whole reason the decorative layer is affordable: no
        components to resolve, no index entry, no flocking slot."""
        _, entity_manager = make_swarm(cap=1, decorative=500)

        assert sum(1 for _ in entity_manager.get_entities_with(Transform)) <= 1
