"""A generic ECS entity pool: acquire/release without garbage-collector churn.

The question every genre with high-frequency spawn/despawn asks (pooled
bullets, particles-as-entities, wave-spawned enemies, an RTS unit pool) --
answered once here, mechanism only. What a pooled entity actually *is*
(its components, its reset logic) is entirely the caller's `factory`; this
module knows nothing about bullets, enemies, or any other game vocabulary.

Mined from `games/protocolo_bandeira`'s own `ObjectPool` -- its
`BulletPool`/`EnemyPool` subclasses turned out to be trivial factory
closures around the exact same acquire/release pattern, the same
"second/third consumer" signal that earlier promoted
`kits.loot.weighted_choice` to `pyguara.common.random`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pyguara.ecs.component import StrictComponent
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager


@dataclass(slots=True)
class Poolable(StrictComponent):
    """Marks an entity as belonging to an `EntityPool`.

    A pooled entity's factory must attach this itself -- `EntityPool`
    reads and writes it, but never adds one on a caller's behalf, since
    what else the entity needs (a reset position, a lifetime) is the
    factory's job regardless.

    Attributes:
        pool_name: Which pool this entity belongs to -- informational,
            not read by `EntityPool` itself.
        is_active: Whether this entity is currently acquired (in play) or
            idle in the pool, available for `acquire()`.
    """

    pool_name: str = ""
    is_active: bool = False

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a zero-argument
        `super()` still resolves against the discarded original, raising
        TypeError on every instantiation.
        """
        StrictComponent.__init__(self)


class EntityPool:
    """Pre-allocates entities once, then hands them out and takes them back.

    Every entity is created exactly once, at construction, via `factory` --
    never during gameplay. `acquire()`/`release()` toggle `Poolable.is_active`
    and move an entity between the available and active sets; nothing is
    ever destroyed. Fixed capacity: `acquire()` returns `None` once
    exhausted rather than growing on demand, so a caller with a bursty
    spawn rate picks `size` deliberately instead of discovering an
    unbounded pool the hard way.

    The active set is a dict keyed on entity id, not a list, and that is
    load-bearing rather than incidental. A list costs two O(n) scans per
    `release()` -- one to check membership, one to remove -- so putting a
    whole pool away is quadratic in its size. Measured before the change,
    draining 3000 entities took 74 ms, or four and a half frames at 60 Hz,
    from a structure whose entire purpose is high-frequency spawn and
    despawn. Dicts preserve insertion order, so `get_active()`'s
    acquisition-order guarantee survives the change for free.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        pool_name: str,
        size: int,
        factory: Callable[[EntityManager, int], Entity],
    ) -> None:
        """Pre-allocate `size` entities via `factory`.

        Args:
            entity_manager: Where pooled entities live.
            pool_name: Recorded on each entity's `Poolable.pool_name`.
            size: How many entities to pre-allocate.
            factory: Builds one entity, given the manager and its index
                (0-based) within this pool. Must attach a `Poolable`
                component along with whatever else defines the entity --
                `EntityPool` sets its `pool_name`/`is_active` but does not
                add the component itself.
        """
        self._entity_manager = entity_manager
        self._pool_name = pool_name
        self._available: list[Entity] = []
        # Keyed on entity id for O(1) release; insertion-ordered, which is
        # what keeps `get_active()` in acquisition order.
        self._active: dict[str, Entity] = {}

        for index in range(size):
            entity = factory(entity_manager, index)
            poolable = entity.get_component(Poolable)
            poolable.pool_name = pool_name
            poolable.is_active = False
            self._available.append(entity)

    def acquire(self) -> Entity | None:
        """Take one entity out of the pool, marking it active.

        Returns:
            An available entity, or `None` if every entity is already
            active.
        """
        if not self._available:
            return None
        entity = self._available.pop()
        entity.get_component(Poolable).is_active = True
        self._active[entity.id] = entity
        return entity

    def release(self, entity: Entity) -> None:
        """Return `entity` to the pool, marking it idle.

        A no-op if `entity` is not currently active in this pool -- which
        covers releasing the same entity twice, and releasing an entity
        that belongs to a different pool.

        The identity check is deliberate. Looking the id up and comparing
        the stored object with `is` keeps exactly the semantics the old
        list membership test had, rather than trusting an id to be unique
        across every pool sharing an `EntityManager`.
        """
        if self._active.get(entity.id) is not entity:
            return
        del self._active[entity.id]
        entity.get_component(Poolable).is_active = False
        self._available.append(entity)

    def get_active(self) -> list[Entity]:
        """Every entity currently acquired, in acquisition order."""
        return list(self._active.values())

    @property
    def available_count(self) -> int:
        """How many entities can still be `acquire()`d."""
        return len(self._available)

    @property
    def active_count(self) -> int:
        """How many entities are currently acquired."""
        return len(self._active)
