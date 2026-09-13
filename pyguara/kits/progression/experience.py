"""Experience, and the one function that grants it.

Data component plus a free function, matching `StatBlock`/`get_stat` and
`Health`/`apply_damage`: the component holds the numbers, and the
behaviour that mutates them lives beside it rather than on it.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.ecs.component import StrictComponent
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.progression.curve import LevelCurve
from pyguara.kits.progression.events import ExperienceGained, LeveledUp


@dataclass(slots=True)
class Experience(StrictComponent):
    """An entity's progress through a level curve.

    Attributes:
        current: Experience toward the next level. Reset by the carry-over
            on each level-up rather than zeroed, so a grant that overshoots
            is not silently thrown away.
        total: Lifetime experience, never spent. What an end-of-run screen
            reports.
        level: Current level, 1-based.
        pending_levels: Levels reached but not yet spent. `grant_experience`
            increments this; the game decrements it as it hands out
            whatever a level buys. The kit never spends it itself -- it has
            no idea what a level is worth.
    """

    current: float = 0.0
    total: float = 0.0
    level: int = 1
    pending_levels: int = 0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a
        zero-argument `super()` still resolves against the discarded
        original, raising TypeError on every instantiation.
        """
        StrictComponent.__init__(self)


def grant_experience(
    dispatcher: EventDispatcher,
    entity_id: str,
    experience: Experience,
    curve: LevelCurve,
    amount: float,
    max_level: int | None = None,
) -> int:
    """Add `amount` to `experience`, levelling it up as far as it reaches.

    Carry-over is kept: crossing a level costs exactly that level's price
    and the remainder counts toward the next, so a single large grant can
    cross several levels and lands in the same place as the same total
    delivered in pieces.

    Args:
        dispatcher: Where `ExperienceGained` and `LeveledUp` are
            dispatched.
        entity_id: `experience`'s owning entity id, for the events.
        experience: The component to advance.
        curve: Prices each level.
        amount: Experience to add. Zero still dispatches; negative is
            ignored, since "take experience back" is a different operation
            that would need its own de-levelling rules.
        max_level: Level at which progression stops, if any. At the cap,
            `current` stops accumulating rather than growing a number
            nothing will ever spend -- but `total` still counts, because an
            end-of-run screen should report everything collected.

    Returns:
        How many levels were crossed by this grant.
    """
    amount = max(0.0, amount)
    experience.total += amount

    capped = max_level is not None and experience.level >= max_level
    if not capped:
        experience.current += amount

    # Resolve every crossing first, then dispatch. `ExperienceGained`
    # carries the settled numbers and goes out before the `LeveledUp`s it
    # caused, so a listener drawing an experience bar has already redrawn
    # it by the time another listener pushes a level-up scene over the top.
    crossings: list[LeveledUp] = []
    while not capped:
        cost = curve.cost_for(experience.level)
        if experience.current < cost:
            break

        experience.current -= cost
        experience.level += 1
        experience.pending_levels += 1

        capped = max_level is not None and experience.level >= max_level
        if capped:
            # At the cap the leftover is dropped rather than held: it can
            # never be spent, and keeping it would show a progress bar
            # filling against a level that will not arrive.
            experience.current = 0.0

        crossings.append(
            LeveledUp(
                entity=entity_id,
                level=experience.level,
                pending_levels=experience.pending_levels,
            )
        )

    dispatcher.dispatch(
        ExperienceGained(
            entity=entity_id,
            amount=amount,
            current=experience.current,
            total=experience.total,
            level=experience.level,
        )
    )
    for crossing in crossings:
        dispatcher.dispatch(crossing)
    return len(crossings)
