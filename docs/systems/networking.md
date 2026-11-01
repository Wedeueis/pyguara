# Networking

`pyguara.net` connects one hosting player's game to the players who join it: the transport
and session move messages and decide who may play, and replication keeps every client's world
matching the host's. **Prediction does not exist yet**, so a client's own character still moves
only when the host's snapshot says so.

It is opt-in. A single-player game imports none of it, and importing it needs no native
extension: only starting a session does.

## Hosting and joining

```python
from pyguara.net import (
    Channel, ClientSession, HostSession, Invite, MessageReceived, PlayerJoined,
    UdpTransport, Versions,
)

versions = Versions(engine="0.6.0", game="1.0", content_hash=my_content_hash)

# The host makes an invite and shares its string with its friends.
invite = Invite.create("203.0.113.5", 7777)
print(invite)  # pyguara://203.0.113.5:7777#...
host = HostSession(UdpTransport.host(invite.key, invite.port), versions)

# A player joins with that string.
invite = Invite.parse(text_from_a_friend)
client = ClientSession(
    UdpTransport.client(
        invite.key, secrets.randbits(63), invite.host, invite.port, versions.encode()
    )
)
```

Poll once a frame. Neither session raises because of what a peer sent.

```python
for event in host.poll():
    if isinstance(event, PlayerJoined):
        host.send(event.peer, Channel.EVENTS, welcome_bytes)
    elif isinstance(event, MessageReceived):
        handle(event.peer, event.channel, event.data)
```

A player whose engine version, game version, content hash or protocol differs is refused,
and `Refused.reason` names both sides. A wrong invite is deliberately silent at the network
layer, so it shows up as `Left` after 10 seconds, with a message saying to check the invite.

**An invite is a secret.** Anyone holding it can join, and anyone who also recorded the
session's handshake can read that session. Make a new one per session. `repr(invite)` leaves
the key out, so it does not end up in a log by accident. Players also see each other's IP
addresses on a direct connection, and a game should say so.

## Channels

| Channel | Delivery | Use it for |
| --- | --- | --- |
| `COMMANDS` | Unreliable | Per-tick input. Repeat recent ticks in each message, so one loss costs nothing |
| `SNAPSHOT` | Unreliable, may reorder | State. **Carry a tick, and drop anything older than you have** |
| `EVENTS` | Reliable, ordered | Damage, deaths, drops, spawns |
| `LEVEL` | Reliable, ordered, lowest priority | Large transfers |
| `CONTROL` | Reliable, ordered | The session's own. A client's messages here are ignored |

Channels are not ordered against each other, so an event can overtake the snapshot it
depends on.

**Keep unreliable messages under about 1,100 bytes.** A larger one is split into slices, and
losing one slice loses the whole message. Split a large snapshot into several messages that
each decode alone.

`send` returns `False` rather than raising when a message is not accepted: no such peer, or
over the channel's limit. On a reliable channel that means a backlog, and the largest single
message is half the channel's limit: about 512 KiB on `EVENTS` and 8 MiB on `LEVEL`.

## Replication

The host simulates. Clients draw what they receive, about 100 ms behind, so there is always a
newer snapshot to interpolate toward.

```python
schema = ReplicationSchema()   # the same on host and client, in the same order
schema.register(Transform, position=QuantisedVector(step=0.25), rotation=Angle())
schema.register(Health, current=UInt16(), max_health=UInt16())

# Host
replication = ReplicationHost(entity_manager, schema, session.send)
app.add_step_hook(HostDriver(app, session, replication))
enemy.add_component(Replicated("enemy"))             # everyone sees it
drop.add_component(Replicated("drop", owner=slot))   # only that player does

# Client: a name from the network can only choose among these
replication = ReplicationClient(entity_manager, schema, {"enemy": make_enemy, "drop": make_drop})
app.add_step_hook(ClientDriver(session, replication, on_event=handle_game_message))
```

Run nothing that simulates on a client: no AI, flocking or spawning. To see all of this running:

```bash
uv run python games/net_horde/main.py                      # both sides, one window
uv run python games/net_horde/main.py --host               # one window
uv run python games/net_horde/main.py --join "pyguara://"  # the other
```

Things that will catch you out:

- **Field range.** A 16-bit `QuantisedVector` at step 0.25 reaches about 8000 units from the
  origin. Use `wide=True` for more. A value that doesn't fit saturates, and is counted in
  `ReplicationHost.saturated()`.
- **A reliable message of your own** must start with a byte below `FIRST_RESERVED_KIND`, 0xE0.
- **Per-player drops on the host's own screen.** The host's world holds everyone's, so its
  renderer and effects must filter by `Replicated.owner`. A client's world never holds anyone
  else's, since they are never sent.
- **Teleports.** A jump over `snap_distance`, 256 units by default, is drawn at once rather than
  as motion. Shorter ones slide.
- **A component needs to exist on the client's entity**, from its spawner, or its state is ignored.
- **Pass `digest_every=` while developing.** The host then sends a hash of the state, and
  `ReplicationClient.digests_mismatched` above 0 is a real desync.

### What it costs

Measured with `tools/net_phase0.py`, on a horde of real components with three clients, per frame
at 60 Hz with 20 Hz snapshots. Reproducible, but not from a shipping game.

| Entities | Host | Client | Per client, at 20 Hz |
| ---: | ---: | ---: | ---: |
| 200 | 0.22 ms | 0.82 ms | 0.35 Mbit/s |
| 500 | 0.55 ms | 2.7 ms | 0.88 Mbit/s |
| 1,000 | 1.13 ms | 6.0 ms | 1.77 Mbit/s |

A client spends more than the host because it decodes and interpolates, but it isn't running the
simulation. **Python's garbage collector is the remaining hitch**: a full collection took up to 23
ms, which makes the worst frame about 20 ms where it would otherwise be about 4. That run held four
worlds in one process, so a real client should be smaller, but measure it in a real game.

## Everything from the network is untrusted

The Rust core authenticates packets and survives hostile ones, but **it does not make a
decoded value sensible**. An invited player can send any bytes in a valid message. So in your
own decoders:

- Bounds-check lengths, ids and enums.
- Reject non-finite floats.
- Clamp and validate commands on the host: move vectors, cooldowns.
- Treat a decoding failure as dropping the message, never as an exception in the frame loop.
- Never unpickle network data.

## Testing

`SimulatedNetwork` drives the real Rust core through a seeded fake wire, with an explicit
clock. There are no sockets, threads or sleeps, and a failure replays from its seed.

```python
network = SimulatedNetwork(seed=1, conditions=LinkConditions(latency=0.05, loss=0.02))
host = network.add_host(key)
client = network.add_client(key, network.address_of(host), versions.encode())
network.advance(1 / 60)
```

These suites need the extension built, and fail rather than skip without it. A simulation
proves the logic. It cannot prove how a real connection behaves or whether playing over one
feels good, so see [the network probe](../guides/network-probe.md) for testing between two
machines.

See `docs/adr/0007-networking-model.md` for why it works this way.
