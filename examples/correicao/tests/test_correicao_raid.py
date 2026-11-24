"""The raid's rules: how ants arrive, bite, die and are replaced.

Driven through the systems directly on a bare `Swarm`, with a stand-in
texture, so no window or GPU is needed.
"""

from __future__ import annotations

import math

from examples.correicao.components import PlayerState
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
    RaidSystem,
    make_raid,
)
from pyguara.ai.swarm import Swarm
from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
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
) -> tuple[Swarm, PlayerState, HordeSpawner, list[int]]:
    swarm = Swarm(cell_size=26.0)
    state = PlayerState(position=CENTRE)
    kinds = make_raid(swarm, [_Texture("ant_0"), _Texture("ant_1")])
    spawner = HordeSpawner(
        swarm, state, kinds, RandomStream(seed), target=target, view_radius=VIEW_RADIUS
    )
    return swarm, state, spawner, kinds


def _ants(swarm: Swarm) -> list[Vector2]:
    return swarm.positions(swarm.ids())


def _place(swarm: Swarm, kinds: list[int], *offsets: Vector2) -> list[int]:
    """Put one ant at the calango plus each offset."""
    return swarm.spawn(kinds[0], [CENTRE + offset for offset in offsets])


def test_the_raid_fills_up_a_tick_at_a_time_out_of_view() -> None:
    swarm, _, spawner, _ = _raid(target=600)

    spawner.update(DT)
    assert spawner.alive == SPAWN_PER_TICK
    for _ in range(5):
        spawner.update(DT)

    assert spawner.alive == 600 == len(_ants(swarm))
    assert all((p - CENTRE).length > VIEW_RADIUS for p in _ants(swarm))


def test_the_raid_uses_every_kind() -> None:
    swarm, _, spawner, kinds = _raid(target=600)
    for _ in range(3):
        spawner.update(DT)
    assert set(swarm.kinds_of(swarm.ids())) == set(kinds)


def test_a_pulse_kills_the_ants_inside_it_and_they_are_replaced() -> None:
    swarm, state, spawner, kinds = _raid(target=3)
    _place(
        swarm,
        kinds,
        Vector2(PULSE_RADIUS - 5, 0),
        Vector2(0, PULSE_RADIUS - 5),
        Vector2(PULSE_RADIUS + 60, 0),
    )
    combat = CombatSystem(swarm, state, view_radius=VIEW_RADIUS)
    state.pulse_cooldown = 0.0

    combat.resolve()

    assert state.kills == 2
    assert spawner.alive == 1 == len(_ants(swarm))
    spawner.update(DT)
    assert spawner.alive == 3


def test_an_ant_on_the_calango_bites_between_pulses() -> None:
    swarm, state, _, kinds = _raid(target=1)
    _place(swarm, kinds, Vector2(4, 0))
    combat = CombatSystem(swarm, state, view_radius=VIEW_RADIUS)
    state.pulse_cooldown = 10.0

    combat.update(COMBAT_PERIOD)

    assert state.bites == 1
    assert state.health == 100.0 - BITE_DAMAGE


def test_a_straggler_far_behind_is_removed_for_a_fresh_one() -> None:
    swarm, state, spawner, kinds = _raid(target=1)
    _place(swarm, kinds, Vector2(VIEW_RADIUS * 3, 0))
    combat = CombatSystem(swarm, state, view_radius=VIEW_RADIUS)
    state.pulse_cooldown = 10.0

    combat.resolve()

    assert spawner.alive == 0
    assert state.kills == 0


def test_the_raid_heads_for_where_the_calango_is_now() -> None:
    swarm, state, _, kinds = _raid(target=1)
    (ant,) = _place(swarm, kinds, Vector2(-300, 0))
    raid = RaidSystem(swarm, state, kinds, view_radius=VIEW_RADIUS)
    state.position = CENTRE + Vector2(0, -400)

    raid.update(DT)

    velocity = swarm.velocities([ant])[0]
    to_calango = state.position - swarm.positions([ant])[0]
    assert velocity.dot(to_calango) > 0.9 * velocity.length * to_calango.length


def test_the_raid_closes_in_on_the_calango() -> None:
    swarm, state, spawner, kinds = _raid(target=200)
    spawner.update(DT)
    raid = RaidSystem(swarm, state, kinds, view_radius=VIEW_RADIUS)

    def mean_distance() -> float:
        ants = _ants(swarm)
        return sum((p - state.position).length for p in ants) / len(ants)

    before = mean_distance()
    for _ in range(120):
        raid.update(DT)

    assert mean_distance() < before - 100.0


def test_ants_far_off_screen_steer_less_often() -> None:
    swarm, state, _, kinds = _raid(target=2)
    near, far = _place(swarm, kinds, Vector2(-300, 0), Vector2(-3000, 0))
    raid = RaidSystem(swarm, state, kinds, view_radius=VIEW_RADIUS)
    turned = {near: 0, far: 0}
    for _ in range(8):
        before = dict(zip((near, far), swarm.velocities([near, far]), strict=True))
        raid.update(DT)
        after = dict(zip((near, far), swarm.velocities([near, far]), strict=True))
        for ant in turned:
            turned[ant] += after[ant] != before[ant]
    assert turned == {near: 8, far: 2}


def test_the_same_seed_raids_the_same_way() -> None:
    def run() -> list[tuple[float, float]]:
        swarm, state, spawner, kinds = _raid(target=300, seed=11)
        raid = RaidSystem(swarm, state, kinds, view_radius=VIEW_RADIUS)
        combat = CombatSystem(swarm, state, view_radius=VIEW_RADIUS)
        for _ in range(90):
            spawner.update(DT)
            raid.update(DT)
            combat.update(DT)
        return sorted((p.x, p.y) for p in _ants(swarm))

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
    swarm, state, _, kinds = _raid(target=1)
    _place(swarm, kinds, Vector2(10, 0))
    combat = CombatSystem(swarm, state, view_radius=VIEW_RADIUS)

    combat.update(COMBAT_PERIOD)

    assert state.kills == 0
