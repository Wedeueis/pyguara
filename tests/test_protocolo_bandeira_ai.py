"""Tests for Protocolo Bandeira's enemy AI ranges.

The condition nodes hardcoded a detection radius and an attack radius,
and ignored the per-type ranges the enemy pool was configuring -- so a
shooter's 400 and a bomber's 350 both behaved as 300, and no amount of
tuning the pool could change what an enemy could see.
"""

from __future__ import annotations

import pytest

from games.protocolo_bandeira.ai_behaviors import (
    is_in_attack_range,
    is_player_detected,
)
from games.protocolo_bandeira.components import AIContext
from games.protocolo_bandeira.pooling import EnemyPool
from pyguara.common.types import Rect, Vector2
from pyguara.ecs.manager import EntityManager

ARENA = Rect(26, 104, 908, 544)


def make_context(distance: float, **kwargs) -> AIContext:
    """Build a context with the player a given distance away."""
    return AIContext(
        entity_id="e1",
        position=Vector2.zero(),
        player_position=Vector2(distance, 0.0),
        distance_to_player=distance,
        dt=1 / 60,
        **kwargs,
    )


class TestDetectionUsesTheEnemysOwnRanges:
    """The condition nodes used to hardcode 300 and 150."""

    def test_a_long_sighted_enemy_sees_further_than_the_old_constant(self) -> None:
        context = make_context(900.0, detection_range=1400.0)

        assert is_player_detected(context)

    def test_a_short_sighted_enemy_still_does_not(self) -> None:
        context = make_context(900.0, detection_range=300.0)

        assert not is_player_detected(context)

    def test_attack_range_is_the_enemys_own_too(self) -> None:
        assert is_in_attack_range(make_context(280.0, attack_range=320.0))
        assert not is_in_attack_range(make_context(280.0, attack_range=40.0))

    def test_a_missing_player_is_never_detected(self) -> None:
        context = AIContext(
            entity_id="e1",
            position=Vector2.zero(),
            player_position=None,
            distance_to_player=float("inf"),
            dt=1 / 60,
            detection_range=1400.0,
        )

        assert not is_player_detected(context)
        assert not is_in_attack_range(context)


class TestSpawnedEnemiesCanReachTheFight:
    """A wave spawns off the field; its detection has to cover the field."""

    @pytest.mark.parametrize("kind", ["chaser", "shooter", "bomber"])
    def test_detection_spans_the_arena_diagonal(self, kind: str) -> None:
        pool = EnemyPool(EntityManager(), size=4)
        entity = pool.spawn_enemy(Vector2(0, 0), kind, 1.0)

        diagonal = (ARENA.width**2 + ARENA.height**2) ** 0.5
        assert entity is not None
        assert entity.enemy_ai.detection_range > diagonal
