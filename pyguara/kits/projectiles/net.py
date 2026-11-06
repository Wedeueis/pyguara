"""Shots over the network: each sent once, and flown by every client itself.

Imported on its own, as `pyguara.kits.projectiles.net`: the kit doesn't import it, so a
single-player game loads no networking.

    register_projectiles(schema, kinds, position=..., velocity=...)   # both sides
    ProjectileHost(projectiles, replication, app)                      # host
    ProjectileClient(projectiles, dispatcher, replication, dt)         # each client

Projectiles are not replicated in snapshots. Hundreds of bullets read every tick would
use up the snapshot budget, so the host sends each shot once, as a reliable event: who
fired it and when, its kind, origin, velocity and life. A client flies it on its own
`ProjectileSystem`, and the host alone decides what it hits. When a shot stops early, at a
target, at a wall, or because the host cleared them, the host sends where it ended, and
the client stops its copy there. One that simply runs out of life ends on its own on
both sides, so it costs nothing more. A bullet in flight costs no bandwidth at all.

Both events run on the client's delayed timeline with everything else, so a shot leaves
its shooter where the client draws the shooter, and stops at a target as the target is
hit. A client's own shots are the exception, since its own character is drawn in the
present: `ProjectileClient.fire` shows them the moment the player fires, and the host's
copy of the same shot is recognised by its `ProjectileKey` rather than shown twice. A shot
the client predicted and the host never fired is taken away, and one the host fired that
the client didn't predict appears from the network, late. Both mean prediction disagreed
about whether a skill was ready, and are counted.

On the client, an own shot stops at the first opposing target it reaches, for display:
nothing is damaged. Hits are the host's, and arrive as its game events. Other players'
shots pass through what they meet until the host says otherwise. A shot can therefore
look as though it touched a target and did nothing, which is the accepted trade.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.projectiles import Projectile, ProjectileEnd, ProjectileSystem
from pyguara.net.replication import ReplicationClient, ReplicationHost
from pyguara.net.schema import (
    Choice,
    FieldCodec,
    Int32,
    Quantised,
    ReplicationSchema,
    UInt8,
    UInt16,
)

NO_SLOT = 255
"""The slot a shot fired by no player is sent with, such as an enemy's."""

# A predicted shot the host hasn't confirmed this many ticks after the client's view
# reaches it never will be: the confirmation travels with the snapshots that view is
# drawn from.
_CONFIRM_GRACE_TICKS = 30
_MAX_INDEX = 65535
_LIFE = Quantised(step=1 / 1000, wide=True)


@dataclass(frozen=True, slots=True)
class ProjectileKey:
    """Names one shot, the same way on the host and on the client that fired it.

    Attributes:
        slot: The player who fired it, or `NO_SLOT`.
        tick: The tick it was fired on: the tick of the command that fired it.
        index: Which of that player's shots on that tick, counting from 0 in the order
            they were fired. Host and client must fire in the same order.
    """

    slot: int
    tick: int
    index: int


@dataclass
class ProjectileFired:
    """A shot leaving its origin. Sent by `ProjectileHost`, not dispatched there."""

    slot: int
    tick: int
    index: int
    kind: str
    origin: Vector2
    velocity: Vector2
    life: float
    timestamp: float = 0.0
    source: Any = None

    @property
    def key(self) -> ProjectileKey:
        """The shot's key."""
        return ProjectileKey(self.slot, self.tick, self.index)


@dataclass
class ProjectileEnded:
    """A shot stopping before its life ran out, and where."""

    slot: int
    tick: int
    index: int
    position: Vector2
    timestamp: float = 0.0
    source: Any = None

    @property
    def key(self) -> ProjectileKey:
        """The shot's key."""
        return ProjectileKey(self.slot, self.tick, self.index)


@dataclass(frozen=True, slots=True)
class NetShot:
    """A client's shot, as its projectile's payload, for drawing.

    Attributes:
        key: Which shot.
        kind: What it is, one of the kinds registered.
        predicted: Whether this client fired it and is showing it ahead of the host.
    """

    key: ProjectileKey
    kind: str
    predicted: bool


def register_projectiles(
    schema: ReplicationSchema,
    kinds: Sequence[str],
    *,
    position: FieldCodec,
    velocity: FieldCodec,
) -> None:
    """Send shots with this schema. Host and clients call it alike, in the same place.

    Args:
        schema: The replication schema.
        kinds: Every kind of shot, which a client draws from.
        position: How an origin or an end point is sent, normally the codec positions
            are replicated with.
        velocity: How a velocity is sent.
    """
    key = {"slot": UInt8(), "tick": Int32(), "index": UInt16()}
    schema.register_event(
        ProjectileFired,
        **key,
        kind=Choice(kinds),
        origin=position,
        velocity=velocity,
        life=_LIFE,
    )
    schema.register_event(ProjectileEnded, **key, position=position)


class _HasFixedTick(Protocol):
    @property
    def fixed_tick(self) -> int: ...


class _Counter:
    """Numbers each slot's shots within a tick."""

    def __init__(self) -> None:
        self._tick: int | None = None
        self._next: dict[int, int] = {}

    def take(self, slot: int, tick: int) -> int | None:
        if tick != self._tick:
            self._tick = tick
            self._next.clear()
        index = self._next.get(slot, 0)
        if index > _MAX_INDEX:
            return None
        self._next[slot] = index + 1
        return index


def _slot_number(slot: int | None) -> int:
    if slot is None:
        return NO_SLOT
    if not 0 <= slot < NO_SLOT:
        raise ValueError(f"A slot must be from 0 to {NO_SLOT - 1}")
    return slot


class ProjectileHost:
    """Fires the host's shots, and tells every client about them."""

    def __init__(
        self,
        projectiles: ProjectileSystem,
        replication: ReplicationHost,
        clock: _HasFixedTick,
    ) -> None:
        """Attach to the game's projectile system.

        Args:
            projectiles: Where shots fly and hit, as in a single-player game. Its
                `on_end` must be free: this takes it.
            replication: Sends the shots. Its schema must have `register_projectiles`.
            clock: Where ticks come from, normally the `Application`. Fire during the
                fixed update, so a shot's tick is its command's.

        Raises:
            ValueError: If `on_end` is taken, or the schema doesn't send shots.
        """
        if projectiles.on_end is not None:
            raise ValueError("The projectile system's on_end is already taken")
        if replication.schema.event_layout(ProjectileFired) is None:
            raise ValueError("The schema needs register_projectiles")
        self._projectiles = projectiles
        self._replication = replication
        self._clock = clock
        self._counter = _Counter()
        self._flying: dict[int, ProjectileKey] = {}
        projectiles.on_end = self._ended
        self.dropped = 0
        """Shots not fired: the pool was full, or one slot fired too many in a tick."""

    def close(self) -> None:
        """Stop telling clients about shots."""
        if self._projectiles.on_end == self._ended:
            self._projectiles.on_end = None
        self._flying.clear()

    def spawn(
        self,
        kind: str,
        position: Vector2,
        velocity: Vector2,
        *,
        slot: int | None = None,
        life: float = 2.0,
        **options: Any,
    ) -> Projectile | None:
        """Fire a shot, here and on every client.

        Args:
            kind: What it is, one of the kinds registered. Clients draw from this.
            position: Where it starts.
            velocity: Pixels per second.
            slot: The player who fired it, whose client may already be showing it, or
                None for a shot no player fired.
            life: Seconds until it expires.
            **options: Everything else `ProjectileSystem.spawn` takes, such as
                `hit_radius`, `team` and `payload`. Clients receive none of it.

        Returns:
            The projectile, or None if it couldn't be fired.

        Raises:
            ValueError: If `slot` is out of range.
        """
        number = _slot_number(slot)
        tick = self._clock.fixed_tick
        index = self._counter.take(number, tick)
        if index is None:
            self.dropped += 1
            return None
        projectile = self._projectiles.spawn(
            options.pop("texture", None), position, velocity, life=life, **options
        )
        if projectile is None:
            self.dropped += 1
            return None
        key = ProjectileKey(number, tick, index)
        self._flying[id(projectile)] = key
        self._replication.send_event(
            ProjectileFired(number, tick, index, kind, position, velocity, life),
            tick + 1,
        )
        return projectile

    def _ended(self, projectile: Projectile, reason: ProjectileEnd) -> None:
        key = self._flying.pop(id(projectile), None)
        if key is None or reason is ProjectileEnd.EXPIRED:
            return
        self._replication.send_event(
            ProjectileEnded(key.slot, key.tick, key.index, projectile.position),
            self._clock.fixed_tick + 1,
        )


@dataclass(slots=True)
class _Arrival:
    fired: ProjectileFired


class ProjectileClient:
    """Flies the host's shots on a client, and shows this player's own at once."""

    def __init__(
        self,
        projectiles: ProjectileSystem,
        dispatcher: EventDispatcher,
        replication: ReplicationClient,
        tick_seconds: float,
    ) -> None:
        """Attach to a display-only projectile system.

        Args:
            projectiles: Where the client's copies fly. It runs no game rules: this
                takes its `on_hit`, which damages nothing. Give it the client's walls
                as `solids` if it has them, and a spatial index of what the client
                draws if own shots should stop at targets.
            dispatcher: Where the client's `ReplicationClient` dispatches the host's
                events, through `on_event=dispatcher.dispatch`.
            replication: The client's replication, for its delayed view.
            tick_seconds: How long one tick is.
        """
        self._projectiles = projectiles
        self._dispatcher = dispatcher
        self._replication = replication
        self._tick_seconds = tick_seconds
        self._counter = _Counter()
        self._arrivals: list[_Arrival] = []
        self._shown: dict[ProjectileKey, Projectile] = {}
        self._unconfirmed: dict[ProjectileKey, Projectile] = {}
        self._confirmed: set[ProjectileKey] = set()
        self._own_slots: set[int] = set()
        self._last_render: float | None = None
        projectiles.on_hit = self._shown_hit
        dispatcher.subscribe(ProjectileFired, self._on_fired, owner=self)
        dispatcher.subscribe(ProjectileEnded, self._on_ended, owner=self)
        self.mispredicted = 0
        """Own shots shown that the host never fired."""
        self.unpredicted = 0
        """Own shots the host fired that weren't shown ahead of it."""

    def close(self) -> None:
        """Stop listening, and remove every shot."""
        self._dispatcher.clear_subscribers(owner=self)
        self._projectiles.clear()
        self._arrivals.clear()
        self._shown.clear()
        self._unconfirmed.clear()
        self._confirmed.clear()
        self._own_slots.clear()

    def fire(
        self,
        slot: int,
        tick: int,
        kind: str,
        position: Vector2,
        velocity: Vector2,
        *,
        life: float = 2.0,
        **options: Any,
    ) -> Projectile | None:
        """Show one of this player's own shots at once, before the host confirms it.

        Call it where the host's game calls `ProjectileHost.spawn` for the same shot,
        from the predicted step of the same command, so both number it alike.

        Args:
            slot: This player's slot.
            tick: The tick being predicted, `PredictionClient.tick` read before
                stepping.
            kind: What it is.
            position: Where it starts.
            velocity: Pixels per second.
            life: Seconds until it expires.
            **options: Everything else `ProjectileSystem.spawn` takes. `hit_radius`
                and `team` decide where it stops for display.

        Returns:
            The projectile, or None if it wasn't shown, including when this same shot
            is already showing, as it is when prediction replays a tick.
        """
        index = self._counter.take(_slot_number(slot), tick)
        if index is None:
            return None
        self._own_slots.add(slot)
        key = ProjectileKey(slot, tick, index)
        if key in self._unconfirmed or key in self._confirmed:
            return None
        options.pop("payload", None)
        projectile = self._projectiles.spawn(
            options.pop("texture", None),
            position,
            velocity,
            life=life,
            payload=NetShot(key, kind, predicted=True),
            **options,
        )
        if projectile is not None:
            self._unconfirmed[key] = projectile
            self._shown[key] = projectile
        return projectile

    def update(self, dt: float) -> None:
        """Fly every shot. Call once a frame, after the frame's network update.

        Shots move with the delayed view rather than the frame, so they keep pace
        with the interpolated world even as that view's clock is corrected.

        Args:
            dt: Seconds since the last call, used until the delayed view starts.
        """
        render = self._replication.render_tick
        step = dt
        if render is not None and self._last_render is not None:
            # On the delayed view's clock, which speeds and slows to keep its lag, so
            # a shot stays where the world it flies through is drawn.
            step = max(0.0, (render - self._last_render) * self._tick_seconds)
        self._last_render = render
        self._projectiles.update(step)
        for arrival in self._arrivals:
            self._show(arrival.fired, render)
        self._arrivals.clear()
        self._forget(render)

    def _on_fired(self, fired: ProjectileFired) -> None:
        key = fired.key
        if key in self._unconfirmed:
            del self._unconfirmed[key]
            self._confirmed.add(key)
            return
        if key in self._confirmed:
            return
        self._arrivals.append(_Arrival(fired))

    def _show(self, fired: ProjectileFired, render: float | None) -> None:
        late = 0.0
        if render is not None:
            late = max(0.0, (render - fired.tick) * self._tick_seconds)
        if late >= fired.life:
            return
        if fired.slot in self._own_slots:
            self.unpredicted += 1
        projectile = self._projectiles.spawn(
            None,
            fired.origin + fired.velocity * late,
            fired.velocity,
            life=fired.life - late,
            payload=NetShot(fired.key, fired.kind, predicted=False),
        )
        if projectile is not None:
            self._shown[fired.key] = projectile

    def _on_ended(self, ended: ProjectileEnded) -> None:
        key = ended.key
        projectile = self._shown.pop(key, None)
        if projectile is None or not self._is(projectile, key):
            return
        projectile.position = ended.position
        projectile.active = False

    def _forget(self, render: float | None) -> None:
        for key, projectile in list(self._shown.items()):
            if not self._is(projectile, key):
                del self._shown[key]
        if render is None:
            return
        horizon = render - _CONFIRM_GRACE_TICKS
        for key, projectile in list(self._unconfirmed.items()):
            if key.tick + 1 < horizon:
                del self._unconfirmed[key]
                self.mispredicted += 1
                if self._is(projectile, key):
                    projectile.active = False
        self._confirmed = {key for key in self._confirmed if key.tick + 1 >= horizon}

    @staticmethod
    def _is(projectile: Projectile, key: ProjectileKey) -> bool:
        payload = projectile.payload
        return projectile.active and isinstance(payload, NetShot) and payload.key == key

    @staticmethod
    def _shown_hit(projectile: Projectile, target: Entity) -> bool:
        payload = projectile.payload
        return isinstance(payload, NetShot) and payload.predicted
