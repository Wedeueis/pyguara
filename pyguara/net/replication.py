"""Keeping every client's world matching the host's.

The host owns the simulation. Each snapshot it reads the replicated fields of every
tracked entity and sends them, and clients draw what they receive, about 100 ms behind
so there is always a newer snapshot to interpolate toward.

Snapshots are complete states, so a lost one costs nothing and the next corrects any
error. That makes a client's world converge on its own after any loss, which is the
property this module exists for. The ways a client could stay wrong instead are each
handled here on purpose:

- **A snapshot names an entity whose spawn hasn't arrived.** The record is dropped and
  no entity is invented. The next snapshot repeats it.
- **An old snapshot arrives late.** Each entity keeps the newest tick it has seen, and
  anything older is dropped, so a dead enemy's stale record can't move a new one.
- **A despawn overtakes the motion.** Spawns and despawns run on the same delayed
  timeline as interpolation, in order.
- **A network id gets reused.** Freed ids wait out a quarantine far longer than any peer
  can lag and still be connected.
- **The two sides disagree about the layout.** The host sends a fingerprint of its
  schema, and a client that differs stops applying anything and says so.

Game events registered on the schema (`register_event`) travel the same way: reliably,
in order with spawns and despawns, and applied on the same delayed timeline, so a kill
lands while the enemy is still there and a client's screen never shows a hit before the
snapshot it belongs to. `EventRelay` sends a dispatcher's events as they happen.

`notify_component_changed` is not used: no movement system calls it, which Phase 0
measured, so a snapshot reads the fields directly.

Replication's reliable messages share `Channel.EVENTS` with the game's, and their first
byte is at or above `FIRST_RESERVED_KIND`. A game's own messages use lower values.
"""

from __future__ import annotations

import bisect
import struct
import zlib
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pyguara.ecs.component import StrictComponent
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.log import get_logger
from pyguara.net.schema import ComponentSchema, EventLayout, ReplicationSchema
from pyguara.net.transport import Channel

logger = get_logger(__name__)

FIRST_RESERVED_KIND = 0xE0

_SNAPSHOT = 0xE1
_SPAWN = 0xE2
_DESPAWN = 0xE3
_HELLO = 0xE4
_DIGEST = 0xE5
_EVENT = 0xE6

_TICK_HEADER = struct.Struct("<BI")
_RECORD_HEADER = struct.Struct("<HH")
_SPAWN_HEADER = struct.Struct("<BIHBB")
_DESPAWN_MESSAGE = struct.Struct("<BIH")
_HELLO_MESSAGE = struct.Struct("<BI")
_DIGEST_MESSAGE = struct.Struct("<BIII")
_EVENT_HEADER = struct.Struct("<BIB")
_MASK = struct.Struct("<H")
_SPAWN_FLAG_CONTROLLED = 1

_MAX_ID = 65535
_MAX_PREFAB_NAME_BYTES = 64
# Keep a message to one datagram: a sliced unreliable message is lost whole if any
# slice is.
_MAX_MESSAGE_BYTES = 1100
_ID_QUARANTINE_TICKS = 30 * 60
_HISTORY = 16
_MAX_OUTBOX = 8192
_SNAP_RENDER_TICKS = 30.0
_CLOCK_CORRECTION_PER_SECOND = 2.0


@dataclass(slots=True)
class Replicated(StrictComponent):
    """Marks an entity for the host to replicate.

    Attributes:
        prefab: The name clients create it from, through their spawners. At most 64
            bytes: one that can't be sent is refused and counted in `unreplicated`.
        owner: The player slot that alone may see it, or None for everyone. Per-player
            drops use this.
        controller: The player slot whose character this is. Only that client is told,
            and it predicts the entity rather than drawing it from snapshots. Set it
            before the entity's first snapshot: a later change isn't sent.
    """

    prefab: str = ""
    owner: int | None = None
    controller: int | None = None

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips."""
        StrictComponent.__init__(self)


@dataclass(slots=True)
class _Tracked:
    net_id: int
    entity: Entity
    replicated: Replicated
    # Held rather than looked up, since this runs per entity per snapshot, and
    # rebuilt when a component of a replicated type is added or removed.
    parts: list[tuple[ComponentSchema, Any]]
    mask: int
    record: bytes = b""
    announced: bool = False


@dataclass(slots=True)
class _Peer:
    peer: int
    slot: int
    outbox: deque[bytes]
    cursor: int = 0
    events_sent: int = 0


class ReplicationHost:
    """The host's side: decides what each client hears.

    Attributes:
        dropped_snapshots: Unreliable messages the transport would not accept.
        skipped_records: Records left out of a snapshot by the byte budget. They go
            first in the next one, so nothing starves.
        unreplicated: Entities marked `Replicated` that can't be: 65536 ids are live, or
            the prefab name can't be sent.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        schema: ReplicationSchema,
        send: Callable[[int, Channel, bytes], bool],
        snapshot_interval_ticks: int = 3,
        max_snapshot_bytes: int = 16_000,
        digest_every: int = 0,
        on_backlog: Callable[[int], object] | None = None,
    ) -> None:
        """Start tracking.

        Args:
            entity_manager: The world to replicate.
            schema: What crosses the wire.
            send: Sends a message to a peer, returning False if it was not accepted.
            snapshot_interval_ticks: Fixed ticks per snapshot. 3 is 20 Hz at 60 Hz.
            max_snapshot_bytes: Budget per client per snapshot. At 20 Hz, the default
                is 2.6 Mbit/s for each.
            digest_every: Send a state hash every this many snapshots, so a client can
                check it agrees. 0 is off. For debugging and tests.
            on_backlog: Called with a peer whose reliable backlog has outgrown the
                limit. It can't keep up, and should be removed.
        """
        self._manager = entity_manager
        self._schema = schema
        self._send = send
        self._interval = snapshot_interval_ticks
        self._budget = max_snapshot_bytes
        self._digest_every = digest_every
        self._on_backlog = on_backlog
        self._peers: dict[int, _Peer] = {}
        self._tracked: dict[str, _Tracked] = {}
        self._new: list[_Tracked] = []
        self._next_id = 0
        self._quarantine: deque[tuple[int, int]] = deque()
        self._free: deque[int] = deque()
        self._tick = 0
        self._last_snapshot_tick: int | None = None
        self._snapshots = 0
        self.dropped_snapshots = 0
        self.skipped_records = 0
        self.unreplicated = 0

        entity_manager.subscribe_entity_removed(self._on_entity_removed)
        entity_manager.subscribe_component_added(Replicated, self._on_replicated_added)
        entity_manager.subscribe_component_removed(
            Replicated, self._on_replicated_removed
        )
        for component in schema.components:
            entity_manager.subscribe_component_added(
                component.component_type, self._on_part_changed
            )
            entity_manager.subscribe_component_removed(
                component.component_type, self._on_part_changed
            )
        for entity in entity_manager.get_entities_with(Replicated):
            self._track(entity, entity.get_component(Replicated))

    @property
    def schema(self) -> ReplicationSchema:
        """What crosses the wire."""
        return self._schema

    @property
    def tracked_count(self) -> int:
        """How many entities are being replicated."""
        return len(self._tracked)

    def saturated(self) -> int:
        """Return how many values have not fit their field, across the schema."""
        return sum(
            component.saturated() for component in self._schema.components
        ) + sum(event.saturated() for event in self._schema.events)

    def net_id_of(self, entity_id: str) -> int | None:
        """Return an entity's network id, or None if it isn't replicated."""
        tracked = self._tracked.get(entity_id)
        return None if tracked is None else tracked.net_id

    def send_event(self, event: Any, tick: int, slot: int | None = None) -> None:
        """Send a game event to clients, reliably and in order with spawns.

        Anything spawned before this call is announced first, so an event can name
        an entity created in the same tick.

        Args:
            event: An event whose type is registered with `register_event`.
            tick: The first tick whose state includes it. A client applies it when
                its delayed view reaches that tick.
            slot: The one player to tell, or None for everyone.

        Raises:
            ValueError: If its type isn't registered.
        """
        layout = self._schema.event_layout(type(event))
        if layout is None:
            raise ValueError(
                f"{type(event).__name__} isn't registered with register_event"
            )
        self._announce_new()
        message = _EVENT_HEADER.pack(_EVENT, tick, layout.index) + layout.encode(
            event, self.net_id_of
        )
        for peer in self._peers.values():
            if slot is None or peer.slot == slot:
                self._queue(peer, message, True)

    def add_peer(self, peer: int, slot: int) -> None:
        """Start replicating to a peer, telling it about everything it can see.

        Args:
            peer: The connection.
            slot: Its player slot, which decides what it may see.
        """
        state = _Peer(peer, slot, deque())
        self._peers[peer] = state
        self._queue(
            state, _HELLO_MESSAGE.pack(_HELLO, self._schema.fingerprint()), False
        )
        for tracked in self._tracked.values():
            if tracked.announced and self._visible(tracked, state):
                self._refresh_record(tracked)
                self._queue(state, self._spawn_message(tracked, state), True)

    def remove_peer(self, peer: int) -> None:
        """Stop replicating to a peer."""
        self._peers.pop(peer, None)

    def step(self, tick: int) -> None:
        """Send what is due. Call once a frame, after the simulation.

        Args:
            tick: The fixed tick the world is at.
        """
        self._tick = tick
        self._release_quarantine()
        self._announce_new()
        due = (
            self._last_snapshot_tick is None
            or tick - self._last_snapshot_tick >= self._interval
        )
        if due and self._peers:
            self._last_snapshot_tick = tick
            self._send_snapshots(tick)
        self._drain_outboxes()

    def _visible(self, tracked: _Tracked, peer: _Peer) -> bool:
        owner = tracked.replicated.owner
        return owner is None or owner == peer.slot

    def _parts_of(
        self, entity: Entity
    ) -> tuple[list[tuple[ComponentSchema, Any]], int]:
        parts: list[tuple[ComponentSchema, Any]] = []
        mask = 0
        for schema in self._schema.components:
            if entity.has_component(schema.component_type):
                parts.append((schema, entity.get_component(schema.component_type)))
                mask |= 1 << schema.index
        return parts, mask

    def _allocate_id(self) -> int | None:
        if self._free:
            return self._free.popleft()
        if self._next_id <= _MAX_ID:
            self._next_id += 1
            return self._next_id - 1
        return None

    def _release_quarantine(self) -> None:
        while self._quarantine and self._quarantine[0][0] <= self._tick:
            self._free.append(self._quarantine.popleft()[1])

    def _track(self, entity: Entity, replicated: Replicated) -> None:
        if entity.id in self._tracked:
            return
        if not 0 < len(replicated.prefab.encode()) <= _MAX_PREFAB_NAME_BYTES:
            self.unreplicated += 1
            logger.error("Entity %s has an unsendable prefab name", entity.id)
            return
        net_id = self._allocate_id()
        if net_id is None:
            self.unreplicated += 1
            logger.error("Out of network ids: entity %s won't replicate", entity.id)
            return
        parts, mask = self._parts_of(entity)
        tracked = _Tracked(net_id, entity, replicated, parts, mask)
        self._tracked[entity.id] = tracked
        self._new.append(tracked)

    def _on_replicated_added(self, entity: Entity, component: Any) -> None:
        self._track(entity, component)

    def _on_part_changed(self, entity: Entity, component: Any) -> None:
        tracked = self._tracked.get(entity.id)
        if tracked is not None:
            tracked.parts, tracked.mask = self._parts_of(entity)

    def _on_replicated_removed(self, entity: Entity, component: Any) -> None:
        self._forget(entity)

    def _on_entity_removed(self, entity: Entity) -> None:
        self._forget(entity)

    def _forget(self, entity: Entity) -> None:
        tracked = self._tracked.pop(entity.id, None)
        if tracked is None:
            return
        self._quarantine.append((self._tick + _ID_QUARANTINE_TICKS, tracked.net_id))
        if not tracked.announced:
            # Spawned and removed between snapshots: no client ever heard of it.
            self._new.remove(tracked)
            return
        message = _DESPAWN_MESSAGE.pack(_DESPAWN, self._tick, tracked.net_id)
        for peer in self._peers.values():
            if self._visible(tracked, peer):
                self._queue(peer, message, True)

    def _refresh_record(self, tracked: _Tracked) -> None:
        tracked.record = b"".join(
            [schema.encode(component) for schema, component in tracked.parts]
        )

    def _spawn_message(self, tracked: _Tracked, peer: _Peer) -> bytes:
        name = tracked.replicated.prefab.encode()
        flags = (
            _SPAWN_FLAG_CONTROLLED if tracked.replicated.controller == peer.slot else 0
        )
        return (
            _SPAWN_HEADER.pack(_SPAWN, self._tick, tracked.net_id, len(name), flags)
            + name
            + _MASK.pack(tracked.mask)
            + tracked.record
        )

    def _announce_new(self) -> None:
        for tracked in self._new:
            tracked.announced = True
            self._refresh_record(tracked)
            for peer in self._peers.values():
                if self._visible(tracked, peer):
                    self._queue(peer, self._spawn_message(tracked, peer), True)
        self._new.clear()

    def _queue(self, peer: _Peer, message: bytes, counted: bool) -> None:
        if counted:
            peer.events_sent += 1
        peer.outbox.append(message)

    def _drain_outboxes(self) -> None:
        for peer in list(self._peers.values()):
            outbox = peer.outbox
            while outbox and self._send(peer.peer, Channel.EVENTS, outbox[0]):
                outbox.popleft()
            if len(outbox) > _MAX_OUTBOX and self._on_backlog is not None:
                self._on_backlog(peer.peer)

    def _send_snapshots(self, tick: int) -> None:
        tracked_all = list(self._tracked.values())
        for tracked in tracked_all:
            tracked.record = b"".join(
                [schema.encode(component) for schema, component in tracked.parts]
            )
        self._snapshots += 1
        digest_due = (
            self._digest_every > 0 and self._snapshots % self._digest_every == 0
        )
        header = _TICK_HEADER.pack(_SNAPSHOT, tick)
        for peer in self._peers.values():
            visible = [t for t in tracked_all if self._visible(t, peer)]
            self._send_one_snapshot(peer, visible, header)
            if digest_due:
                self._send_digest(peer, visible, tick)

    def _send_one_snapshot(
        self, peer: _Peer, visible: list[_Tracked], header: bytes
    ) -> None:
        if not visible:
            return
        start = peer.cursor % len(visible)
        rotated = visible[start:] + visible[:start]
        parts = [header]
        size = len(header)
        total = 0
        sent = 0
        record_header = _RECORD_HEADER
        for tracked in rotated:
            record = tracked.record
            length = 4 + len(record)
            if total + length > self._budget:
                break
            if size + length > _MAX_MESSAGE_BYTES:
                self._send_unreliable(peer, b"".join(parts))
                parts = [header]
                size = len(header)
            parts.append(record_header.pack(tracked.net_id, tracked.mask))
            parts.append(record)
            size += length
            total += length
            sent += 1
        if len(parts) > 1:
            self._send_unreliable(peer, b"".join(parts))
        self.skipped_records += len(visible) - sent
        peer.cursor = (start + sent) % len(visible) if sent < len(visible) else 0

    def _send_unreliable(self, peer: _Peer, message: bytes) -> None:
        if not self._send(peer.peer, Channel.SNAPSHOT, message):
            self.dropped_snapshots += 1

    def _send_digest(self, peer: _Peer, visible: list[_Tracked], tick: int) -> None:
        crc = _state_crc((t.net_id, t.record) for t in visible)
        message = _DIGEST_MESSAGE.pack(_DIGEST, tick, peer.events_sent, crc)
        self._send_unreliable(peer, message)


def _state_crc(records: Any) -> int:
    crc = 0
    for net_id, record in sorted(records):
        crc = zlib.crc32(_MASK.pack(net_id) + record, crc)
    return crc


@dataclass(slots=True)
class _Sample:
    tick: int
    record: bytes
    values: dict[int, tuple[Any, ...]]


@dataclass(slots=True)
class _Remote:
    net_id: int
    prefab: str
    spawn_tick: int
    history: list[_Sample]
    entity: Entity | None = None
    parts: dict[int, tuple[ComponentSchema, Any]] | None = None
    applied: bytes | None = None
    gone: bool = False
    controlled: bool = False


@dataclass(slots=True)
class _Arrived:
    layout: EventLayout
    values: tuple[Any, ...]


class ReplicationClient:
    """A client's side: applies what the host sent, on a delayed timeline.

    Spawners are named in advance, so a name from the network can only ever choose
    among them. It is never a path to load.

    Attributes:
        malformed: Messages that could not be read, which are dropped.
        stale_records: Records older than one already seen, which are dropped.
        unknown_records: Records for an entity with no spawn yet, which are dropped.
        digests_matched: State hashes that agreed with the host.
        digests_mismatched: State hashes that did not. Above 0 is a real desync.
        digests_skipped: Hashes that could not be compared, because of loss.
        failed: Why this client has stopped applying anything, or None.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        schema: ReplicationSchema,
        spawners: Mapping[str, Callable[[], Entity]],
        interpolation_ticks: float = 6.0,
        tick_rate: float = 60.0,
        predicted_components: tuple[type, ...] = (),
        on_controlled: Callable[[Entity | None], object] | None = None,
        on_event: Callable[[Any], object] | None = None,
    ) -> None:
        """Start empty.

        Args:
            entity_manager: Where remote entities are created.
            schema: What crosses the wire. Must match the host's.
            spawners: Name to a function creating that entity here.
            interpolation_ticks: How far behind the newest snapshot to draw. 6 is 100
                ms at 60 Hz, which rides out one lost 20 Hz snapshot.
            tick_rate: The host's fixed updates per second.
            predicted_components: What prediction writes on this player's own character,
                which snapshots must leave alone. Its other components still update, so
                health can keep arriving.
            on_controlled: Called with this player's own character when it appears, and
                with None when it goes.
            on_event: Called with each game event the host sends, when the delayed
                view reaches its tick, with entities named by their ids here. Usually
                a dispatcher's `dispatch`. Without it, events are read and dropped.
        """
        self._manager = entity_manager
        self._schema = schema
        self._spawners = spawners
        self._predicted = predicted_components
        self._on_controlled = on_controlled
        self._on_event = on_event
        self._delay = interpolation_ticks
        self._rate = tick_rate
        self._remotes: dict[int, _Remote] = {}
        self._active: dict[int, _Remote] = {}
        self._timeline: deque[tuple[int, _Remote | _Arrived, bool]] = deque()
        self._newest_tick: int | None = None
        self._render_tick: float | None = None
        self._events_received = 0
        self._by_index = {c.index: c for c in schema.components}
        self.malformed = 0
        self.stale_records = 0
        self.unknown_records = 0
        self.digests_matched = 0
        self.digests_mismatched = 0
        self.digests_skipped = 0
        self.failed: str | None = None

    @property
    def render_tick(self) -> float | None:
        """The host tick currently being drawn, or None before anything has arrived."""
        return self._render_tick

    def entities(self) -> dict[int, Entity]:
        """Return the remote entities currently in the world, by network id."""
        return {
            net_id: remote.entity
            for net_id, remote in self._active.items()
            if remote.entity is not None
        }

    def latest_records(self) -> dict[int, bytes]:
        """Return the newest state received per known entity, as sent. For tests."""
        return {
            net_id: remote.history[-1].record
            for net_id, remote in self._remotes.items()
            if remote.history
        }

    def handle_message(self, channel: int, data: bytes) -> bool:
        """Take a message from the host. Hostile bytes are dropped, never raised.

        Args:
            channel: The channel it came on.
            data: The message.

        Returns:
            True if it was replication's, False if it is for the game.
        """
        if not data or data[0] < FIRST_RESERVED_KIND:
            return False
        if self.failed is not None:
            return True
        try:
            self._dispatch(channel, data)
        except (struct.error, ValueError, IndexError, UnicodeDecodeError):
            self.malformed += 1
        return True

    def _dispatch(self, channel: int, data: bytes) -> None:
        kind = data[0]
        if channel == Channel.SNAPSHOT:
            if kind == _SNAPSHOT:
                self._on_snapshot(data)
            elif kind == _DIGEST:
                self._on_digest(data)
            else:
                self.malformed += 1
        elif channel == Channel.EVENTS:
            if kind == _SPAWN:
                self._on_spawn(data)
            elif kind == _DESPAWN:
                self._on_despawn(data)
            elif kind == _HELLO:
                self._on_hello(data)
            elif kind == _EVENT:
                self._on_event_message(data)
            else:
                self.malformed += 1
        else:
            self.malformed += 1

    def _on_hello(self, data: bytes) -> None:
        _, theirs = _HELLO_MESSAGE.unpack(data)
        ours = self._schema.fingerprint()
        if theirs != ours:
            self.failed = f"The host replicates a different schema: {theirs:08x}, ours {ours:08x}."
            logger.error(self.failed)

    def _see_tick(self, tick: int) -> None:
        if self._newest_tick is None or tick > self._newest_tick:
            self._newest_tick = tick
        if self._render_tick is None:
            self._render_tick = tick - self._delay

    def _decode_record(
        self, data: bytes, offset: int, mask: int
    ) -> tuple[dict[int, tuple[Any, ...]], int]:
        """Read one record's payload.

        Raises:
            ValueError: If the mask is invalid, it does not fit, or a value is bad.
        """
        size = self._schema.payload_size(mask)
        if size is None or offset + size > len(data):
            raise ValueError("A record does not fit its message")
        values: dict[int, tuple[Any, ...]] = {}
        position = offset
        for component in self._schema.components:
            if mask >> component.index & 1:
                values[component.index] = component.decode(data, position)
                position += component.size
        return values, position

    def _on_snapshot(self, data: bytes) -> None:
        _, tick = _TICK_HEADER.unpack_from(data, 0)
        self._see_tick(tick)
        offset = _TICK_HEADER.size
        end = len(data)
        while offset < end:
            net_id, mask = _RECORD_HEADER.unpack_from(data, offset)
            offset += _RECORD_HEADER.size
            start = offset
            values, offset = self._decode_record(data, offset, mask)
            remote = self._remotes.get(net_id)
            if remote is None:
                self.unknown_records += 1
                continue
            self._add_sample(remote, tick, data[start:offset], values)

    def _add_sample(
        self,
        remote: _Remote,
        tick: int,
        record: bytes,
        values: dict[int, tuple[Any, ...]],
    ) -> None:
        history = remote.history
        if tick < remote.spawn_tick or (history and tick <= history[-1].tick):
            self.stale_records += 1
            return
        history.append(_Sample(tick, record, values))
        if len(history) > _HISTORY:
            del history[0]

    def _on_spawn(self, data: bytes) -> None:
        _, tick, net_id, name_length, flags = _SPAWN_HEADER.unpack_from(data, 0)
        if flags & ~_SPAWN_FLAG_CONTROLLED:
            raise ValueError("A spawn has unknown flags")
        offset = _SPAWN_HEADER.size
        name = data[offset : offset + name_length]
        if len(name) != name_length:
            raise ValueError("A spawn's name does not fit its message")
        prefab = name.decode("utf-8")
        offset += name_length
        (mask,) = _MASK.unpack_from(data, offset)
        offset += _MASK.size
        values, end = self._decode_record(data, offset, mask)
        if end != len(data):
            raise ValueError("A spawn has trailing bytes")
        self._events_received += 1
        self._see_tick(tick)
        remote = _Remote(
            net_id,
            prefab,
            tick,
            [_Sample(tick, data[offset:end], values)],
            controlled=bool(flags & _SPAWN_FLAG_CONTROLLED),
        )
        self._remotes[net_id] = remote
        self._timeline.append((tick, remote, True))

    def _on_despawn(self, data: bytes) -> None:
        _, tick, net_id = _DESPAWN_MESSAGE.unpack(data)
        self._events_received += 1
        self._see_tick(tick)
        remote = self._remotes.pop(net_id, None)
        if remote is None:
            self.unknown_records += 1
            return
        self._timeline.append((tick, remote, False))

    def _on_event_message(self, data: bytes) -> None:
        _, tick, index = _EVENT_HEADER.unpack_from(data, 0)
        if index >= len(self._schema.events):
            raise ValueError("No such event")
        layout = self._schema.events[index]
        values = layout.decode(data, _EVENT_HEADER.size)
        self._events_received += 1
        self._see_tick(tick)
        self._timeline.append((tick, _Arrived(layout, values), False))

    def _on_digest(self, data: bytes) -> None:
        _, tick, events_sent, crc = _DIGEST_MESSAGE.unpack(data)
        comparable = events_sent == self._events_received and all(
            remote.history and remote.history[-1].tick == tick
            for remote in self._remotes.values()
        )
        if not comparable:
            self.digests_skipped += 1
            return
        ours = _state_crc(
            (net_id, remote.history[-1].record)
            for net_id, remote in self._remotes.items()
        )
        if ours == crc:
            self.digests_matched += 1
        else:
            self.digests_mismatched += 1
            logger.error("State differs from the host's at tick %d", tick)

    def update(self, dt: float) -> None:
        """Advance the timeline and write interpolated state. Call once a frame.

        Args:
            dt: Seconds since the last call.
        """
        if self._render_tick is None or self._newest_tick is None:
            return
        self._advance_clock(dt)
        self._run_timeline()
        render = self._render_tick
        for remote in self._active.values():
            self._apply_interpolated(remote, render)

    def _advance_clock(self, dt: float) -> None:
        assert self._render_tick is not None and self._newest_tick is not None
        previous = self._render_tick
        advanced = previous + dt * self._rate
        error = (self._newest_tick - self._delay) - advanced
        if abs(error) > _SNAP_RENDER_TICKS:
            self._render_tick = self._newest_tick - self._delay
            return
        correction = error * min(1.0, dt * _CLOCK_CORRECTION_PER_SECOND)
        # Never backwards: time reversing would replay motion.
        self._render_tick = max(previous, advanced + correction)

    def _run_timeline(self) -> None:
        render = self._render_tick
        assert render is not None
        timeline = self._timeline
        while timeline and timeline[0][0] <= render:
            _, item, is_spawn = timeline.popleft()
            if isinstance(item, _Arrived):
                self._apply_event(item)
            elif is_spawn:
                self._create(item)
            else:
                self._destroy(item)

    def _entity_of(self, net_id: int) -> str | None:
        remote = self._active.get(net_id)
        if remote is None or remote.entity is None:
            return None
        return remote.entity.id

    def _apply_event(self, arrived: _Arrived) -> None:
        if self._on_event is None:
            return
        try:
            event = arrived.layout.build(arrived.values, self._entity_of)
        except Exception:  # noqa: BLE001 - a host's values must not end the frame
            self.malformed += 1
            logger.error(
                "Could not build a %s from the host's values",
                arrived.layout.event_type.__name__,
                exc_info=True,
            )
            return
        self._on_event(event)

    def _create(self, remote: _Remote) -> None:
        if remote.gone:
            return
        spawner = self._spawners.get(remote.prefab)
        if spawner is None:
            self.malformed += 1
            logger.error("No spawner named %r", remote.prefab[:64])
            self._remotes.pop(remote.net_id, None)
            return
        try:
            entity = spawner()
        except Exception:  # noqa: BLE001 - a spawner failing must not end the frame
            self.malformed += 1
            logger.error("Spawner %r failed", remote.prefab, exc_info=True)
            self._remotes.pop(remote.net_id, None)
            return
        remote.entity = entity
        remote.parts = {}
        for schema in self._schema.components:
            if entity.has_component(schema.component_type):
                remote.parts[schema.index] = (
                    schema,
                    entity.get_component(schema.component_type),
                )
        self._active[remote.net_id] = remote
        if remote.controlled and self._on_controlled is not None:
            # Where it starts comes from the spawn. After that, prediction decides.
            self._write(remote.parts, remote.history[0].values)
            for index, (schema, _) in list(remote.parts.items()):
                if schema.component_type in self._predicted:
                    del remote.parts[index]
            self._on_controlled(entity)

    def _destroy(self, remote: _Remote) -> None:
        remote.gone = True
        if self._active.get(remote.net_id) is remote:
            del self._active[remote.net_id]
        if remote.entity is not None:
            if remote.controlled and self._on_controlled is not None:
                self._on_controlled(None)
            self._manager.remove_entity(remote.entity.id)
            remote.entity = None

    def _apply_interpolated(self, remote: _Remote, render: float) -> None:
        history = remote.history
        parts = remote.parts
        if not history or parts is None:
            return
        newest = history[-1]
        if render >= newest.tick:
            # Nothing newer to move toward, so hold the newest rather than guess.
            if remote.applied is not newest.record:
                self._write(parts, newest.values)
                remote.applied = newest.record
            return
        index = bisect.bisect_right(history, render, key=_sample_tick)
        if index == 0:
            older = history[0]
            if remote.applied is not older.record:
                self._write(parts, older.values)
                remote.applied = older.record
            return
        older = history[index - 1]
        newer = history[index]
        if older.record == newer.record:
            if remote.applied is not older.record:
                self._write(parts, older.values)
                remote.applied = older.record
            return
        amount = (render - older.tick) / (newer.tick - older.tick)
        remote.applied = None
        for component_index, (schema, component) in parts.items():
            old_values = older.values.get(component_index)
            new_values = newer.values.get(component_index)
            if old_values is None or new_values is None:
                continue
            schema.write_blended(component, old_values, new_values, amount)
        del history[: max(0, index - 2)]

    @staticmethod
    def _write(
        parts: dict[int, tuple[ComponentSchema, Any]],
        values: dict[int, tuple[Any, ...]],
    ) -> None:
        for component_index, (schema, component) in parts.items():
            part_values = values.get(component_index)
            if part_values is not None:
                schema.apply(component, part_values)


def _sample_tick(sample: _Sample) -> int:
    return sample.tick
