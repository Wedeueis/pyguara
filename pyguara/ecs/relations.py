"""Entity-to-entity relations: who owns whom.

Distinct from `Transform`'s parenting, and deliberately so. A `Transform`
parent is *spatial* -- it says "my position is expressed relative to
yours", and a turret bolted to a moving ship needs it. `ChildOf` is
*ownership* -- it says "when you are destroyed, so am I", which is a
different question with a different answer. A health bar floating above an
enemy wants both; a dropped item that should outlive the enemy that
carried it wants neither; a spawner's minions that should die with it want
ownership without any spatial relationship at all.

Keeping them separate is what lets each be used alone. They are composed,
not conflated: an entity that wants both attaches a `ChildOf` and sets its
`Transform` parent, and the two happen to name the same entity.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.ecs.component import BaseComponent


@dataclass(slots=True)
class ChildOf(BaseComponent):
    """Marks an entity as owned by another, for cascade destruction.

    Attach it through `EntityManager.set_parent()` rather than
    `add_component()`, and change it the same way. The manager keeps a
    reverse index (parent -> children) so a cascade costs nothing per
    destroy, and that index is maintained from `set_parent()` and from the
    component add/remove hooks -- assigning `parent_id` in place bypasses
    both and leaves the index describing a parent that no longer claims
    this entity. The same contract `entity._components` has always had.

    Attributes:
        parent_id: The id of the owning entity.
    """

    parent_id: str = ""

    def __post_init__(self) -> None:
        """Initialise the base-class state the dataclass `__init__` skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a
        zero-argument `super()` still resolves against the discarded
        original, raising TypeError on every instantiation.
        """
        BaseComponent.__init__(self)
