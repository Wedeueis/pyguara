"""Resist, mitigation and evasion math.

Pure functions -- no `Stat`/`ModifiableValue`/entity coupling, just the
arithmetic, so a game can call them against whatever it already computed
a stat's value as. Mined from `reclaimer_legacy`'s `damage_system.py` for
the formula shapes (a diminishing-returns defense curve, luck-scaled
chance), with its `Character`/`DamagePacket` orchestration stripped out --
that pipeline is `kits/action_combat`'s job, built on top of these.
"""

from __future__ import annotations


def effective_defense(base_defense: float, pierce_fraction: float) -> float:
    """Return `base_defense` reduced by an attacker's pierce.

    Args:
        base_defense: The defender's raw defense stat (armor, resistance).
        pierce_fraction: How much of that defense the attack ignores,
            0.0-1.0. 0.3 means 30% of the defense is ignored.

    Returns:
        The defense value mitigation actually sees.
    """
    return base_defense * (1.0 - pierce_fraction)


def mitigation_from_defense(defense: float, scaling: float) -> float:
    """Return the fraction of damage `defense` mitigates, as a diminishing curve.

    `defense / (defense + scaling)` -- 0.0 at zero defense, approaching but
    never reaching 1.0 as defense grows, so no amount of stacking ever
    makes a hit deal zero damage. `scaling` sets how much defense is needed
    to reach a given mitigation fraction; a game commonly derives it from
    the defender's level or the attacker's own offensive stat, but this
    function has no opinion on that -- it just takes the number.

    Args:
        defense: Defense value to convert, typically `effective_defense()`'s
            result.
        scaling: The defense value at which mitigation reaches 50%. Must be
            positive.

    Returns:
        Mitigation fraction, 0.0-1.0. Multiply incoming damage by
        `1 - mitigation_from_defense(...)` to get the damage that lands.
    """
    if defense <= 0:
        return 0.0
    return defense / (defense + scaling)


def apply_luck_to_chance(base_chance: float, luck: float) -> float:
    """Scale a chance (dodge, block, crit, ...) by a luck-like modifier.

    `base_chance * (1 + luck)` -- `luck=0.0` leaves the chance unchanged;
    `luck=0.25` raises it by a quarter. Clamped to `[0.0, 1.0]` since a
    chance outside that range isn't meaningful to a caller rolling against
    it (`random.random() < chance`).

    Args:
        base_chance: The unmodified chance, 0.0-1.0.
        luck: Fractional adjustment; negative lowers the chance.

    Returns:
        The adjusted chance, clamped to `[0.0, 1.0]`.
    """
    return max(0.0, min(1.0, base_chance * (1.0 + luck)))
