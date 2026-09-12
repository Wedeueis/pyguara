"""Vinagre: Matilha - Combat.

The fight the rest of the demo exists to stage. Three systems:

- `PackCombatSystem` -- dogs in contact bite the jaguar, on a cooldown.
- `JaguarCombatSystem` -- the jaguar's STALK -> WINDUP -> SWIPE -> RECOVER
  loop, which is the whole skill expression: the wind-up is a visible tell,
  Scatter dodges it, and a whiffed swipe leaves the jaguar open to bonus
  damage.
- `PackRecoverySystem` -- downed dogs get back up, faster when packmates
  are near, so a scattered pack pays for it and a tight one recovers.

Damage runs through `pyguara.kits.action_combat.apply_damage` rather than
mutating `Health` here, so crits, invincibility windows and the
`DamageDealt` event all come from the kit.
"""

from __future__ import annotations

import math
from typing import cast

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
from pyguara.kits.action_combat import Health, apply_damage
from pyguara.kits.pack import PackMember, PackRole
from pyguara.kits.stats import DamageType

# --- Pack offence -----------------------------------------------------
BITE_RANGE = 34.0
BITE_COOLDOWN = 0.75
BITE_DAMAGE_FLANKER = 4.0
BITE_DAMAGE_VANGUARD = 7.0  # the player's own dog hits hardest
BITE_FLASH_SECONDS = 0.18
# Biting a jaguar that just whiffed a swipe is the payoff for dodging.
RECOVER_DAMAGE_MULTIPLIER = 2.5

# --- Jaguar defence ---------------------------------------------------
SWIPE_TRIGGER_RANGE = 52.0
SWIPE_RANGE = 74.0
SWIPE_ARC_DEGREES = 150.0
SWIPE_KNOCKBACK = 420.0
WINDUP_SECONDS = 0.65  # the tell: long enough to read and react to
SWIPE_SECONDS = 0.18
RECOVER_SECONDS = 0.9
SWIPE_COOLDOWN = 1.9
DOWNED_SECONDS = 3.2

# --- Pack recovery ----------------------------------------------------
RALLY_RADIUS = 90.0
RALLY_SPEEDUP_PER_DOG = 0.9
KNOCKBACK_DECAY = 0.12  # fraction of knockback velocity retained per second


def _alive_dogs(em: EntityManager) -> list[Entity]:
    return [
        entity
        for entity in em.get_entities_with(PackMember, DogState, Transform)
        if not entity.get_component(DogState).is_downed
    ]


class PackCombatSystem:
    """Dogs in contact with the jaguar bite it, on a per-dog cooldown.

    Also decays swipe knockback, which is applied to `Transform` here
    rather than through the flocking force so a swiped dog is genuinely
    thrown clear instead of merely nudged.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        jaguar_id: str,
        event_dispatcher: EventDispatcher,
    ) -> None:
        self._em = entity_manager
        self._jaguar_id = jaguar_id
        self._dispatcher = event_dispatcher

    def update(self, dt: float) -> None:
        jaguar = self._em.get_entity(self._jaguar_id)
        for dog in self._em.get_entities_with(PackMember, DogState, Transform):
            state = dog.get_component(DogState)
            state.bite_cooldown = max(0.0, state.bite_cooldown - dt)
            state.bite_flash = max(0.0, state.bite_flash - dt)

            if state.knockback.length > 1.0:
                transform = dog.get_component(Transform)
                transform.position = transform.position + state.knockback * dt
                state.knockback = state.knockback * (KNOCKBACK_DECAY**dt)
            else:
                state.knockback = Vector2(0, 0)

        if jaguar is None or not jaguar.has_component(Health):
            return
        jaguar_health = jaguar.get_component(Health)
        jaguar_state = jaguar.get_component(JaguarState)
        jaguar_pos = jaguar.get_component(Transform).position
        if not jaguar_health.is_alive:
            return

        for dog in _alive_dogs(self._em):
            state = dog.get_component(DogState)
            if state.bite_cooldown > 0.0:
                continue
            dog_pos = dog.get_component(Transform).position
            if (dog_pos - jaguar_pos).length > BITE_RANGE:
                continue

            role = dog.get_component(PackMember).role
            damage = (
                BITE_DAMAGE_VANGUARD
                if role is PackRole.VANGUARD
                else BITE_DAMAGE_FLANKER
            )
            if jaguar_state.phase is JaguarPhase.RECOVER:
                damage *= RECOVER_DAMAGE_MULTIPLIER

            state.bite_cooldown = BITE_COOLDOWN
            state.bite_flash = BITE_FLASH_SECONDS
            jaguar_state.hurt_flash = 0.14

            apply_damage(
                self._dispatcher,
                target_id=jaguar.id,
                target=jaguar_health,
                amount=damage,
                damage_type=DamageType.PHYSICAL,
                attacker=dog.id,
            )
            self._dispatcher.dispatch(
                PackBitEvent(
                    dog_entity_id=dog.id,
                    position=dog_pos.lerp(jaguar_pos, 0.6),
                    damage=damage,
                    was_punish=jaguar_state.phase is JaguarPhase.RECOVER,
                )
            )


class JaguarCombatSystem:
    """Drives the jaguar's STALK -> WINDUP -> SWIPE -> RECOVER loop.

    `JaguarAISystem` owns fleeing; this owns fighting back, and gates
    movement by reading `phase` (the jaguar plants its feet to swing).
    Kept separate so the "how it runs away" and "how it hits back"
    behaviours stay independently readable and testable.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        jaguar_id: str,
        event_dispatcher: EventDispatcher,
        pack_break_threshold: int,
    ) -> None:
        self._em = entity_manager
        self._jaguar_id = jaguar_id
        self._dispatcher = event_dispatcher
        self._pack_break_threshold = pack_break_threshold
        self._pack_broken = False

    def update(self, dt: float) -> None:
        jaguar = self._em.get_entity(self._jaguar_id)
        if jaguar is None:
            return
        state = jaguar.get_component(JaguarState)
        state.hurt_flash = max(0.0, state.hurt_flash - dt)
        state.swipe_cooldown = max(0.0, state.swipe_cooldown - dt)
        if jaguar.has_component(Health) and not jaguar.get_component(Health).is_alive:
            state.phase = JaguarPhase.STALK
            return

        position = jaguar.get_component(Transform).position
        state.phase_timer = max(0.0, state.phase_timer - dt)

        if state.phase is JaguarPhase.STALK:
            self._maybe_wind_up(state, position)
        elif state.phase is JaguarPhase.WINDUP and state.phase_timer <= 0.0:
            self._swing(jaguar, state, position)
        elif state.phase is JaguarPhase.SWIPE and state.phase_timer <= 0.0:
            state.phase = JaguarPhase.RECOVER
            state.phase_timer = RECOVER_SECONDS
        elif state.phase is JaguarPhase.RECOVER and state.phase_timer <= 0.0:
            state.phase = JaguarPhase.STALK

    def _maybe_wind_up(self, state: JaguarState, position: Vector2) -> None:
        if state.swipe_cooldown > 0.0:
            return
        dogs = _alive_dogs(self._em)
        if not dogs:
            return
        nearest = min(
            dogs,
            key=lambda dog: (dog.get_component(Transform).position - position).length,
        )
        offset = nearest.get_component(Transform).position - position
        if offset.length > SWIPE_TRIGGER_RANGE:
            return

        state.phase = JaguarPhase.WINDUP
        state.phase_timer = WINDUP_SECONDS
        if offset.length > 0.001:
            state.swipe_direction = cast(Vector2, offset.normalized())

    def _swing(self, jaguar: Entity, state: JaguarState, position: Vector2) -> None:
        state.phase = JaguarPhase.SWIPE
        state.phase_timer = SWIPE_SECONDS
        state.swipe_cooldown = SWIPE_COOLDOWN

        half_arc = math.radians(SWIPE_ARC_DEGREES) * 0.5
        hit_any = False
        for dog in _alive_dogs(self._em):
            offset = dog.get_component(Transform).position - position
            distance = offset.length
            if distance > SWIPE_RANGE or distance < 0.001:
                continue
            direction = cast(Vector2, offset.normalized())
            if math.acos(max(-1.0, min(1.0, direction.dot(state.swipe_direction)))) > (
                half_arc
            ):
                continue

            hit_any = True
            dog_state = dog.get_component(DogState)
            dog_state.downed_timer = DOWNED_SECONDS
            dog_state.knockback = direction * SWIPE_KNOCKBACK
            self._dispatcher.dispatch(
                DogDownedEvent(
                    dog_entity_id=dog.id,
                    position=dog.get_component(Transform).position,
                )
            )

        self._dispatcher.dispatch(
            JaguarSwipedEvent(
                position=position, direction=state.swipe_direction, hit=hit_any
            )
        )
        self._check_pack_broken()

    def _check_pack_broken(self) -> None:
        if self._pack_broken:
            return
        downed = sum(
            1
            for dog in self._em.get_entities_with(PackMember, DogState)
            if dog.get_component(DogState).is_downed
        )
        if downed >= self._pack_break_threshold:
            self._pack_broken = True
            self._dispatcher.dispatch(PackBrokenEvent(downed_count=downed))


class PackRecoverySystem:
    """Counts downed dogs back up, faster the more packmates stand nearby.

    The pack's own cohesion is the healing mechanic: a dog left alone
    takes the full `DOWNED_SECONDS`, while one its packmates rally around
    is back in the fight in a fraction of that -- which is what makes
    Scatter genuinely costly and regrouping worth doing.
    """

    def __init__(self, entity_manager: EntityManager) -> None:
        self._em = entity_manager

    def update(self, dt: float) -> None:
        dogs = list(self._em.get_entities_with(PackMember, DogState, Transform))
        for dog in dogs:
            state = dog.get_component(DogState)
            if not state.is_downed:
                continue
            position = dog.get_component(Transform).position
            helpers = sum(
                1
                for other in dogs
                if other.id != dog.id
                and not other.get_component(DogState).is_downed
                and (other.get_component(Transform).position - position).length
                <= RALLY_RADIUS
            )
            state.downed_timer = max(
                0.0, state.downed_timer - dt * (1.0 + helpers * RALLY_SPEEDUP_PER_DOG)
            )
