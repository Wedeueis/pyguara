"""The generic, overridable gameplay effect.

A plain domain object, like `Modifier`/`ModifiableValue` -- not an ECS
component. No fixed subtypes or categories: `reclaimer_legacy` baked in
four (Augmentation/Response/Tactical/Adaptive); per #28, that's game data
here, not something this kit's type system imposes. What an effect
actually *does* -- apply a `kits.stats` modifier, subscribe to a
`kits.action_combat.DamageDealt` (or any other kit's event), tick damage
each frame -- is entirely up to the subclass; this kit is coupled to other
kits only through core event dispatch, never a direct import.
"""

from __future__ import annotations

from typing import Any

from pyguara.events.dispatcher import EventDispatcher


class Effect:
    """Base class for a stacking, time-limited or reactive gameplay effect.

    Attributes:
        key: Identity used by `container.add_effect()`'s stacking rules to
            decide whether two applications are "the same" effect.
            Defaults to the class name; override for two effects of the
            same class to be considered distinct (or two different classes
            to share stacking, if a game wants that).
        duration: Seconds until this effect auto-expires, or None for
            permanent (removed only by an explicit `remove_effect()` call).
        elapsed: Seconds since this effect was applied. `update()`'s
            default implementation advances this; a subclass overriding
            `update()` for its own tick behavior (damage-over-time, say)
            should call `super().update(dt)` to keep expiry working.
        source: Whatever applied this effect, if anything -- an item id,
            an attacker entity id, a status name. Not used by this class
            itself; here for a subclass or `key` to key off.
    """

    def __init__(
        self,
        key: str | None = None,
        duration: float | None = None,
        source: Any = None,
    ) -> None:
        """Create an effect, not yet applied to anything.

        Args:
            key: See `key` attribute. Defaults to the class name.
            duration: See `duration` attribute.
            source: See `source` attribute.
        """
        self.key = key if key is not None else type(self).__name__
        self.duration = duration
        self.elapsed = 0.0
        self.source = source

    @property
    def is_expired(self) -> bool:
        """Whether `duration` has elapsed. Always False for a permanent effect."""
        return self.duration is not None and self.elapsed >= self.duration

    def on_apply(self, entity_id: str, dispatcher: EventDispatcher) -> None:
        """Run once when this effect is newly added to a container.

        Override to apply a stat modifier, subscribe to an event, or
        anything else this effect needs set up. The default does nothing.

        Args:
            entity_id: The entity this effect now applies to.
            dispatcher: `pyguara.events.dispatcher.EventDispatcher`, for
                subscribing to whatever event this effect reacts to.
        """

    def on_remove(self, entity_id: str, dispatcher: EventDispatcher) -> None:
        """Run once when this effect is removed -- expiry or explicit.

        Override to undo whatever `on_apply()` set up: remove a stat
        modifier (by source, this effect itself is a natural choice),
        unsubscribe from an event. The default does nothing.

        Args:
            entity_id: The entity this effect no longer applies to.
            dispatcher: Same dispatcher passed to `on_apply()`.
        """

    def update(self, dt: float) -> None:
        """Run once a tick while this effect is active.

        The default only advances `elapsed`, for `is_expired`. Override
        for tick-based behavior (a DoT's per-tick damage); call
        `super().update(dt)` to keep expiry tracking working.

        Args:
            dt: Seconds since the last tick.
        """
        self.elapsed += dt
