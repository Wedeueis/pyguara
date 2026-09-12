"""Tests for Protocolo Bandeira's arena and its waves.

The demo's play area is no longer the whole window, which moves two
things that were previously implicit. Enemies spawn *outside* the arena
and walk in, so spawn placement is now relative to a rectangle rather
than to the screen; and a spawn is telegraphed on the ground before it
happens, so a wave is not finished when the last enemy dies -- it is
finished when nothing is queued, nothing is ringed, and nothing is alive.

The enemy AI's own ranges, which the spawn move also depended on, are
covered in `test_protocolo_bandeira_ai.py`.
"""

from __future__ import annotations

from games.protocolo_bandeira.events import WaveCompleteEvent
from games.protocolo_bandeira.pooling import EnemyPool
from games.protocolo_bandeira.wave_manager import WaveManager
from pyguara.common.random import RandomStream
from pyguara.common.types import Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher

ARENA = Rect(26, 104, 908, 544)


class TestWaveSpawnPlacement:
    def test_spawns_land_outside_the_arena(self) -> None:
        manager = WaveManager(
            EnemyPool(EntityManager(), size=32),
            EventDispatcher(),
            ARENA,
            RandomStream(11),
        )

        for _ in range(40):
            position = manager._get_spawn_position(Vector2(480, 360))
            assert not ARENA.contains_point(position)

    def test_spawns_stay_within_reach_of_the_arena(self) -> None:
        """Far enough out to walk in from, not so far as to be a hike."""
        manager = WaveManager(
            EnemyPool(EntityManager(), size=32),
            EventDispatcher(),
            ARENA,
            RandomStream(11),
        )
        reachable = ARENA.inflate(
            WaveManager.SPAWN_MARGIN * 2 + 2, WaveManager.SPAWN_MARGIN * 2 + 2
        )

        for _ in range(40):
            assert reachable.contains_point(
                manager._get_spawn_position(Vector2(480, 360))
            )


class TestSpawnsAreTelegraphed:
    def make(self) -> tuple[WaveManager, EnemyPool, EventDispatcher]:
        pool = EnemyPool(EntityManager(), size=64)
        dispatcher = EventDispatcher()
        manager = WaveManager(pool, dispatcher, ARENA, RandomStream(3))
        return manager, pool, dispatcher

    def test_a_ring_appears_before_the_enemy_does(self) -> None:
        manager, pool, _ = self.make()
        manager.start_wave(1)

        # Long enough for the director to release the first entry, but
        # well inside the warning's lead.
        manager.update(0.2, Vector2(480, 360))

        assert manager.warnings
        assert len(pool.get_active()) == 0

    def test_the_enemy_arrives_when_the_ring_closes(self) -> None:
        manager, pool, _ = self.make()
        manager.start_wave(1)
        manager.update(0.2, Vector2(480, 360))
        ringed = manager.warnings[0][0]

        manager.update(WaveManager.WARNING_LEAD, Vector2(480, 360))

        active = pool.get_active()
        assert len(active) >= 1
        assert any(e.transform.position == ringed for e in active)

    def test_the_ring_tightens_as_the_spawn_approaches(self) -> None:
        manager, _, _ = self.make()
        manager.start_wave(1)
        manager.update(0.2, Vector2(480, 360))
        first = manager.warnings[0][1]

        manager.update(WaveManager.WARNING_LEAD / 2, Vector2(480, 360))

        assert manager.warnings[0][1] > first

    def test_a_wave_is_not_over_while_a_ring_is_still_closing(self) -> None:
        """The last kill used to end the wave even with spawns pending."""
        manager, pool, dispatcher = self.make()
        completed: list[WaveCompleteEvent] = []
        dispatcher.subscribe(WaveCompleteEvent, completed.append)

        manager.start_wave(1)
        # Run until the first enemy has arrived. The director releases
        # faster than a ring closes, so the next one is always already
        # ringed by the time the previous lands.
        for _ in range(8):
            manager.update(0.1, Vector2(480, 360))
        assert len(pool.get_active()) == 1
        assert manager.warnings

        manager.on_enemy_killed()

        assert completed == []
        assert manager.is_wave_active

    def test_pending_rings_count_as_enemies_remaining(self) -> None:
        manager, _, _ = self.make()
        manager.start_wave(1)
        manager.update(0.2, Vector2(480, 360))

        assert manager.enemies_remaining == WaveManager.BASE_ENEMIES


class TestWaveMeter:
    def test_it_is_empty_before_a_wave_starts(self) -> None:
        manager = WaveManager(
            EnemyPool(EntityManager(), size=32),
            EventDispatcher(),
            ARENA,
            RandomStream(5),
        )

        assert manager.wave_fraction == 0.0

    def test_it_is_full_at_the_start_of_a_wave(self) -> None:
        manager = WaveManager(
            EnemyPool(EntityManager(), size=32),
            EventDispatcher(),
            ARENA,
            RandomStream(5),
        )
        manager.start_wave(1)

        assert manager.wave_fraction == 1.0

    def test_it_drains_as_the_wave_is_cleared(self) -> None:
        manager = WaveManager(
            EnemyPool(EntityManager(), size=32),
            EventDispatcher(),
            ARENA,
            RandomStream(5),
        )
        manager.start_wave(1)
        # Bring the whole wave onto the field.
        for _ in range(60):
            manager.update(0.1, Vector2(480, 360))
        full = manager.wave_fraction

        manager.on_enemy_killed()

        assert manager.wave_fraction < full
