"""`Swarm`'s batch API: ids, kinds, spawning, killing, seeking and queries."""

from __future__ import annotations

import math

import pytest

from pyguara.ai.swarm import Swarm, SwarmKind
from pyguara.common.types import Vector2


def _swarm(count: int = 0, **kind: float) -> tuple[Swarm, int, list[int]]:
    swarm = Swarm(cell_size=32.0)
    index = swarm.add_kind(SwarmKind(**kind))
    ids = swarm.spawn(index, [Vector2(10.0 * i, 0.0) for i in range(count)])
    return swarm, index, ids


class TestKinds:
    def test_defaults_match_flocking_agent(self) -> None:
        from pyguara.ai.flocking_system import FlockingAgent

        agent, kind = FlockingAgent(), SwarmKind()
        for name in SwarmKind.__dataclass_fields__:
            assert getattr(kind, name) == getattr(agent, name), name

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("mass", 0.0),
            ("mass", -1.0),
            ("max_speed", -1.0),
            ("neighbor_radius", -5.0),
            ("separation_radius", -1.0),
            ("max_force", math.inf),
            ("cohesion_weight", math.nan),
        ],
    )
    def test_unusable_tuning_is_refused(self, field: str, value: float) -> None:
        with pytest.raises(ValueError, match=field):
            SwarmKind(**{field: value})

    def test_a_radius_spanning_too_many_cells_is_refused(self) -> None:
        swarm = Swarm(cell_size=0.001)
        with pytest.raises(ValueError, match="cell_size"):
            swarm.add_kind(SwarmKind(neighbor_radius=80.0))
        assert swarm.kinds == ()

    def test_an_unknown_kind_is_refused(self) -> None:
        swarm, _, _ = _swarm()
        with pytest.raises(ValueError, match="kind 3"):
            swarm.spawn(3, [Vector2(0, 0)])

    @pytest.mark.parametrize("cell_size", [0.0, -1.0, math.nan, math.inf])
    def test_a_bad_cell_size_is_refused(self, cell_size: float) -> None:
        with pytest.raises(ValueError, match="cell_size"):
            Swarm(cell_size=cell_size)


class TestIds:
    def test_spawn_returns_one_id_per_position_in_order(self) -> None:
        swarm, _, ids = _swarm(5)
        assert len(set(ids)) == 5
        assert swarm.positions(ids) == [Vector2(10.0 * i, 0.0) for i in range(5)]
        assert swarm.count == 5
        assert swarm.ids() == ids

    def test_a_killed_agent_is_gone_and_its_id_never_returns(self) -> None:
        swarm, kind, ids = _swarm(3)
        swarm.kill([ids[1]])
        assert not swarm.is_alive(ids[1])
        assert swarm.count == 2
        (reused,) = swarm.spawn(kind, [Vector2(5, 5)])
        assert reused != ids[1]
        assert not swarm.is_alive(ids[1])
        with pytest.raises(KeyError):
            swarm.positions([ids[1]])

    def test_a_kill_with_a_dead_id_removes_nothing(self) -> None:
        swarm, _, ids = _swarm(3)
        swarm.kill([ids[0]])
        with pytest.raises(KeyError):
            swarm.kill([ids[1], ids[0]])
        assert swarm.is_alive(ids[1])

    def test_a_kill_naming_an_agent_twice_removes_nothing(self) -> None:
        swarm, _, ids = _swarm(3)
        with pytest.raises(ValueError, match="twice"):
            swarm.kill([ids[2], ids[2]])
        assert swarm.count == 3

    def test_an_id_from_nowhere_is_not_alive(self) -> None:
        swarm, _, _ = _swarm(2)
        assert not swarm.is_alive(12345678901)

    def test_kinds_of_names_each_agents_kind(self) -> None:
        swarm, first, ids = _swarm(2)
        second = swarm.add_kind(SwarmKind(max_speed=50.0))
        more = swarm.spawn(second, [Vector2(0, 0)])
        assert swarm.kinds_of(ids + more) == [first, first, second]


class TestSpawning:
    def test_agents_start_at_rest_unless_given_a_velocity(self) -> None:
        swarm, kind, ids = _swarm(1)
        moving = swarm.spawn(kind, [Vector2(0, 0)], [Vector2(3, 4)])
        assert swarm.velocities(ids + moving) == [Vector2(0, 0), Vector2(3, 4)]

    @pytest.mark.parametrize(
        ("positions", "velocities", "match"),
        [
            ([Vector2(math.nan, 0)], None, "NaN"),
            ([Vector2(0, 0)], [Vector2(math.inf, 0)], "not finite"),
            ([Vector2(0, 0)], [], "velocities"),
        ],
    )
    def test_bad_input_spawns_nothing(
        self,
        positions: list[Vector2],
        velocities: list[Vector2] | None,
        match: str,
    ) -> None:
        swarm, kind, _ = _swarm()
        with pytest.raises((ValueError, OverflowError), match=match):
            swarm.spawn(kind, positions, velocities)
        assert swarm.count == 0

    def test_a_tuple_is_a_position(self) -> None:
        swarm, kind, _ = _swarm()
        (agent,) = swarm.spawn(kind, [(1.5, 2.5)])  # type: ignore[list-item]
        assert swarm.positions([agent]) == [Vector2(1.5, 2.5)]


class TestSeeking:
    def test_a_kind_target_draws_its_agents_and_not_others(self) -> None:
        swarm = Swarm(cell_size=32.0)
        drawn = swarm.add_kind(SwarmKind())
        idle = swarm.add_kind(SwarmKind())
        a = swarm.spawn(drawn, [Vector2(0, 0)])
        b = swarm.spawn(idle, [Vector2(500, 0)])
        swarm.set_kind_seek(drawn, Vector2(0, 300))
        swarm.update(1 / 60)
        assert swarm.velocities(a)[0].y > 0
        assert swarm.velocities(b) == [Vector2(0, 0)]

    def test_clearing_a_kind_target_stops_the_pull(self) -> None:
        swarm, kind, ids = _swarm(1)
        swarm.set_kind_seek(kind, Vector2(0, 300))
        swarm.set_kind_seek(kind, None)
        swarm.update(1 / 60)
        assert swarm.velocities(ids) == [Vector2(0, 0)]

    def test_each_agent_can_seek_its_own_target(self) -> None:
        swarm, _, ids = _swarm(2)
        swarm.set_seek(ids, [Vector2(0, -500), Vector2(10, 500)])
        swarm.update(1 / 60)
        up, down = swarm.velocities(ids)
        assert up.y < 0 < down.y

    def test_mismatched_targets_are_refused(self) -> None:
        swarm, _, ids = _swarm(2)
        with pytest.raises(ValueError, match="targets"):
            swarm.set_seek(ids, [Vector2(0, 0)])


class TestQueries:
    def test_query_radius_finds_exactly_the_agents_in_range_sorted(self) -> None:
        swarm = Swarm(cell_size=16.0)
        kind = swarm.add_kind(SwarmKind())
        points = [Vector2((i * 37) % 200, (i * 53) % 200) for i in range(300)]
        ids = swarm.spawn(kind, points)
        swarm.kill(ids[::5])
        centre, radius = Vector2(90, 110), 45.0
        expected = sorted(
            agent
            for agent, point in zip(ids, points, strict=True)
            if swarm.is_alive(agent)
            and (point.x - centre.x) ** 2 + (point.y - centre.y) ** 2 <= radius**2
        )
        assert expected
        assert swarm.query_radius(centre, radius) == expected

    def test_query_radius_sees_where_agents_moved_to(self) -> None:
        swarm, kind, _ = _swarm()
        (agent,) = swarm.spawn(kind, [Vector2(0, 0)], [Vector2(600, 0)])
        assert swarm.query_radius(Vector2(0, 0), 1.0) == [agent]
        swarm.update(0.5)
        assert swarm.query_radius(Vector2(0, 0), 1.0) == []
        assert swarm.query_radius(swarm.positions([agent])[0], 1.0) == [agent]

    def test_query_outside_is_the_complement(self) -> None:
        swarm, _, ids = _swarm(10)
        inside = swarm.query_radius(Vector2(0, 0), 35.0)
        outside = swarm.query_outside(Vector2(0, 0), 35.0)
        assert sorted(inside + outside) == sorted(ids)
        assert not set(inside) & set(outside)

    def test_a_negative_radius_is_refused(self) -> None:
        swarm, _, _ = _swarm(1)
        with pytest.raises(ValueError, match="radius"):
            swarm.query_radius(Vector2(0, 0), -1.0)


class TestUpdate:
    def test_an_empty_swarm_ticks(self) -> None:
        swarm, _, _ = _swarm()
        swarm.update(1 / 60)
        assert swarm.count == 0

    def test_a_lone_agent_coasts(self) -> None:
        swarm, kind, _ = _swarm()
        (agent,) = swarm.spawn(kind, [Vector2(0, 0)], [Vector2(60, 0)])
        swarm.update(0.5)
        assert swarm.positions([agent]) == [Vector2(30, 0)]

    def test_speed_is_capped(self) -> None:
        swarm, kind, _ = _swarm(max_speed=50.0)
        (agent,) = swarm.spawn(kind, [Vector2(0, 0)])
        swarm.set_kind_seek(kind, Vector2(10_000, 0))
        for _ in range(120):
            swarm.update(1 / 60)
        assert swarm.velocities([agent])[0].length <= 50.0 + 1e-9

    @pytest.mark.parametrize("dt", [-0.1, math.nan, math.inf])
    def test_a_bad_step_is_refused(self, dt: float) -> None:
        swarm, _, _ = _swarm(1)
        with pytest.raises(ValueError, match="dt"):
            swarm.update(dt)

    def test_a_dead_agent_is_nobodys_flockmate(self) -> None:
        swarm, _, ids = _swarm(2)
        swarm.kill([ids[1]])
        swarm.update(1 / 60)
        assert swarm.neighbour_counts() == [0]
