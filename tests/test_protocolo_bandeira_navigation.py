"""A chaser that goes around the termite mounds instead of through them.

`render.py` called the mounds "cover to run past" long before they were
anything of the kind: they were drawn, and a chaser walked straight over
one. These pin the two halves of the fix -- that a mound is a wall on the
navigation grid, and that A* is only paid for when one is in the way.
"""

from __future__ import annotations

import pytest

from games.protocolo_bandeira.ai_behaviors import chase_player
from games.protocolo_bandeira.components import AIContext
from games.protocolo_bandeira.navigation import (
    CELL_SIZE,
    CLEARANCE,
    MAX_PATH_AGE,
    REPLAN_DISTANCE,
    ArenaNavGrid,
    ChaserNavigator,
)
from pyguara.ai.behavior_tree import NodeStatus
from pyguara.common.types import Rect, Vector2

ARENA = Rect(26, 104, 908, 544)
MOUND = (Vector2(480, 376), 28.0)
"""One mound, in the middle of the arena, big enough to have to go round."""

WEST = Vector2(300, 376)
EAST = Vector2(660, 376)
"""Either side of it, on the line straight through."""


@pytest.fixture
def grid() -> ArenaNavGrid:
    """An arena with a single mound at its centre."""
    return ArenaNavGrid(ARENA, [MOUND])


@pytest.fixture
def navigator(grid: ArenaNavGrid) -> ChaserNavigator:
    return ChaserNavigator(grid)


class TestTheGrid:
    """What a mound does to the map."""

    def test_the_grid_covers_the_arena(self, grid: ArenaNavGrid) -> None:
        assert grid.graph.width == pytest.approx(ARENA.width / CELL_SIZE, abs=1)
        assert grid.graph.height == pytest.approx(ARENA.height / CELL_SIZE, abs=1)

    def test_a_mound_blocks_its_own_cells(self, grid: ArenaNavGrid) -> None:
        assert grid.graph.walls
        assert not grid.graph.is_passable(grid.to_cell(MOUND[0]))

    def test_the_block_is_grown_by_a_chasers_width(self, grid: ArenaNavGrid) -> None:
        """Without clearance a route hugs the rock and the body clips it."""
        just_outside = MOUND[0] + Vector2(MOUND[1] + CLEARANCE * 0.5, 0.0)

        assert not grid.graph.is_passable(grid.to_cell(just_outside))

    def test_open_ground_stays_open(self, grid: ArenaNavGrid) -> None:
        assert grid.graph.is_passable(grid.to_cell(Vector2(120, 180)))

    def test_an_arena_with_no_mounds_has_no_walls(self) -> None:
        assert not ArenaNavGrid(ARENA, []).graph.walls


class TestLineOfSight:
    """The cheap test the whole module is built around."""

    def test_the_mound_breaks_the_line(self, grid: ArenaNavGrid) -> None:
        assert not grid.is_clear(WEST, EAST)

    def test_a_clear_run_is_clear(self, grid: ArenaNavGrid) -> None:
        assert grid.is_clear(Vector2(120, 180), Vector2(600, 180))

    def test_a_line_that_only_grazes_the_arena_edge_is_clear(
        self, grid: ArenaNavGrid
    ) -> None:
        assert grid.is_clear(Vector2(40, 120), Vector2(900, 130))


class TestRouting:
    """What A* gives back."""

    def test_a_blocked_run_gets_a_route(self, grid: ArenaNavGrid) -> None:
        assert grid.route(WEST, EAST)

    def test_the_route_never_crosses_the_mound(self, grid: ArenaNavGrid) -> None:
        for point in grid.route(WEST, EAST):
            assert point.distance_to(MOUND[0]) > MOUND[1], point

    def test_the_route_does_not_start_where_the_chaser_stands(
        self, grid: ArenaNavGrid
    ) -> None:
        """Steering at the cell you are in is steering nowhere."""
        route = grid.route(WEST, EAST)

        assert route[0].distance_to(WEST) > 1.0

    def test_a_chaser_standing_inside_a_mound_still_gets_a_route(
        self, grid: ArenaNavGrid
    ) -> None:
        """Enemies spawn where the wave manager puts them."""
        assert grid.route(MOUND[0], Vector2(120, 180))

    def test_a_goal_inside_a_mound_still_gets_a_route(self, grid: ArenaNavGrid) -> None:
        """The player is not blocked, so they can stand on one."""
        assert grid.route(Vector2(120, 180), MOUND[0])

    def test_a_route_to_where_you_already_are_is_empty(
        self, grid: ArenaNavGrid
    ) -> None:
        assert grid.route(WEST, WEST) == []


class TestTheNavigator:
    """When a path is paid for, and when it is not."""

    def test_a_clear_view_costs_no_search(self, navigator: ChaserNavigator) -> None:
        """The common case. A wave of chasers on open ground must not each
        run A* every frame."""
        for _ in range(60):
            navigator.direction("e1", Vector2(120, 180), Vector2(600, 180), 1 / 60)

        assert navigator.plans == 0

    def test_a_clear_view_steers_straight_at_the_player(
        self, navigator: ChaserNavigator
    ) -> None:
        direction = navigator.direction(
            "e1", Vector2(120, 180), Vector2(600, 180), 1 / 60
        )

        assert direction.x == pytest.approx(1.0)
        assert direction.y == pytest.approx(0.0)

    def test_a_blocked_view_searches_once_and_then_follows(
        self, navigator: ChaserNavigator
    ) -> None:
        for _ in range(30):
            navigator.direction("e1", WEST, EAST, 1 / 60)

        assert navigator.plans == 1, "the path is cached, not re-planned per frame"

    def test_a_blocked_chaser_does_not_steer_into_the_mound(
        self, navigator: ChaserNavigator
    ) -> None:
        straight = (EAST - WEST).normalize()

        routed = navigator.direction("e1", WEST, EAST, 1 / 60)

        assert routed.distance_to(straight) > 0.2, "it should be going around"

    def test_the_path_expires(self, navigator: ChaserNavigator) -> None:
        navigator.direction("e1", WEST, EAST, 1 / 60)

        navigator.direction("e1", WEST, EAST, MAX_PATH_AGE + 0.1)

        assert navigator.plans == 2

    def test_a_player_who_runs_off_invalidates_the_path(
        self, navigator: ChaserNavigator
    ) -> None:
        navigator.direction("e1", WEST, EAST, 1 / 60)

        # Further along the same blocked line: still behind the mound, so
        # the straight-line shortcut cannot be what re-plans this.
        moved = EAST + Vector2(REPLAN_DISTANCE * 2, 0.0)
        navigator.direction("e1", WEST, moved, 1 / 60)

        assert navigator.plans == 2

    def test_a_player_who_shuffles_does_not(self, navigator: ChaserNavigator) -> None:
        """Less than this and a chaser re-plans every frame the player
        strafes."""
        navigator.direction("e1", WEST, EAST, 1 / 60)

        navigator.direction("e1", WEST, EAST + Vector2(0.0, 8.0), 1 / 60)

        assert navigator.plans == 1

    def test_reaching_the_player_asks_for_no_direction(
        self, navigator: ChaserNavigator
    ) -> None:
        here = Vector2(200, 200)

        assert navigator.direction("e1", here, here, 1 / 60) == Vector2.zero()

    def test_each_chaser_keeps_its_own_path(self, navigator: ChaserNavigator) -> None:
        navigator.direction("e1", WEST, EAST, 1 / 60)
        navigator.direction("e2", EAST, WEST, 1 / 60)

        assert navigator.waypoints("e1") != navigator.waypoints("e2")

    def test_walking_into_the_open_drops_the_path(
        self, navigator: ChaserNavigator
    ) -> None:
        navigator.direction("e1", WEST, EAST, 1 / 60)
        assert navigator.waypoints("e1")

        navigator.direction("e1", Vector2(120, 180), Vector2(600, 180), 1 / 60)

        assert not navigator.waypoints("e1")


class TestThePoolDoesNotLeakPaths:
    """Enemy ids are handed out again; a route must not outlive its owner."""

    def test_a_dead_chasers_path_is_dropped(self, navigator: ChaserNavigator) -> None:
        navigator.direction("e1", WEST, EAST, 1 / 60)

        navigator.retain({"e2"})

        assert not navigator.waypoints("e1")

    def test_a_live_chasers_path_survives(self, navigator: ChaserNavigator) -> None:
        navigator.direction("e1", WEST, EAST, 1 / 60)

        navigator.retain({"e1", "e2"})

        assert navigator.waypoints("e1")

    def test_forgetting_one_that_never_had_a_path_is_harmless(
        self, navigator: ChaserNavigator
    ) -> None:
        navigator.forget("never_existed")


class TestTheBehaviourTreeAction:
    """`chase_player` is where the two halves meet."""

    def _context(self, navigator: ChaserNavigator | None) -> AIContext:
        return AIContext(
            entity_id="e1",
            position=WEST,
            player_position=EAST,
            distance_to_player=WEST.distance_to(EAST),
            dt=1 / 60,
            navigator=navigator,
        )

    def test_without_a_navigator_it_is_the_straight_line_it_always_was(
        self,
    ) -> None:
        context = self._context(None)

        assert chase_player(context) is NodeStatus.SUCCESS
        assert context.move_direction == (EAST - WEST).normalize()

    def test_with_one_it_goes_around(self, navigator: ChaserNavigator) -> None:
        context = self._context(navigator)

        assert chase_player(context) is NodeStatus.SUCCESS
        assert context.move_direction is not None
        assert context.move_direction != (EAST - WEST).normalize()

    def test_no_player_is_still_a_failure(self, navigator: ChaserNavigator) -> None:
        context = self._context(navigator)
        context.player_position = None

        assert chase_player(context) is NodeStatus.FAILURE
        assert context.move_direction is None


class TestItActuallyGetsThere:
    """Walking the steering out, step by step -- the claim in one test."""

    def _walk(
        self, navigator: ChaserNavigator, start: Vector2, goal: Vector2
    ) -> list[Vector2]:
        """Steer a chaser from `start` to `goal` at a plausible speed."""
        dt, speed = 1 / 60, 140.0
        position = start
        trail = [position]
        for _ in range(600):  # ten seconds; the run is about two
            if position.distance_to(goal) < 12.0:
                break
            position = position + navigator.direction("e1", position, goal, dt) * (
                speed * dt
            )
            trail.append(position)
        return trail

    def test_it_reaches_the_player(self, navigator: ChaserNavigator) -> None:
        trail = self._walk(navigator, WEST, EAST)

        assert trail[-1].distance_to(EAST) < 12.0

    def test_it_never_walks_through_the_mound(self, navigator: ChaserNavigator) -> None:
        """The whole point. Before this module the trail was a straight
        line across the middle of the rock."""
        for point in self._walk(navigator, WEST, EAST):
            assert point.distance_to(MOUND[0]) > MOUND[1], point

    def test_the_detour_is_not_a_long_way_round(
        self, navigator: ChaserNavigator
    ) -> None:
        """A chaser that loops the arena to avoid a pebble reads as broken."""
        trail = self._walk(navigator, WEST, EAST)
        walked = sum(a.distance_to(b) for a, b in zip(trail, trail[1:], strict=False))

        assert walked < WEST.distance_to(EAST) * 1.5

    def test_the_whole_run_costs_a_handful_of_searches(
        self, navigator: ChaserNavigator
    ) -> None:
        self._walk(navigator, WEST, EAST)

        assert navigator.plans <= 3, "not one per frame"
