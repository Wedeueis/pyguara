"""Regression tests for Vinagre: Matilha's level geometry.

An earlier build shipped all three stages as open fields with no walls at
all. Headless playtesting caught the actual failure mode directly: with
nowhere it *couldn't* go, a fleeing jaguar would dodge around flanking dogs
and wander back past its own spawn instead of ever reaching the corner
zone. The corridor-with-walls redesign fixes that by construction, but a
level is hand-authored geometry -- these tests are the regression guard
against a future tuning pass accidentally sealing off the very cells the
level depends on being reachable.
"""

from __future__ import annotations

import math

import pytest

from games.vinagre_matilha.level_builder import (
    CELL_SIZE,
    STAGE_1,
    STAGE_2,
    STAGE_3,
    STAGES,
    StageConfig,
    build_graph,
)
from pyguara.ai.pathfinding.flow_field import dijkstra_map
from pyguara.common.grid import world_to_cell
from pyguara.common.types import Vector2


def _reachable(config: StageConfig, from_pos: Vector2, to_pos: Vector2) -> bool:
    graph, _ = build_graph(config)
    start = world_to_cell(from_pos, CELL_SIZE)
    goal = world_to_cell(to_pos, CELL_SIZE)
    costs = dijkstra_map(graph, goals=[goal])
    return costs.get(start, math.inf) != math.inf


@pytest.mark.parametrize("stage", STAGES, ids=[s.name for s in STAGES])
class TestStageConnectivity:
    """Every stage's spawn points must be mutually reachable as authored.

    Corner-zone reachability is checked separately below: Stage 3's is
    *intentionally* gated by an unopened log (see `TestStage3LogGate`), so
    asserting it here for all three stages would be wrong for that one.
    """

    def test_dog_spawn_can_reach_jaguar_spawn(self, stage: StageConfig) -> None:
        assert _reachable(stage, stage.dog_spawn, stage.jaguar_spawn)


@pytest.mark.parametrize(
    "stage", [STAGE_1, STAGE_2], ids=["Sandbar Drill", "Braided Channel"]
)
class TestGatelessStageConnectivity:
    """Stage 1/2 have no puzzle gate: the corner zone must be reachable
    from both spawns as soon as the level is built."""

    def test_dog_spawn_can_reach_corner_zone(self, stage: StageConfig) -> None:
        assert _reachable(stage, stage.dog_spawn, stage.corner_zone.center_vec)

    def test_jaguar_spawn_can_reach_corner_zone(self, stage: StageConfig) -> None:
        assert _reachable(stage, stage.jaguar_spawn, stage.corner_zone.center_vec)


class TestStage1Corridor:
    """Sandbar Drill: a simple walled corridor with no puzzle gate."""

    def test_spawns_and_corner_sit_inside_the_corridor(self) -> None:
        graph, _ = build_graph(STAGE_1)
        for point in (
            STAGE_1.dog_spawn,
            STAGE_1.jaguar_spawn,
            STAGE_1.corner_zone.center_vec,
        ):
            cell = world_to_cell(point, CELL_SIZE)
            assert graph.is_passable(cell)


class TestStage3LogGate:
    """Jaguar's Bend: the log must be a genuine gate, not a bypassable prop."""

    def test_corner_zone_is_unreachable_before_the_plate_opens(self) -> None:
        assert not _reachable(
            STAGE_3, STAGE_3.dog_spawn, STAGE_3.corner_zone.center_vec
        )

    def test_corner_zone_is_reachable_once_the_logs_cells_are_cleared(self) -> None:
        graph, log_cells = build_graph(STAGE_3)
        assert log_cells, (
            "Stage 3 must declare a log_rect for this test to mean anything"
        )
        graph.walls.difference_update(log_cells)  # PressurePlateSystem's own fix-up

        start = world_to_cell(STAGE_3.dog_spawn, CELL_SIZE)
        goal = world_to_cell(STAGE_3.corner_zone.center_vec, CELL_SIZE)
        costs = dijkstra_map(graph, goals=[goal])
        assert costs.get(start, math.inf) != math.inf

    def test_plate_alcove_is_reachable_without_crossing_the_log(self) -> None:
        assert STAGE_3.plate_rect is not None
        assert _reachable(STAGE_3, STAGE_3.dog_spawn, STAGE_3.plate_rect.center_vec)
