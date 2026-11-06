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
| `EVENTS` | Reliable, ordered | Damage, deaths, drops, spawns. See [Game events](#game-events) |
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

### Game events

Hits, kills and heals have to agree on every screen, so the host sends them as events and
each client dispatches them to its own game. Register an event on the same schema, with a
codec per field, and the host's relay sends every registered type as the game dispatches it:

```python
schema.register_event(
    HitLanded,
    target=EntityRef(),                       # arrives as the client's own entity id
    amount=Quantised(step=0.01, wide=True),
    damage_type=EnumField(DamageType),
    killed=Flag(),
)
schema.register_event(SkillUsed, user=EntityRef(), skill=Choice(SKILL_NAMES))

# Host: the game dispatches as always, and its own screen reacts as before.
relay = EventRelay(dispatcher, replication, app)

# Client: the same presentation code reacts, since it listens to the same events.
replication = ReplicationClient(entity_manager, schema, spawners, on_event=dispatcher.dispatch)
```

- **An event lands with the snapshot it belongs to.** It goes out reliably, in order with spawns
  and despawns, and a client applies it when its delayed view reaches the event's tick. A hit
  number appears as the health drops, and a kill still names the enemy, although the host
  removed it the same tick.
- **`EntityRef` names replicated entities only.** It travels as the network id and arrives as
  the client's id for that entity, or None if it isn't replicated or is already gone. An entity
  spawned the same tick can be named: sending an event announces pending spawns first.
- **A client builds the event from the sent fields alone**, so every other field of the
  dataclass needs a default. Registering one without a default, or a field the class doesn't
  have, raises at once.
- **`Choice` sends a string from a fixed list**, such as a skill's name, by its position. Both
  sides list the same values in the same order; the fingerprint includes them, so a client with
  a different list refuses rather than misreading.
- **For one player only**, pass `slot_of=` to the relay, or `slot=` to
  `ReplicationHost.send_event`.
- **Don't relay what a client predicts.** A client's own hop or shot already played when the
  player pressed the button, and the host's copy arrives about a round trip later. Leave those
  events unregistered, or have the client ignore its own. Shots have this built in: see
  [Shots](#shots).
- **Events don't reach a player who joins later.** They describe moments, not state.

### Shots

Bullets are not replicated: hundreds of them read every snapshot would use up the budget. The
host sends each shot once, as a reliable event, and every client flies it on its own
`ProjectileSystem`. The host alone decides what a shot hits. It lives in the projectiles kit,
as `pyguara.kits.projectiles.net`, since core never imports a kit:

```python
from pyguara.kits.projectiles.net import (
    ProjectileClient, ProjectileHost, register_projectiles,
)

# Both sides, on the same schema.
register_projectiles(
    schema, SHOT_KINDS,
    position=QuantisedVector(step=0.25, wide=True),
    velocity=QuantisedVector(step=0.25),
)

# Host: the game's own ProjectileSystem, with its real on_hit. Fire through the relay.
shots = ProjectileHost(projectiles, replication, app)
shots.spawn("bolt", origin, velocity, slot=player_slot, life=0.8, hit_radius=6, payload=shot)

# Client: a display-only ProjectileSystem. Dispatch the host's events to it.
replication = ReplicationClient(world, schema, spawners, on_event=dispatcher.dispatch)
shots = ProjectileClient(display_projectiles, dispatcher, replication, TICK_SECONDS)
# Each frame, after the network update:
shots.update(frame_time)
```

A client draws from `projectile.payload`, a `NetShot` carrying the shot's kind.

- **A shot costs bytes once, when fired.** 24 bytes of event, about 34 on the wire. When one
  stops early, at a target, at a wall or by `ProjectileSystem.clear()`, the host sends where it
  stopped, 15 bytes more. One that runs out of life ends by itself on both sides. With 200
  bullets in flight a client receives exactly what it does with none
  (`tests/test_net_projectiles.py`).
- **Shots fly on the delayed timeline.** A shot leaves its shooter where the client draws the
  shooter, and moves with the delayed view's clock rather than the frame's, so it keeps pace with
  the interpolated world while that clock is corrected.
- **A player's own shots show at once.** Call `ProjectileClient.fire` from the character's
  `advance`, where the host's game calls `ProjectileHost.spawn` with that player's slot, with
  the tick `PredictionClient.advancing` names. Not `PredictionClient.tick`: one `step` advances
  several ticks when the client catches up, and a correction replays past ticks from inside
  `handle_message`, so only `advancing` is the tick being simulated. A shot is named by
  `ProjectileKey(slot, tick, index)`, so the host's copy is recognised and not shown twice.
  Both sides must fire a tick's shots in the same order. A replay firing a shot again is
  ignored, since it's already showing.
- **Prediction can be wrong about a skill being ready.** A shot shown that the host never fired
  is taken away half a second after the host's would have arrived, and counted in
  `mispredicted`. One the host fired that the client didn't show appears from the network, late,
  and is counted in `unpredicted`. Either one staying above zero means the client's idea of
  cooldowns or energy differs from the host's.
- **On a client, an own shot stops at the first opposing target it reaches**, for display only.
  That needs the display system to have a spatial index of what the client draws. Other players'
  shots pass through until the host says they stopped. A shot can look as if it touched a target
  and did nothing, which is the accepted trade: damage comes only from the host, as game events.
- **The host's `ProjectileSystem` must leave `on_end` free**, since the relay takes it.
  Stopping shots by setting `active = False` bypasses it, so a client never hears. Use
  `ProjectileSystem.clear()`.

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

## Prediction

Your own character runs at once. Its commands go to the host, each naming the host tick it
applies to, and the host sends back the exact state. If that differs from what the client
predicted for that tick, the client goes back to the host's state and replays the newer
commands. A state "at tick N" includes every command before N.

```python
@dataclass(frozen=True)
class Move:
    x: float = 0.0
    y: float = 0.0

commands = CommandSchema(Move, x=Quantised(step=1 / 64), y=Quantised(step=1 / 64))

def velocity_of(command: Move) -> Vector2:   # runs on both machines
    direction = Vector2(command.x, command.y)
    if direction.magnitude > 1.0:            # untrusted on the host
        direction = direction.normalize()
    return direction * SPEED

# Host
prediction = PredictionHost(commands, Move(), session.send)
app.add_step_hook(HostDriver(app, session, replication, prediction=prediction))
character.add_component(Replicated("player", controller=slot))
prediction.bind(slot, TopDownPrediction(character, mover, velocity_of))
# In fixed_update, for each remote player, before TopDownSystem runs:
body.velocity = velocity_of(prediction.take(slot, app.fixed_tick))

# Client
prediction = PredictionClient(commands, Move(), session.send)
replication = ReplicationClient(
    entity_manager, schema, spawners,
    predicted_components=(Transform,),
    on_controlled=lambda entity: prediction.bind(
        entity and TopDownPrediction(entity, mover, velocity_of)
    ),
)
app.add_step_hook(ClientDriver(session, replication, prediction=prediction))
# In fixed_update:
prediction.step(command_from_keys())
```

The client needs its own copy of the solids for the mover to query. The host's own player
just uses the keys: it has no one to predict for.

Things that will catch you out:

- **Velocity has to be a pure function of the command.** Anything else it reads, such as a
  timer, has to be in the state `capture` returns, or a replay comes out differently.
- **Only the movement is predicted.** `TopDownSystem`'s separation push needs other actors, so
  it arrives as a correction. Expect visible corrections while pressed against something the
  client doesn't simulate: phase 0 measured 10-19 px in constant contact before smoothing.
- **After the fixed updates, `Transform` holds what's shown**, which can include a fading
  correction. Read it in a fixed update for the simulated position.
- **The first moment after joining isn't predicted well.** The client starts with a guess at its
  lead, and commands sent before that settles get corrected.
- **Other players' characters are drawn about 100 ms behind.** They're interpolated like
  everything else.

**`PredictionClient.corrections` should stay flat** while you walk around walls with nothing
pushing you. If it climbs, the host and client are stepping differently, which is a bug.

### What it costs

Measured with the test harness on one machine, at a simulated 100 ms round trip.

| | |
| --- | ---: |
| Client, per frame, standing still, including the message | 18 us |
| Host, per player, per tick | 4 us |
| Replay of 6 ticks while moving, from phase 0 | 0.28 ms |
| Longest replay one correction can cause | 120 ticks |
| Command message, 60 a second | 47 bytes |
| State message, 20 a second | 40 bytes |
| A client's upload, on the simulated link | 26 kbit/s |

Over 30 seconds of walking and hitting walls, with five seeds, after the first 3 seconds:

| Network | Corrections | Commands late | Lead over the host |
| --- | ---: | ---: | ---: |
| 100 ms | 0 | 0 | 8 ticks |
| 100 ms, 2% loss | 0 | 0 | 8-9 ticks |
| 200 ms, 30 ms jitter, 2% loss | 0 | 0 | 12 ticks |
| 160 ms, 30 ms jitter, 20% loss | 0 | 2-6 | 10-12 ticks |

A simulated network proves the logic. **Whether it feels immediate has to be judged by a person**,
which is what `games/net_horde` is for.

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
