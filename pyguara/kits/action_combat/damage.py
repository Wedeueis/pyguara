"""The damage pipeline: mitigation, invincibility, and Health mutation.

Combines `kits/stats`' pure formulas with `Health`'s state into the one
function a hit -- melee, projectile, hazard, DoT tick -- actually calls.
Which stat means "defense" for a given `DamageType` is this kit's own
vocabulary to impose (unlike `kits/stats`, which stays generic): `"armor"`
for `PHYSICAL`, `"resistance"` for `ELEMENTAL`. A game not using those
names supplies its own `StatBlock` with them, or passes `stats=None` to
skip mitigation entirely.
"""

from __future__ import annotations

from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.action_combat.events import DamageDealt
from pyguara.kits.action_combat.health import Health
from pyguara.kits.stats import (
    DamageType,
    StatBlock,
    effective_defense,
    get_stat,
    mitigation_from_defense,
)

# Stat names this pipeline reads mitigation from. A game is free to ignore
# these and pass stats=None, doing its own mitigation before calling in
# with a final amount.
ARMOR_STAT = "armor"
RESISTANCE_STAT = "resistance"

_DEFENSE_STAT_BY_TYPE = {
    DamageType.PHYSICAL: ARMOR_STAT,
    DamageType.ELEMENTAL: RESISTANCE_STAT,
}


def apply_damage(
    dispatcher: EventDispatcher,
    target_id: str,
    target: Health,
    amount: float,
    damage_type: DamageType,
    target_stats: StatBlock | None = None,
    pierce_fraction: float = 0.0,
    mitigation_scaling: float = 50.0,
    is_critical: bool = False,
    crit_multiplier: float = 1.5,
    invincibility_duration: float = 0.0,
    attacker: str | None = None,
) -> DamageDealt:
    """Apply one hit to `target`, dispatch the result, and return it.

    A no-op on `target.current` (but still dispatched, with `amount=0`)
    while `target.is_invincible` -- a listener wanting "was this blocked"
    reads `amount == 0`, rather than needing a separate silence to mean it.

    Args:
        dispatcher: Where `DamageDealt` is dispatched.
        target_id: `target`'s owning entity id, for the event.
        target: The `Health` component taking the hit.
        amount: Base damage, before crit and mitigation.
        damage_type: What kind of damage this is. `TRUE` skips mitigation
            entirely, regardless of `target_stats`.
        target_stats: The target's stats, for mitigation. None skips
            mitigation (the caller already applied it, or the target has
            no stats at all).
        pierce_fraction: How much of the relevant defense stat the
            attacker ignores, 0.0-1.0. See `kits.stats.effective_defense`.
        mitigation_scaling: Passed straight to
            `kits.stats.mitigation_from_defense`.
        is_critical: Whether to apply `crit_multiplier`.
        crit_multiplier: Damage multiplier for a critical hit.
        invincibility_duration: Seconds of invincibility to grant on a
            successful (non-invincible, `amount > 0`) hit. 0 (the default)
            grants none -- a DoT tick typically shouldn't reset i-frames a
            melee hit just granted.
        attacker: The entity id responsible, if any. See `DamageDealt.attacker`.

    Returns:
        The `DamageDealt` event, already dispatched.
    """
    if target.is_invincible:
        event = DamageDealt(
            target=target_id,
            attacker=attacker,
            amount=0.0,
            damage_type=damage_type,
            is_critical=is_critical,
            killed=False,
        )
        dispatcher.dispatch(event)
        return event

    damage = amount * crit_multiplier if is_critical else amount

    if damage_type is not DamageType.TRUE and target_stats is not None:
        defense_stat = _DEFENSE_STAT_BY_TYPE.get(damage_type)
        if defense_stat is not None:
            defense = get_stat(target_stats, defense_stat)
            defense = effective_defense(defense, pierce_fraction)
            mitigation = mitigation_from_defense(defense, mitigation_scaling)
            damage *= 1.0 - mitigation

    damage = max(0.0, damage)
    target.current = max(0.0, target.current - damage)
    if damage > 0 and invincibility_duration > 0:
        target.invincible_timer = invincibility_duration

    event = DamageDealt(
        target=target_id,
        attacker=attacker,
        amount=damage,
        damage_type=damage_type,
        is_critical=is_critical,
        killed=not target.is_alive,
    )
    dispatcher.dispatch(event)
    return event
