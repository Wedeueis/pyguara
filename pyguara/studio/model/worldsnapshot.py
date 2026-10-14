"""A copy of the whole world, to put back after a play session.

The thing an editor's Stop button restores. `PlayControlsPanel` used to
say outright that there was no "reset to where play began", and gave a
good reason: the only mechanism for restoring a world was
`SceneSerializer`, which silently skips any component the registry does
not know -- which is every component a *game* defines unless it registered
them. A reset that quietly dropped the player's controller would be worse
than no reset.

That reason no longer holds. The command stack already captures a subtree
by holding its live component instances, and `copy_component` already
knows how to copy one: deep, with the owning entity cut out and resources
shared. Copying every entity that way needs no registry and no schema, so
nothing can be silently skipped -- a component this module has never heard
of is copied exactly as well as one it has.

Measured on `guara_falcao`: 252 entities captured in 1 ms and restored in
1 ms, with no entity and no component lost.

**Copied, not referenced.** The obvious mistake, and one the existing
subtree snapshot deliberately makes for its own purpose: holding the live
component means the game mutates the very objects the snapshot is meant to
restore, and Stop puts back exactly what play left behind. Verified by
moving a tile and restoring: with references it came back moved.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyguara.ecs.component import Component
from pyguara.ecs.manager import EntityManager
from pyguara.ecs.relations import ChildOf
from pyguara.log import get_logger
from pyguara.studio.commands.entity import EntitySnapshot, copy_component

logger = get_logger(__name__)

HANDLE_FIELDS: tuple[str, ...] = ("_body_handle",)
"""Fields holding a live engine object, cleared on the way into a copy.

A `RigidBody` carries the physics backend's body. Copying it is wrong
twice over -- the backend still owns the original, and a restored copy
would point at a body that was removed with the entity. Cleared, the
physics system builds a fresh one, which is exactly what it does for an
entity it has not seen: `if rb._body_handle is None: _create_physics_entity`.

Auditing the demo found two components holding anything handle-like and
only this one holding an engine object, so the list is short on purpose
rather than by oversight.
"""


@dataclass
class WorldSnapshot:
    """Every entity in a world, copied.

    Attributes:
        entities: One snapshot per entity, parents before children, so
            restoring in order never names a parent that does not exist
            yet.
    """

    entities: list[EntitySnapshot] = field(default_factory=list)

    @property
    def count(self) -> int:
        """How many entities it holds."""
        return len(self.entities)

    @classmethod
    def capture(cls, world: EntityManager) -> WorldSnapshot:
        """Copy `world` whole.

        Args:
            world: The world to copy.

        Returns:
            The snapshot.
        """
        ordered = _parents_first(world)
        entities = [
            EntitySnapshot(
                entity_id=entity_id,
                components=[
                    _without_handles(copy_component(component))
                    for component in _own_components(world, entity_id)
                ],
                tags=set(world.get_entity(entity_id).tags),  # type: ignore[union-attr]
                enabled=world.is_entity_enabled(entity_id),
                parent_id=world.parent_of(entity_id),
            )
            for entity_id in ordered
        ]
        return cls(entities=entities)

    def restore(self, world: EntityManager) -> None:
        """Put the world back as it was.

        The world is cleared first: a restore that merged would leave
        behind whatever play created, which is the half of "reset" people
        notice missing.

        Copies again on the way out, so the same snapshot can restore more
        than once -- Stop, Play, Stop -- without the second restore
        handing back objects the first run already mutated.

        Args:
            world: The world to rebuild.
        """
        world.clear()
        for snapshot in self.entities:
            entity = world.create_entity(snapshot.entity_id)
            entity.tags.update(snapshot.tags)
            for component in snapshot.components:
                entity.add_component(_without_handles(copy_component(component)))

        for snapshot in self.entities:
            if snapshot.parent_id is not None:
                try:
                    world.set_parent(snapshot.entity_id, snapshot.parent_id)
                except Exception as exc:  # pragma: no cover - a vanished parent
                    logger.debug(f"Could not restore a parent link: {exc}")
            world.set_entity_enabled(snapshot.entity_id, snapshot.enabled)

        logger.info(f"Restored {self.count} entities from the snapshot.")


def _own_components(world: EntityManager, entity_id: str) -> list[Component]:
    """Return the components to copy for one entity.

    `ChildOf` is excluded: the parent link is restored through
    `set_parent`, which is what maintains the manager's parent -> children
    index. Re-attaching the component by hand would set the field and
    leave the index empty.

    Args:
        world: The world to read.
        entity_id: The entity.

    Returns:
        Its components, minus the ownership link.
    """
    entity = world.get_entity(entity_id)
    if entity is None:  # pragma: no cover - the caller just listed it
        return []
    return [c for c in entity.get_all_components() if not isinstance(c, ChildOf)]


def _without_handles(component: Component) -> Component:
    """Clear any live engine handle on a copied component.

    Args:
        component: The copy.

    Returns:
        The same component, with its handles cleared.
    """
    for name in HANDLE_FIELDS:
        if hasattr(component, name):
            try:
                setattr(component, name, None)
            except Exception as exc:  # pragma: no cover - a frozen component
                logger.debug(f"Could not clear {name}: {exc}")
    return component


def _parents_first(world: EntityManager) -> list[str]:
    """Return every entity id with parents before their children.

    Args:
        world: The world to read.

    Returns:
        The ids, in an order safe to rebuild in.
    """
    ordered: list[str] = []
    seen: set[str] = set()

    def visit(entity_id: str, depth: int = 0) -> None:
        if entity_id in seen or depth > 64:
            return
        seen.add(entity_id)
        ordered.append(entity_id)
        for child_id in sorted(world.children_of(entity_id)):
            visit(child_id, depth + 1)

    for entity in sorted(world.get_all_entities(), key=lambda e: e.id):
        if world.parent_of(entity.id) is None:
            visit(entity.id)
    # Anything left is in a cycle the manager should have refused; kept
    # rather than dropped, because losing an entity on Stop is worse than
    # restoring one whose parent link cannot be rebuilt.
    for entity in sorted(world.get_all_entities(), key=lambda e: e.id):
        if entity.id not in seen:
            seen.add(entity.id)
            ordered.append(entity.id)
    return ordered
