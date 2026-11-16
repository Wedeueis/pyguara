"""Entity-to-entity relations: who owns whom.

Distinct from `Transform` parenting. A `Transform` parent is spatial:
"my position is expressed relative to yours". `ChildOf` is ownership:
"when you are destroyed, so am I". A health bar above an enemy wants
both; a spawner's minions want ownership with no spatial relationship.

An entity that wants both attaches a `ChildOf` and sets its
`Transform` parent.
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
