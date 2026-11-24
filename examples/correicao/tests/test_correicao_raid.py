"""The raid's rules: how ants arrive, bite, die and are replaced.

Driven through the systems directly on a bare `EntityManager`, with a
stand-in texture, so no window or GPU is needed.
"""

from __future__ import annotations

import math

from examples.correicao.components import Ant, PlayerState
from examples.correicao.systems import (
    BITE_DAMAGE,
    COMBAT_PERIOD,
    PLAYER_SPEED,
    PULSE_RADIUS,
    SPAWN_PER_TICK,
    WORLD_SIZE,
    CombatSystem,
    HordeSpawner,
    PlayerSystem,
)
from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.resources.types import Texture

VIEW_RADIUS = 400.0
DT = 1 / 60
CENTRE = Vector2(WORLD_SIZE / 2, WORLD_SIZE / 2)


class _Texture(Texture):
    @property
    def width(self) -> int:
        return 16

    @property
    def height(self) -> int:
        return 12

    @property
    def native_handle(self) -> object:
        return None


def _raid(
    target: int = 300, seed: int = 7
) -> tuple[EntityManager, PlayerState, HordeSpawner]:
    manager = EntityManager()
    state = PlayerState(position=CENTRE)
    spawner = HordeSpawner(
        manager,
        state,
        [_Texture("ant_0"), _Texture("ant_1")],
        RandomStream(seed),
        target=target,
        view_radius=VIEW_RADIUS,
    )
    return manager, state, spawner


def _ants(manager: EntityManager) -> list[Vector2]:
    return [
        entity.get_component(Transform).position
        for entity in manager.get_entities_with(Ant, Transform)
    ]


def _place(manager: EntityManager, spawner: HordeSpawner, *offsets: Vector2) -> None:
    """Spawn one ant per offset, then move each to the calango plus its offset."""
    for _ in offsets:
        spawner.spawn()
    ants = list(manager.get_entities_with(Ant, Transform))
    for entity, offset in zip(ants[-len(offsets) :], offsets, strict=True):
        entity.get_component(Transform).position = CENTRE + offset


def test_the_raid_fills_up_a_tick_at_a_time_out_of_view() -> None:
    manager, _, spawner = _raid(target=600)

    spawner.update(DT)
    assert spawner.alive == SPAWN_PER_TICK
    for _ in range(5):
        spawner.update(DT)

    assert spawner.alive == 600 == len(_ants(manager))
    assert all((p - CENTRE).length > VIEW_RADIUS for p in _ants(manager))


def test_a_pulse_kills_the_ants_inside_it_and_they_are_replaced() -> None:
    manager, state, spawner = _raid(target=3)
    _place(
        manager,
        spawner,
        Vector2(PULSE_RADIUS - 5, 0),
        Vector2(0, PULSE_RADIUS - 5),
        Vector2(PULSE_RADIUS + 60, 0),
    )
    combat = CombatSystem(manager, state, spawner, view_radius=VIEW_RADIUS)
    state.pulse_cooldown = 0.0

    combat.resolve()

    assert state.kills == 2
    assert spawner.alive == 1 == len(_ants(manager))
    spawner.update(DT)
    assert spawner.alive == 3


def test_an_ant_on_the_calango_bites_between_pulses() -> None:
    manager, state, spawner = _raid(target=1)
    _place(manager, spawner, Vector2(4, 0))
    combat = CombatSystem(manager, state, spawner, view_radius=VIEW_RADIUS)
    state.pulse_cooldown = 10.0

    combat.update(COMBAT_PERIOD)

    assert state.bites == 1
    assert state.health == 100.0 - BITE_DAMAGE


def test_a_straggler_far_behind_is_removed_for_a_fresh_one() -> None:
    manager, state, spawner = _raid(target=1)
    _place(manager, spawner, Vector2(VIEW_RADIUS * 3, 0))
    combat = CombatSystem(manager, state, spawner, view_radius=VIEW_RADIUS)
    state.pulse_cooldown = 10.0

    combat.resolve()

    assert spawner.alive == 0
    assert state.kills == 0


def test_the_combat_pass_points_every_ant_at_where_the_calango_is_now() -> None:
    manager, state, spawner = _raid(target=20)
    spawner.update(DT)
    state.position = CENTRE + Vector2(100, -50)
    state.pulse_cooldown = 10.0

    CombatSystem(manager, state, spawner, view_radius=VIEW_RADIUS).resolve()

    targets = {
        entity.get_component(FlockingAgent).seek_target
        for entity in manager.get_entities_with(Ant, FlockingAgent)
    }
    assert targets == {state.position}


def test_the_flock_closes_in_on_the_calango() -> None:
    manager, state, spawner = _raid(target=200)
    spawner.update(DT)
    flock = FlockingSystem(manager, cell_size=26.0)

    def mean_distance() -> float:
        ants = _ants(manager)
        return sum((p - state.position).length for p in ants) / len(ants)

    before = mean_distance()
    for _ in range(120):
        flock.update(DT)

    assert mean_distance() < before - 100.0


def test_the_same_seed_raids_the_same_way() -> None:
    def run() -> list[tuple[float, float]]:
        manager, state, spawner = _raid(target=300, seed=11)
        flock = FlockingSystem(manager, cell_size=26.0)
        combat = CombatSystem(manager, state, spawner, view_radius=VIEW_RADIUS)
        for _ in range(90):
            spawner.update(DT)
            flock.update(DT)
            combat.update(DT)
        return sorted((p.x, p.y) for p in _ants(manager))

    assert run() == run()


def test_the_autopilot_walks_until_a_key_is_pressed() -> None:
    state = PlayerState(position=CENTRE)
    player = PlayerSystem(state)
    for _ in range(60):
        player.update(DT)
    assert player.autopilot
    assert (state.position - CENTRE).length > 0

    player.move_direction = Vector2(1, 0)
    start = state.position
    player.update(DT)

    assert not player.autopilot
    assert math.isclose(state.position.x - start.x, PLAYER_SPEED * DT)


def test_the_calango_stays_inside_the_world() -> None:
    state = PlayerState(position=Vector2(5, 5))
    player = PlayerSystem(state, autopilot=False)
    player.move_direction = Vector2(-1, -1)

    for _ in range(30):
        player.update(DT)

    assert state.position == Vector2(0, 0)


def test_an_overrun_calango_gets_back_up_at_full_health() -> None:
    state = PlayerState(position=CENTRE, health=0.0)

    PlayerSystem(state, autopilot=False).update(DT)

    assert state.overruns == 1
    assert state.health == 100.0


def test_the_first_pulse_waits_a_period() -> None:
    manager, state, spawner = _raid(target=1)
    _place(manager, spawner, Vector2(10, 0))
    combat = CombatSystem(manager, state, spawner, view_radius=VIEW_RADIUS)

    combat.update(COMBAT_PERIOD)

    assert state.kills == 0
