"""Tests for Vinagre: Matilha's combat loop (games/vinagre_matilha/combat.py).

The fight is the demo's actual game, so its rules are tested directly
rather than only through headless capture: bites and their cooldown, the
telegraphed swipe that downs dogs, the punish window that rewards dodging
it, and the rally that brings downed dogs back.
"""

from __future__ import annotations

from games.vinagre_matilha.combat import (
    BITE_DAMAGE_FLANKER,
    BITE_DAMAGE_VANGUARD,
    BITE_RANGE,
    DOWNED_SECONDS,
    RECOVER_DAMAGE_MULTIPLIER,
    SWIPE_RANGE,
    WINDUP_SECONDS,
    JaguarCombatSystem,
    PackCombatSystem,
    PackRecoverySystem,
)
from games.vinagre_matilha.components import DogState, JaguarPhase, JaguarState
from games.vinagre_matilha.events import (
    DogDownedEvent,
    JaguarSwipedEvent,
    PackBitEvent,
    PackBrokenEvent,
)
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.action_combat import Health
from pyguara.kits.pack import PackMember, PackRole

_TICK = 1 / 60


def _dog(em: EntityManager, pos: Vector2, role: PackRole = PackRole.FLANKER) -> Entity:
    entity = em.create_entity()
    entity.add_component(Transform(position=pos))
    entity.add_component(PackMember(role=role, dog_id=entity.id))
    entity.add_component(DogState())
    return entity


def _jaguar(em: EntityManager, pos: Vector2, health: float = 100.0) -> Entity:
    entity = em.create_entity()
    entity.add_component(Transform(position=pos))
    entity.add_component(JaguarState())
    entity.add_component(Health(current=health, max_health=health))
    return entity


# ========== PackCombatSystem ==========


class TestPackCombatSystem:
    def test_a_dog_in_range_bites_the_jaguar(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(100, 100))
        _dog(em, Vector2(100 + BITE_RANGE - 4, 100))
        dispatcher = EventDispatcher()
        events: list[PackBitEvent] = []
        dispatcher.subscribe(PackBitEvent, events.append)

        PackCombatSystem(em, jaguar.id, dispatcher).update(_TICK)

        assert jaguar.get_component(Health).current == 100.0 - BITE_DAMAGE_FLANKER
        assert len(events) == 1

    def test_a_dog_out_of_range_does_not_bite(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(100, 100))
        _dog(em, Vector2(100 + BITE_RANGE + 20, 100))
        dispatcher = EventDispatcher()

        PackCombatSystem(em, jaguar.id, dispatcher).update(_TICK)

        assert jaguar.get_component(Health).current == 100.0

    def test_the_vanguard_bites_harder_than_a_flanker(self) -> None:
        assert BITE_DAMAGE_VANGUARD > BITE_DAMAGE_FLANKER
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(100, 100))
        _dog(em, Vector2(110, 100), role=PackRole.VANGUARD)
        dispatcher = EventDispatcher()

        PackCombatSystem(em, jaguar.id, dispatcher).update(_TICK)

        assert jaguar.get_component(Health).current == 100.0 - BITE_DAMAGE_VANGUARD

    def test_the_bite_cooldown_prevents_biting_every_frame(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(100, 100))
        _dog(em, Vector2(110, 100))
        system = PackCombatSystem(em, jaguar.id, EventDispatcher())

        for _ in range(10):
            system.update(_TICK)

        # Exactly one bite has landed despite ten frames in contact.
        assert jaguar.get_component(Health).current == 100.0 - BITE_DAMAGE_FLANKER

    def test_biting_a_staggered_jaguar_deals_bonus_damage(self) -> None:
        """The payoff for dodging: a whiffed swipe leaves it open."""
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(100, 100))
        jaguar.get_component(JaguarState).phase = JaguarPhase.RECOVER
        _dog(em, Vector2(110, 100))
        dispatcher = EventDispatcher()
        events: list[PackBitEvent] = []
        dispatcher.subscribe(PackBitEvent, events.append)

        PackCombatSystem(em, jaguar.id, dispatcher).update(_TICK)

        expected = BITE_DAMAGE_FLANKER * RECOVER_DAMAGE_MULTIPLIER
        assert jaguar.get_component(Health).current == 100.0 - expected
        assert events[0].was_punish is True

    def test_a_downed_dog_does_not_bite(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(100, 100))
        dog = _dog(em, Vector2(110, 100))
        dog.get_component(DogState).downed_timer = 2.0

        PackCombatSystem(em, jaguar.id, EventDispatcher()).update(_TICK)

        assert jaguar.get_component(Health).current == 100.0


# ========== JaguarCombatSystem ==========


class TestJaguarCombatSystem:
    def test_winds_up_when_a_dog_closes_in(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(100, 100))
        _dog(em, Vector2(120, 100))
        system = JaguarCombatSystem(em, jaguar.id, EventDispatcher(), 99)

        system.update(_TICK)

        assert jaguar.get_component(JaguarState).phase is JaguarPhase.WINDUP

    def test_does_not_wind_up_with_no_dog_nearby(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(100, 100))
        _dog(em, Vector2(600, 100))
        system = JaguarCombatSystem(em, jaguar.id, EventDispatcher(), 99)

        system.update(_TICK)

        assert jaguar.get_component(JaguarState).phase is JaguarPhase.STALK

    def test_the_swipe_downs_a_dog_still_in_the_arc(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(100, 100))
        dog = _dog(em, Vector2(130, 100))
        dispatcher = EventDispatcher()
        downed: list[DogDownedEvent] = []
        swiped: list[JaguarSwipedEvent] = []
        dispatcher.subscribe(DogDownedEvent, downed.append)
        dispatcher.subscribe(JaguarSwipedEvent, swiped.append)
        system = JaguarCombatSystem(em, jaguar.id, dispatcher, 99)

        for _ in range(int(WINDUP_SECONDS * 60) + 4):
            system.update(_TICK)

        assert dog.get_component(DogState).is_downed
        assert len(downed) == 1
        assert swiped and swiped[0].hit is True

    def test_a_dog_that_fled_the_arc_is_not_downed(self) -> None:
        """Scatter's whole purpose: leave the arc before the swing lands."""
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(100, 100))
        dog = _dog(em, Vector2(130, 100))
        dispatcher = EventDispatcher()
        swiped: list[JaguarSwipedEvent] = []
        dispatcher.subscribe(JaguarSwipedEvent, swiped.append)
        system = JaguarCombatSystem(em, jaguar.id, dispatcher, 99)

        system.update(_TICK)  # enters WINDUP
        # The dodge: well outside SWIPE_RANGE before the swing resolves.
        dog.get_component(Transform).position = Vector2(100 + SWIPE_RANGE + 60, 100)
        for _ in range(int(WINDUP_SECONDS * 60) + 4):
            system.update(_TICK)

        assert not dog.get_component(DogState).is_downed
        assert swiped and swiped[0].hit is False

    def test_the_phase_loop_returns_to_stalk(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(100, 100))
        _dog(em, Vector2(130, 100))
        system = JaguarCombatSystem(em, jaguar.id, EventDispatcher(), 99)
        state = jaguar.get_component(JaguarState)

        seen = set()
        for _ in range(300):
            system.update(_TICK)
            seen.add(state.phase)

        assert JaguarPhase.WINDUP in seen
        assert JaguarPhase.SWIPE in seen
        assert JaguarPhase.RECOVER in seen
        assert JaguarPhase.STALK in seen

    def test_pack_broken_fires_once_the_threshold_is_reached(self) -> None:
        em = EntityManager()
        jaguar = _jaguar(em, Vector2(100, 100))
        for offset in (-14, 0, 14):
            _dog(em, Vector2(120 + offset, 100))
        dispatcher = EventDispatcher()
        broken: list[PackBrokenEvent] = []
        dispatcher.subscribe(PackBrokenEvent, broken.append)
        system = JaguarCombatSystem(em, jaguar.id, dispatcher, pack_break_threshold=2)

        for _ in range(int(WINDUP_SECONDS * 60) + 4):
            system.update(_TICK)

        assert len(broken) == 1
        assert broken[0].downed_count >= 2


# ========== PackRecoverySystem ==========


class TestPackRecoverySystem:
    def test_a_downed_dog_recovers_over_time(self) -> None:
        em = EntityManager()
        dog = _dog(em, Vector2(0, 0))
        dog.get_component(DogState).downed_timer = 0.5
        system = PackRecoverySystem(em)

        for _ in range(40):
            system.update(_TICK)

        assert not dog.get_component(DogState).is_downed

    def test_nearby_packmates_speed_recovery_up(self) -> None:
        alone = EntityManager()
        lone_dog = _dog(alone, Vector2(0, 0))
        lone_dog.get_component(DogState).downed_timer = DOWNED_SECONDS

        rallied = EntityManager()
        helped_dog = _dog(rallied, Vector2(0, 0))
        helped_dog.get_component(DogState).downed_timer = DOWNED_SECONDS
        for offset in (20, 40, 60):
            _dog(rallied, Vector2(offset, 0))

        for _ in range(30):
            PackRecoverySystem(alone).update(_TICK)
            PackRecoverySystem(rallied).update(_TICK)

        assert (
            helped_dog.get_component(DogState).downed_timer
            < lone_dog.get_component(DogState).downed_timer
        )

    def test_an_upright_dog_is_untouched(self) -> None:
        em = EntityManager()
        dog = _dog(em, Vector2(0, 0))
        PackRecoverySystem(em).update(_TICK)
        assert dog.get_component(DogState).downed_timer == 0.0
