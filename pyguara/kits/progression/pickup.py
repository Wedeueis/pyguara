"""The XP-orb magnet: pickups that fly to whoever is close enough.

**Not a physics interaction.** A magnet is a radius query and a velocity,
with no collider, no body and no contact resolution -- an orb passes
through walls on its way to the player, which is what the genre wants and
what keeps a thousand of them affordable. A game that needs pickups to
respect geometry gives them a `Collider` and does not use this.

The second consumer of the shared `SpatialHash` (`kits/projectiles` was
the first), which is the point: attraction is a "what is near me" question
and that index already answers it in one cell walk instead of a scan over
every orb on the field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.component import StrictComponent
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.progression.events import PickupCollected


@dataclass(slots=True)
class Magnet(StrictComponent):
    """Attracts nearby `Attracted` entities toward this one.

    Attributes:
        radius: How far the pull reaches, in world units. A run that grows
            its pickup range grows this.
        speed: Starting speed an attracted entity is pulled at.
        acceleration: How much that speed grows per second while attracted,
            so an orb snaps in rather than drifting. 0 pulls at a constant
            speed.
        mask: Spatial-index bits this magnet queries with.
    """

    radius: float = 120.0
    speed: float = 120.0
    acceleration: float = 600.0
    mask: int = 0xFFFFFFFF

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a
        zero-argument `super()` still resolves against the discarded
        original, raising TypeError on every instantiation.
        """
        StrictComponent.__init__(self)


@dataclass(slots=True)
class Attracted(StrictComponent):
    """Marks an entity a `Magnet` can pull in, and what it is worth.

    Attributes:
        payload: What collecting this yields. Opaque to the kit, exactly as
            `Upgrade.apply` is -- an experience amount, a currency, a key
            item. It travels out on `PickupCollected` and the game decides
            what it means.
        collect_radius: How close the magnet must get before this counts as
            collected.
        active: Whether this can be attracted at all. A just-dropped orb
            can spend a moment inert so it does not fly back into the
            player who dropped it.
        current_speed: Live pull speed, grown by the magnet's acceleration
            while attracted. Reset when nothing is pulling.
    """

    payload: Any = None
    collect_radius: float = 12.0
    active: bool = True
    current_speed: float = 0.0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a
        zero-argument `super()` still resolves against the discarded
        original, raising TypeError on every instantiation.
        """
        StrictComponent.__init__(self)


class MagnetSystem:
    """Pulls `Attracted` entities toward nearby `Magnet`s and collects them.

    Queries the shared `SpatialHash` around each magnet rather than walking
    every pickup on the field. Entities are expected to be tracked in it
    the usual way (`pyguara.spatial.SpatialTracked` + `SpatialIndexSystem`);
    this system never inserts into it itself.

    Collection dispatches `PickupCollected` and marks the pickup inactive.
    Destroying the entity is left to the game, which may want to pool it,
    play something on it, or fade it out first.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        dispatcher: EventDispatcher,
        spatial_index: SpatialHash[str],
    ) -> None:
        """Store collaborators.

        Args:
            entity_manager: Source of magnets, and of candidates by id.
            dispatcher: Where `PickupCollected` is dispatched.
            spatial_index: Queried around each magnet for candidates.
        """
        self._entity_manager = entity_manager
        self._dispatcher = dispatcher
        self._spatial_index = spatial_index

    def update(self, dt: float) -> None:
        """Pull every attracted entity in range of a magnet, and collect.

        Args:
            dt: Seconds since the last update.
        """
        for entity in self._entity_manager.get_entities_with(Magnet, Transform):
            magnet = entity.get_component(Magnet)
            magnet_position = entity.get_component(Transform).position

            for candidate_id in self._spatial_index.query_radius(
                magnet_position, magnet.radius, magnet.mask
            ):
                candidate = self._entity_manager.get_entity(candidate_id)
                if candidate is None or candidate.id == entity.id:
                    continue
                if not candidate.has_component(Attracted):
                    continue

                pickup = candidate.get_component(Attracted)
                if not pickup.active:
                    continue

                candidate_transform = candidate.get_component(Transform)
                self._pull(candidate_transform, magnet_position, pickup, magnet, dt)

                offset = magnet_position - candidate_transform.position
                # Squared, per `Vector2.sqr_magnitude`'s own advice: this
                # runs once per pickup in range, per magnet, per frame.
                if offset.sqr_magnitude <= pickup.collect_radius**2:
                    pickup.active = False
                    pickup.current_speed = 0.0
                    self._dispatcher.dispatch(
                        PickupCollected(
                            pickup=candidate.id,
                            collector=entity.id,
                            payload=pickup.payload,
                        )
                    )

    def _pull(
        self,
        transform: Transform,
        magnet_position: Vector2,
        pickup: Attracted,
        magnet: Magnet,
        dt: float,
    ) -> None:
        """Move `transform` one step toward `magnet_position`.

        Position is written directly rather than through a velocity: these
        are not physics bodies, and an orb arriving by integration would
        need a force model and a way to be stopped by the geometry it is
        meant to pass through.

        A pickup is expected to be unparented, so its local position is its
        world position; a parented orb's placement is its parent's
        business, not a magnet's.
        """
        offset = magnet_position - transform.position
        distance = offset.magnitude
        if distance <= 0.0:
            return

        if pickup.current_speed <= 0.0:
            pickup.current_speed = magnet.speed
        pickup.current_speed += magnet.acceleration * dt

        # Never overshoot: an orb one frame from the magnet should land on
        # it, not skip past and get pulled back next frame.
        step = min(pickup.current_speed * dt, distance)
        transform.position = transform.position + offset * (step / distance)
