"""Turns a Hitbox/Hurtbox overlap into a call to `apply_damage()`."""

from __future__ import annotations

from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.action_combat.damage import apply_damage
from pyguara.kits.action_combat.health import Health
from pyguara.kits.action_combat.hitbox import Hitbox
from pyguara.kits.action_combat.hurtbox import Hurtbox
from pyguara.kits.stats import StatBlock
from pyguara.physics.events import OnTriggerEnter


class HitboxSystem:
    """Applies damage when a `Hitbox`'s `TriggerVolume` enters a `Hurtbox`.

    Purely event-driven -- `update()` is a no-op present only to satisfy
    `pyguara.systems.protocols.System` for `SystemManager` registration.
    `TriggerSystem` (registered separately) is what actually builds and
    maintains the `Hitbox` entity's sensor collider; this only reacts to
    the `OnTriggerEnter` that produces.
    """

    def __init__(
        self, entity_manager: EntityManager, dispatcher: EventDispatcher
    ) -> None:
        """Subscribe to the trigger event this system reacts to.

        Args:
            entity_manager: Source of the two entities in a hit.
            dispatcher: Subscribed to for `OnTriggerEnter`; also where
                `apply_damage()` dispatches `DamageDealt`.
        """
        self._entity_manager = entity_manager
        self._dispatcher = dispatcher
        dispatcher.subscribe(OnTriggerEnter, self._on_trigger_enter)

    def update(self, dt: float) -> None:
        """No-op: see class docstring."""

    def _on_trigger_enter(self, event: OnTriggerEnter) -> None:
        trigger_entity = self._entity_manager.get_entity(event.trigger_entity)
        if trigger_entity is None or not trigger_entity.has_component(Hitbox):
            return
        hitbox = trigger_entity.get_component(Hitbox)

        target = self._entity_manager.get_entity(event.other_entity)
        if target is None:
            return
        if not target.has_component(Hurtbox) or not target.has_component(Health):
            return
        hurtbox = target.get_component(Hurtbox)

        if (
            hitbox.team is not None
            and hurtbox.team is not None
            and hitbox.team == hurtbox.team
        ):
            return  # Same side; never damage a teammate.

        target_stats = (
            target.get_component(StatBlock) if target.has_component(StatBlock) else None
        )

        apply_damage(
            self._dispatcher,
            target.id,
            target.get_component(Health),
            hitbox.damage,
            hitbox.damage_type,
            target_stats=target_stats,
            pierce_fraction=hitbox.pierce_fraction,
            is_critical=hitbox.is_critical,
            invincibility_duration=hitbox.invincibility_duration,
            attacker=hitbox.attacker,
        )
