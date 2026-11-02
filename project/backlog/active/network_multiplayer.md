# Networked multiplayer: engine plan

**Status:** Phases 0 and 1 are merged (#372, #373): the transport and session exist, and
replication and prediction do not. Still open from those phases: probe 4, which needs two
machines, and running the transport on Windows at all. Written 2026-11-01, against `4ea2fa1`.
Reproduce the Python numbers with `tools/net_phase0.py`.

**The requirement.** One player hosts a game from their own machine, and other players
connect to it. The first user is Reclaimer, an online co-op action RPG with hordes and
heavy projectile counts, for 4 players. Windows is the main platform and Linux the secondary.

Keep to this repo's method: probe before fixing, measure before deciding, and treat the
numbers here as weaker than whatever a later measurement says. This plan's biggest
claims are estimates, and section 11 says which.

---

## 1. Decisions

| | Decision | Status |
| --- | --- | --- |
| 1 | Topology: a **listen server**. The hosting player's game is the server | Required |
| 2 | Model: **the host decides everything**, and clients send input and display state | Recommended |
| 3 | Clients **predict their own character** and interpolate everyone else | Recommended |
| 4 | Transport: **UDP, in Rust**, as a backend behind a `Transport` protocol. Reliability and packet authentication from **`renet` and `renetcode`**, behind a hardening layer, because both can be panicked remotely as shipped (section 3) | Decided |
| 5 | **Rust below the line, Python above it.** Sockets, packets and reliability are native. Anything that reads or writes ECS components stays Python unless a measurement earns a port (ADR 0004) | Decided |
| 6 | Testing is built on an **in-process simulated network**, with seeded loss and lag, driving the real Rust core from Python | Recommended |
| 7 | Co-op among friends: **the host is trusted**, and clients are validated but not policed | Recommended |
| 8 | **Joining takes an invite**: a random 256-bit session key, shared as a string. No Unsecure mode, ever | Decided |
| 9 | **4 players**, so a host and 3 guests | Decided |
| 10 | **No joining mid-run.** Admission closes when a run starts | Decided |
| 11 | **The host owns the town and meta progression; each player owns their character** | Decided |
| 12 | **Every drop is independent for each player** | Decided |

### Why not lockstep

Lockstep sends only inputs and has every machine run the same simulation, which uses
almost no bandwidth and looks like a natural fit now that queries are reproducible
(#324). I rejected it for this game because:

- It needs **bit-identical results across machines**. #324 proved flocking reproducible
  on one machine. Nothing has tested pymunk, or floats generally, across x86 and ARM,
  or across operating systems. The Python and native stores also differ in their last
  bits (ADR 0004, Decision 5), so a mismatch ends the session.
- **Everyone waits for the slowest player's input**, which is poor for fast action.
- **Every machine has to run the whole horde**, not just the host.

Worth revisiting only if bandwidth turns out to be the real limit.

### Why the line is where it is

**Below the line, Rust**, and raw speed is not the main reason:

- **Steady timing.** A Rust thread receives and acknowledges packets without needing the
  GIL. In pure Python, a garbage-collection pause or level generation on the host would
  stall the network for every player.
- **Untrusted input.** This code parses data from the internet, and memory safety and
  strict types suit that.
- **Existing libraries.** `renet` replaces our own reliability layer (section 3), and a
  Steam binding may need native code regardless.
- **No shipping cost.** Every wheel already carries the extension (ADR 0006).

**Above the line, Python.** Replication and prediction read and write ECS components and
run Python movement code. Flocking is the warning here: its crossing was 63% of the native
tick, because every agent is an ECS entity, and these layers have the same shape. Snapshot
encoding sits on the line and stays in Python: Phase 0 priced moving it at 1.2-1.9x, under
ADR 0004's bar, because the component reads are half the cost and cannot move (section 3).

**This is a backend, not a store.** Like the native audio backend, it has no Python
counterpart, so it is loaded through `native.require_extension()`, and `PYGUARA_NO_NATIVE=1`
does not turn it off (ADR 0004, Decision 4). `pyguara.net` must still import cleanly
without the extension, and fail with a clear message only when a session starts, so a
single-player game on an uncovered platform is unaffected.

### Non-goals

Dedicated servers (the design keeps them possible, since a headless host is the same
code), public matchmaking, anti-cheat, host migration, cross-version play, and more
more than 4 players in Reclaimer. The transport allows up to 64, but nothing above it is
designed or tested past 4.

---

## 2. What the engine already gives us

| Have | Why it helps |
| --- | --- |
| Fixed-step simulation, `Application._fixed_update`, 60 Hz default | Ticks are the network's clock |
| `HeadlessRenderer` and `FixedClock` | Host and clients can run in one test process, deterministically |
| `PlayerRouter`, `controller_id` on input events | Already separates players; remote players are a new source |
| `Transform.previous_position`, `interpolate` | Render interpolation already exists |
| `subscribe_entity_removed`, `subscribe_component_added`, `subscribe_component_changed` | Hooks for spawn, despawn and change tracking |
| `PrefabFactory.create(prefab, overrides=)` | "Spawn this prefab here" is already one call |
| `ComponentRegistry` | Named component types, for the wire format |
| `RandomService`, named streams | Host-side gameplay randomness |
| Ordered queries (#324) | Replication order is stable, which makes tests and debugging easier |
| `EventDispatcher.queue_event` | A safe path if a background thread is ever used |
| `MultiScopePersistence` | Per-scope saves for host and guests |

What's missing is all of it on the network side: no sockets exist in the package.

---

## 3. Measured starting costs

Pure Python, on this machine, for one snapshot of N entities at 12 bytes each (id,
position, velocity, one state field, all quantised). Fastest of 200 rounds.

| Entities | Pack | Unpack | JSON instead | Bytes | JSON bytes | At 20 Hz, per client |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 0.023 ms | 0.007 ms | 0.155 ms | 600 | 6,961 | 0.10 Mbit/s |
| 200 | 0.090 ms | 0.026 ms | 0.611 ms | 2,400 | 27,886 | 0.38 Mbit/s |
| 500 | 0.224 ms | 0.067 ms | 1.570 ms | 6,000 | 69,933 | 0.96 Mbit/s |
| 1,000 | 0.447 ms | 0.146 ms | 3.123 ms | 12,000 | 140,033 | 1.92 Mbit/s |

Loopback UDP send plus receive of a 1,200-byte datagram: **5.9 us**.

What this says:

- **Python's packing cost is not the problem.** Packing 1,000 entities is 3% of a frame.
  So the case for the Rust transport is timing and safety (section 1), not this table.
- **Bandwidth is the limit.** The host's upload is per client: 3 guests at 500 entities
  is **2.9 Mbit/s** before deltas, sustained, on a home connection's upstream.
- **JSON is out.** It costs 7x the time and 12x the bytes.
- zlib level 1 saved only 7-13% on this data, because it was random. Real positions may
  compress better; measure on a real game.

**Limits of this table.** It uses synthetic data and flat records, and leaves out reading
the values from ECS components. Phase 0 below replaces it.

### Phase 0 results

**Snapshot cost, reading real components** (probe 1). `Transform`, `FlockingAgent` and
`Health` on entities moved by the real `FlockingSystem`. Fastest of 200.

| Entities | Read | Pack | Total | Of a frame | Bytes | zlib 1 | XOR delta + zlib 1 | Plain, at 20 Hz |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 200 | 0.106 ms | 0.101 ms | 0.207 ms | 1.2% | 2,400 | 1,851 | 1,145 | 0.38 Mbit/s |
| 500 | 0.271 ms | 0.257 ms | 0.528 ms | 3.2% | 6,000 | 4,670 | 2,630 | 0.96 Mbit/s |
| 1,000 | 0.547 ms | 0.505 ms | 1.053 ms | 6.3% | 12,000 | 9,485 | 4,998 | 1.92 Mbit/s |

- **Reading costs about the same as packing**, not more, as this plan had guessed. CPU is
  still not the constraint.
- **Real data compresses.** zlib alone saves 21-23%, against 7-13% on the random data above.
  A delta three ticks apart saves 52-58%, so 3 guests at 500 entities drops from 2.9 to about
  1.3 Mbit/s. Every agent in this horde moves every tick, which is close to the worst case.
- **Limit:** this is a constructed horde on real systems, not a shipping game's scene.

**The crossing** (probe 6). A scratch pyo3 module with the queue design of section 4: filling
and draining 1 message of 1,100 bytes costs 0.4 us, and 20 messages cost 2.9 us. So a crossing
per message is negligible.

Encoding natively, including the crossing, is 0.019 ms against Python's 0.29 ms at 500
entities. But the reads stay in Python, so the whole job gains only **1.9x** as built, and
`tools/price_native_boundary.py` prices it at **1.2x** using a numpy handoff. Both are under
ADR 0004's bar, and the prize is about 0.27 ms. **Encoding stays in Python.**

**Crate or our own** (probe 5).

| Crate | Sans-IO | C or system deps | Licence | Verdict |
| --- | --- | --- | --- | --- |
| `renet` 2.0.1 + `renetcode` 2.0.0 | Yes: bytes and a `Duration` in, bytes out | None; under 30 crates in total | MIT or Apache-2.0 | **Use, hardened** |
| `quinn-proto` 0.11 | Yes | `ring`, which is C and assembly | MIT or Apache-2.0 | Rejected: about 40 crates, a C toolchain on every platform, and certificates to manage |
| `laminar` 0.5 | Not checked | Not checked | MIT or Apache-2.0 | Rejected: last release 2021 |
| `renet2` 1.0 | Not evaluated | Not evaluated | MIT or Apache-2.0 | A fork worth a look if upstream stalls |

Measured on `renet` and `renetcode`, driven through a seeded simulated network at 50 ms plus
jitter and 2% duplication: 500 ordered messages and a 64 KB sliced message.

| Loss | Complete and in order | Worst time |
| ---: | ---: | ---: |
| 0% | 200 of 200 seeds | 2.1 s |
| 5% | 200 of 200 seeds | 3.3 s |
| 20% | 200 of 200 seeds | 3.4 s |
| 40% | 200 of 200 seeds | 5.8 s |

The core costs 23 us per frame for 3 messages of 1,100 bytes, encrypted and decrypted, both
ends together. A healthy session outlives the token's 300 seconds: still connected at 1,900.

**Hostile input is where the crates fall short.** Each of these was reproduced in the shipping
profile, and none needs anything an attacker lacks:

| Input | Who can send it | Result |
| --- | --- | --- |
| One datagram whose first byte's high nibble is over 8 | **Anyone, before any authentication** | Panic, `renetcode` `packet.rs:375` |
| One short datagram, too small for its MAC | **Anyone, before any authentication** | Panic, `renetcode` `crypto.rs:10` |
| Two slices of one message with different `num_slices` | Any connected client. In Unsecure mode that is anyone; with invites, only someone invited | Panic, `renet` `slice_constructor.rs:41` |
| One malformed packet to bare `renet` | Anyone, if `renet` is used without `renetcode` | Disconnects the peer, where section 5 requires a drop |
| A lost first keepalive, while the host is sending (found in phase 1) | The network itself: 19 of 100 joins at 20% loss | The host admits a player whose client then times out |
| A message the sender accepts but the receiver's slice accounting can't hold (found in phase 1) | Any large send | The receiver disconnects the peer |

The fix does not need a fork, and it is checked:

1. **Never use `renet` bare.** `renetcode`'s AEAD rejects forged packets before `renet` parses
   them. Of 1.5M forged and mutated datagrams, 2 reached `renet`. That fits a mutation that
   cancelled itself out, once per direction, with replay protection catching any repeat, but
   the probe didn't confirm it.
2. **Pre-filter every datagram**: `seq_len = b[0] >> 4`, require `seq_len <= 8` and
   `len >= 1 + seq_len + 16`. This took the 1.5M from 163,190 panics to **0**.
3. **`catch_unwind` around each peer's processing**, and drop that peer on a panic. This covers
   the slice attack and whatever fuzzing has not found. `panic = "abort"` would defeat it, so a
   test must pin that the release profile unwinds. Not yet built.
4. **Small per-channel memory limits on client traffic.** `renet` checks its limit before
   allocating for a slice, so this bounds what a client can make the host allocate.
5. **Neither end counts as connected until both know it.** A client sends a one-byte
   confirmation until it hears a payload, and the host neither sends to a peer nor reports it
   until it has heard one. Without this, one lost packet could fail a join that the host
   believed had succeeded.
6. **A reliable channel only fills half its limit**, since slice rounding can at most double
   what the receiver charges.

All six are built, and each was removed in turn to confirm a test fails without it. ADR 0007
lists them with their guards.

12M structure-aware packets at `renet`'s receive path found that slice panic and nothing else;
with `num_slices` held constant, 0 panics. That is why hardening beats writing our own: the
reliability logic held up, and the bugs are at the edges, in places a thin layer can guard. Our
own parser would need the same fuzzing, and would start without this much evidence.

**Not reported upstream, by the owner's decision.** `read_sequence` is unchanged on `renet`'s
master branch; the other two weren't checked there. So recheck all of this before taking a new
version, and keep the fuzz test, since a fix can't be assumed.

---

## 4. Architecture

```text
rust/src/net/        Below the line
├── core             Sans-IO: bytes in, bytes and messages out. Glues renetcode (handshake,
│                    authentication, timeouts) to renet (acks, channels, slicing), and is
│                    where the pre-filter and catch_unwind of section 3 live
└── socket           UDP socket and background thread, a thin layer over the core

pyguara/net/         Above the line
├── transport.py     Transport protocol; UdpTransport; SimulatedTransport
├── session.py       Peers, lobby, version check, disconnect handling
├── clock.py         The client's estimate of the host tick
├── commands.py      Per-tick player commands, sent redundantly
├── replication.py   Replicated component, schemas, snapshots, deltas
├── prediction.py    Input history, reconciliation
├── interpolation.py Snapshot buffer for remote entities
├── events.py        Reliable game events
└── roles.py         NetRole, and which systems run where
```

Host and client in one frame, in the existing `Application.step` order:

```text
HOST                                    CLIENT
receive commands from clients           receive snapshots and events
                                        produce local command, send it
                                        store it in the input history
fixed_update (several per frame):       fixed_update:
  apply each player's command             predict own character only
  full simulation
send snapshot at 20 Hz                  reconcile if a snapshot disagrees
render                                  interpolate others ~100 ms behind, render
```

**A Rust thread owns the socket.** It receives, acknowledges, resends and handles
timeouts on its own, and hands whole messages to Python through a queue that the main
thread drains once per frame. A stalled Python frame therefore delays game state, not the
connection itself.

**The core is sans-IO:** a state machine that takes bytes and a time, and returns bytes and
messages, with no socket or thread inside it. This is what keeps it testable. A Python test
can run two real cores against each other through a seeded simulated network, with an
explicit clock, and no sleeps. The socket thread is a thin layer on top, tested separately.

**Keep the boundary narrow, and message-shaped.** Python hands over one encoded snapshot per
send and receives whole messages, so a crossing per message, never per entity or per field.
This is the flow field's lesson from ADR 0004: an opaque store with few crossings priced far
better than flocking's.

**This requires one change to core**: `Application.step` needs two hooks, around the
fixed updates, which also touch the frame loop. Ask first, as `AGENTS.md` requires for
core systems. Everything else can live in `pyguara/net` as an opt-in, so a single-player
game imports none of it.

**A cost to accept.** Protocol changes need a rebuild (`make native`), and early protocol
work changes often. A stale build is easy to miss: a W28b test run failed in a way that
fitted one. Have `pyguara.net` compare a protocol version with the extension at import, and
name `make native` in the error.

---

## 5. Protocol

**Packet format** comes from the crates: `renetcode`'s encrypted envelope (prefix, up to 8
bytes of sequence, 16-byte MAC) around `renet`'s packets (sequence, channel, messages).

**Keep unreliable messages under about 1,100 bytes.** `renet` slices anything over 1,200, and
a sliced unreliable message is lost whole if one slice is. So a large snapshot is still split
across messages by entity, so each decodes alone and a lost one loses only its own entities,
which the next snapshot corrects. A full slice is an estimated 1,240 bytes on the wire, over
IPv6's 1,232-byte guarantee and under IPv4's usual 1,472. Measure it in phase 1, and check it
on a real path in probe 4.

| Channel | Used for | Delivery |
| --- | --- | --- |
| Commands | Client to host, each tick | Unreliable; each packet repeats the last few ticks, so one loss costs nothing |
| Snapshot | Host to client, 20 Hz | Unreliable; the newest wins. `renet` may reorder these, so the message carries its tick and Python drops stale ones |
| Events | Damage, deaths, spawns, chat, and each player's own drops, sent to that player only | Reliable and ordered |
| Level | Seed, room data, scene changes | Reliable and ordered, fragmented |

**Handshake.** `renetcode`'s connect, challenge and response, in its secure mode:

- **An invite carries a random 256-bit session key.** The client mints its own connect token
  under that key, so only invited players can connect, and the session keys inside the token
  stay secret. Unsecure mode's all-zero key is refused outright.
- **The token's server address is a fixed placeholder, on both sides.** Secure mode checks it
  against the host's public addresses, and a host behind NAT doesn't know its own. Nothing else
  uses the value: the client sends to the address in the invite.
- **Token time counts from zero, not from a wall clock**, with a 10-year expiry, so a guest's
  wrong clock can't refuse them. A replayed token gains nothing without the keys inside it, and
  `renetcode` refuses one token from a second address.
- **A wrong `protocol_id` is ignored in silence**, so keep it fixed forever. Protocol, engine
  and game versions and the content hash travel in the token's 256 bytes of user data, and the
  session layer refuses with a reliable message saying both versions, then disconnects. A wrong
  key is silent too: the client times out, and the error must say to check the invite.

**Ticks.** Commands carry the tick they apply to. The client estimates the host's tick
from round-trip time and runs slightly ahead, so its commands arrive just in time. The
host keeps a small per-player buffer, repeating the last command if one is late.

**Connection loss.** A silent peer times out after 10 seconds. If the host leaves, the session
ends, and there's no migration. Whether a player who drops can return to the same run is an
open question: see section 12.

### Security

- **Never unpickle network data.** W3 removed pickle from saves for this reason. Use
  explicit binary formats only, on both sides of the line.
- **Every field from the network is untrusted, and Rust only covers the packet layer.**
  It protects memory safety in parsing. It does not make a decoded value sensible, and the
  Python layers decode message contents themselves. So bounds-check lengths, ids and enums
  in Python too, reject non-finite floats, and cap message rates. Malformed input drops the
  packet. It must never raise into the frame loop, and the Rust side must never panic across
  the boundary or kill its thread silently.
- **Only authenticated traffic counts against a peer.** UDP source addresses are spoofable, so
  throttling or kicking by address before the MAC check would let a stranger remove a real
  player with forged packets. Unauthenticated datagrams share one global budget.
- **The host validates commands**: clamp move vectors, enforce cooldowns on the host.
- **Hosts and guests see each other's IP addresses** with direct connection. State this
  in the game's UI; a relay hides it (section 8).
- **Every packet is encrypted and authenticated** under keys only invited players hold. There
  is no forward secrecy: anyone who has the invite and recorded the handshake can read that
  session, so treat an invite as a secret and make a new one per session.

---

## 6. Replication

**Opt-in, by component and field.** A `Replicated` component marks an entity. A game
registers a schema per component, stating fields and how to quantise them:

```python
replication.register(Transform, position=Quantised(step=0.25), rotation=Angle(bits=8))
replication.register(Health, current=UInt16(), maximum=UInt16())
```

- **Network ids.** Entity ids are uuid strings, which are too large and carry no order.
  The host assigns each replicated entity a 16-bit id, and both sides keep a map.
- **Spawning.** Sent reliably as prefab name, network id, and initial state. The client
  calls `PrefabFactory.create`. Despawn comes from `subscribe_entity_removed`.
- **Deltas.** Each client acknowledges a snapshot, and the host encodes against that one,
  which keeps working through loss. Start with whole-entity state and measure, because
  delta logic adds bugs.
- **Priority.** When a snapshot is over budget, send nearby and recently changed entities
  first, per client. Skip interest management until a measurement asks for it: co-op
  players are usually together, but the plan must allow them not to be.

**Don't drive replication from `notify_component_changed`.** Phase 0 confirmed the trap: over
30 ticks, `FlockingSystem`, `TopDownSystem` and `PhysicsSystem` moved every entity and notified
zero times. Outside Studio, nothing in `pyguara/` calls it. Replication reads replicated fields
each snapshot, at the cost in section 3.

### Projectiles: the key decision for bullet hell

Don't replicate projectiles per tick. `ProjectileSystem` is a pool of plain objects,
not ECS entities, and hundreds of bullets in snapshots would use up the budget.

**Send each one once, as a reliable event:** origin, velocity, type, spawn tick. Each
client then simulates its flight locally, advanced by the elapsed latency. The host alone
decides hits, and sends those as events. A bullet may visibly pass close to a target
without hitting, which is the accepted trade.

The same rule applies to everything else that is predictable: send the cause, and let
clients work out the rest.

### What runs where

| | Host | Client |
| --- | --- | --- |
| AI, flocking, flow field, spawning | Runs | Off |
| Damage, health, status effects | Runs | Display only |
| Drops | Rolls and tracks each player's separately | Sees and collects only its own |
| Own character's movement | Runs | **Predicted** |
| Other characters and enemies | Runs | Interpolated |
| Bullets | Runs, decides hits | Simulated for display |
| Particles, sparks, audio, damage numbers | Runs locally | Runs locally, from events |
| Level generation | Runs | From seed, verified by hash, with a full transfer as fallback |

**Native and Python stores don't need to match between players.** Clients don't simulate
what the stores do, so one guest running Python doesn't diverge. That's a benefit of this
model over lockstep. Replays are unaffected: this plan doesn't cover recording network
sessions.

`NetRole` needs a way to mark a system as host-only, client-only or both. It should be
done by which systems a scene registers per role, rather than by adding checks to
`SystemManager`, which is core.

### Drops are per player

When something dies, the host rolls a separate drop for each player, and each player sees and
collects only their own. Nobody can take another player's loot, and nothing about a drop needs
agreeing between clients.

- **Rolls:** one named `RandomService` stream per player slot, so one player's rolls never
  shift another's.
- **Player slots:** peer ids are random 63-bit numbers, so the session assigns each player a
  slot, 0 to 3. Save data and masks use the slot.
- **Collection needs no engine change.** `Magnet.mask` already filters by spatial-index bits.
  Track each player's drops under their slot's bit and give their magnet only that bit.
- **Replication needs per-peer visibility.** `Replicated` gains an owner, and a snapshot leaves
  out what its client doesn't own. Other clients never learn these entities exist, which also
  saves bandwidth, since drops stop being multiplied by players.
- **The host's own screen is the trap.** Clients are filtered by what they receive, but the host
  holds all four players' drops in one ECS, so its renderer would draw them all, and its audio
  and particles would fire for them. Give a drop a `Sprite` on the host only if it is the host's
  own, and scope the pickup effects the same way.

### Who owns what

| Data | Owner | Saved on | During a run |
| --- | --- | --- | --- |
| Town, meta progression | Host | Host's machine | Host only |
| Character: stats, levels, gear | Its player | That player's machine | Host decides; the player's machine records what it is told |

A character arrives from the guest's machine at the lobby, so **the host validates it like any
other network data**: bounds-check every field, and reject what doesn't decode. A guest can edit
their own save and join stronger than they earned. That fits decision 7, and stopping it would
take server-side accounts.

In a run the character is host-authoritative like everything else. The host sends XP, levels and
items as reliable events, and the guest's machine saves them. `MultiScopePersistence` fits as is:
a `meta` scope only the host writes, and a `character` scope on each machine.

### Prediction

The client keeps a ring buffer of recent commands. On each snapshot it takes the host's
position for its character at the last acknowledged tick, replays the newer commands from
there, and compares. Small differences are smoothed over a few frames, and large ones snap.

**Replay works** (probe 3), which retires this plan's largest technical risk.
`CharacterMover.move` only queries the space, so one character can re-run alone. Over 600 ticks
of a real host loop, replaying every window through `CharacterMover`:

| Scene | Replay of 6 ticks differs from the host | Worst |
| --- | ---: | ---: |
| Walls only, from position **and** `_remainder` | **0.0%, bit-exact** (also at 12 ticks) | 0 px |
| Walls only, from position alone | 37.5% | 1.41 px |
| A solid enemy chasing, shown 100 ms behind | 3.5% | 10 px |
| A separating enemy chasing | 28.3% | 19 px |

Cost: 0.28 ms at 6 ticks, 0.73 ms at 12, 1.46 ms at 24. The physics world was unchanged after
every replay.

What this asks of the design:

- **Send the owner its character's `_remainder`.** Position alone is off by up to a pixel on
  more than a third of replays, which would read as constant small corrections. It need only
  go to that character's owner, in that client's snapshot.
- **Expect visible corrections in a melee.** The enemy rows are the cost of predicting against
  a world the client doesn't simulate, and they are a worst case: an enemy in contact for most
  of the session. Whether 10-19 px feels acceptable once smoothed is for a person to judge in
  phase 3.
- **The separation push can't be predicted by this replay**, because it lives in
  `TopDownSystem._separate_actors` and needs the other actor. The host's push arrives by
  reconciliation.
- **The kit needs a small refactor, not a pure step function.** The collider-offset handling
  lives in `TopDownSystem.update`'s loop, so a one-body step should be pulled out of it, so
  that host and replay can't drift apart.
- **Velocity must be a pure function of the command**, or replay has nothing to re-run. That's
  a rule for game control code.

Not probed: `kits/platformer_movement`, whose character state is larger than a remainder.

Dash and skills with movement are predicted too. Their damage isn't.

### Desync

With a host deciding everything, a client can't drift apart for long: the next snapshot
corrects it. These are the ways it can stay wrong, and each needs a rule and a test:

- **A snapshot names an entity whose spawn hasn't arrived.** Channels aren't ordered against
  each other. Hold such records until the spawn arrives, and never invent the entity.
- **A despawn and a late snapshot cross.** Every event carries its tick; a record older than
  an entity's despawn tick is dropped, so a dead enemy can't reappear.
- **Network ids get reused.** 16 bits wrap in a long session. Hold a freed id until every client
  has acknowledged a snapshot newer than its despawn.
- **A reliable event is applied before the snapshot it depends on.** Apply events at their tick
  on the interpolation timeline, not on arrival.
- **Prediction disagrees for good.** Velocity must be a pure function of the command, and owner
  state includes `_remainder`. Keep correction size in the debug overlay, since a steady
  non-zero correction with no enemies nearby means a real desync.
- **Client content differs.** The handshake's content hash, and the level hash of section 6.
- **Silent divergence nobody looks at.** In debug builds, the host sends a hash of replicated
  state for a sample of ticks, and the client compares and logs the first mismatch by entity.
  Convergence tests assert it stays clean under every network condition in section 9.

### Effects that don't translate

- **`Application.time_scale`** slows the whole simulation, so hit-stop would stall every
  player if used on the host. Needs a presentation-only version, or a clear warning.
- **Pause** can't exist while connected. Scene code that assumes it needs to know.
- **`ReplayRecorder`** records one machine's input, so it doesn't describe a session.

---

## 7. Phases

Each phase has a test for being done. Don't start the next until it passes.

### Phase 0: Probes (no engine code)
1. Real snapshot cost. **Done**, section 3, on a constructed horde rather than a real scene.
2. Does every movement writer notify? **Done: none do**, section 6.
3. Can one character's movement be stepped alone? **Done: yes**, section 6.
4. Real packet behaviour over a real internet path between two machines. **Deferred by the
   owner** to the end of phase 1, since `tools/net_probe.py` is the instrument it wants.
5. Crate or our own. **Done: `renet` and `renetcode`, hardened**, section 3. Not yet shown:
   that they build on all five wheel platforms (the dependency tree has no C, and phase 1's
   done-when builds them), and how a future Steam transport fits beneath them.
6. Price the crossing. **Done**, section 3.

**Done when:** the numbers and the crate decision are written into this file, and any
section they contradict is rewritten. Earlier audits here found that first estimates are
often wrong, and they were again: section 3's guess about read cost, and the assumption that
a well-used crate would survive hostile input.

### Phase 1: Transport and session
The sans-IO core in `rust/src/net`, gluing `renetcode` to `renet` with section 3's hardening,
and invites with keyed tokens. The socket thread. The Python `Transport`
protocol, `UdpTransport`, and `SimulatedTransport` (seeded lag, jitter, loss, duplication,
reordering), plus the protocol-version check.
**Done when:** a reliable stream arrives complete and in order at 20% loss, under every
seed tried, a hostile-input fuzz test never panics or raises, two processes connect over
UDP, the connection survives a 2-second stall of the Python main thread, and all five wheels
build and carry it.

### Phase 2: Replication
Network ids, schemas, spawn and despawn, snapshots, interpolation, frame hooks in `Application`.
**Done when:** a headless client's world converges to the host's after loss stops, and a
visible demo runs with two windows on one machine.

### Phase 3: Commands and prediction
Remote players through the input layer, tick estimate, command buffer, prediction, reconciliation.
**Done when:** at a simulated 100 ms and 2% loss, moving your own character feels immediate
(a person must judge this), and the host and client agree on position afterwards.

**This is Reclaimer's M2.** Stop here and let real play shape the rest.

### Phase 4: Events and projectiles
Reliable game events, projectile spawn events, role-based system registration.
**Done when:** 200 bullets on screen use a bounded amount of bandwidth, every client agrees on
who died, each player's drops match the host's record for that player, and no client or host
screen shows a drop belonging to someone else.

### Phase 5: Robustness
Lobby API, closing admission when a run starts (a late joiner is refused with a message saying
so), character upload and validation, player leave, version refusal, level transfer, delta
encoding if measurements call for it, debug overlay (ping, loss, bandwidth, correction
size), scene-change barrier.
**Done when:** a 4-player session survives a 30-minute soak over a real connection, a late
joiner is refused, and one player leaving doesn't disturb the others.

### Phase 6: Reaching players
Section 8. **Done when:** a non-technical player can host from home without changing router settings.

---

## 8. The hardest non-code problem: reaching the host

Player-hosted games have to get through the host's home router. **Many hosts can't accept
direct connections**, and carrier-grade NAT, which many ISPs use, makes port forwarding
impossible no matter what the player does. The plan isn't finished until this is solved.

| Option | Reach | Cost | Notes |
| --- | --- | --- | --- |
| Direct IP and port forwarding | Technical players with a public IP | None | Enough for development. Unacceptable as the only release option |
| UPnP port mapping | Some routers | Low | Often disabled, and useless behind carrier-grade NAT |
| NAT hole punching | Many, not all | **You run a rendezvous server** | Fails on some NAT types, so it needs a relay fallback anyway |
| Your own relay | Everyone | **You pay for hosting and bandwidth** | Adds latency. Ongoing cost |
| **Steam Networking** | Everyone on Steam | A Steam app and fee; 30% of sales through Steam | Relay included, encrypted, hides IPs. Steam-only |
| Tailscale, ZeroTier and similar | Enthusiasts | Free for players | A useful stopgap during testing |

**Recommendation.** Use direct IP for development and early friends. Plan on Steam for
release, since `pyguara dist` already targets it, and write `SteamTransport` against the
`Transport` protocol. It needs a binding to Steamworks, which is its own research task, and
the native crate is the likely home for it. **A Steamworks binding would be the first thing
in the extension with a system-library dependency**, which ADR 0006 has so far avoided, so
it may need to be optional or ship separately.

**Open question for the owner:** is Steam the only store? See section 12. `pyguara dist` also
targets itch.io, where Steam's relay isn't available. Supporting itch online would mean running
your own relay, or accepting that some players can't host.

**Windows is the main platform, which changes three things here.** Windows Firewall prompts on a
game's first listening socket, so hosting needs to expect that prompt. Linux stays a real target,
so a Steamworks binding has to build for both. And Windows' coarse timers may slow the socket
thread's tick, which is unmeasured.

Verify the Steam and NAT claims here against current documentation when this phase starts.
They were written from general knowledge, not checked for this plan.

---

## 9. Testing

The aim is the same as elsewhere in this repo: a test that can fail for the right reason.

- **`SimulatedTransport`** makes network conditions seeded and reproducible, so a failure
  can be replayed from a test. It sits below the reliability layer and drives the real Rust
  core, so tests exercise the code that ships. This is the base for everything else.
- **Host and clients in one process**, headless, stepped manually with an explicit clock.
  No sleeps, no real sockets, no socket thread, and fast enough for the normal suite.
- **The socket thread is tested on its own**, on loopback, including a stalled main thread
  and a clean shutdown. It should stay small enough that this is a short suite.
- **These tests need the extension built, and must fail rather than skip without it.**
  `AGENTS.md` records how skipped native suites hid untested code for a long time.
- **Rust fuzzing** of the packet decoder with `cargo-fuzz`, in addition to fuzzing the
  Python decoders.
- **Convergence tests:** after loss stops, client and host agree. Sabotage-check each one
  by breaking the thing it guards.
- **A matrix of conditions:** 0, 50, 100 and 200 ms; 0, 2 and 10% loss; jitter; reordering.
- **Fuzzing:** random and mutated packets at every decoder. Nothing may raise out.
- **Performance guards** in `tests/performance/`, as ratios where possible: encoding stays
  linear, and bandwidth at a given entity count stays bounded.
- **A real UDP smoke test** on loopback in CI, marked integration.

**What these can't prove.** Same as `agent_view` and `audio_capture`: a simulated network
proves the logic. It can't prove how a real connection behaves, or whether it *feels*
good, and an agent can't judge feel. Phases 3 and 5 need real people on real connections.

Add `tools/net_probe.py` so an agent can run two peers under chosen conditions and read
the numbers, as the other tools do for frames and audio.

---

## 10. Documentation to write

- **ADR 0007, networking model**, recording decisions 1-7, why not lockstep, and where the
  Rust line sits. Note ADR 0004 Decision 4 already covers it: a backend, not a store.
- **`docs/systems/networking.md`**, the user guide.
- **`AGENTS.md`**, a short section once something exists to use, including that
  `pyguara.net` is opt-in and its rule about untrusted data.
- **`docs/guides/performance.md`**, with the phase 0 numbers.

---

## 11. Risks and what is still only an estimate

| Claim | Basis | Check in |
| --- | --- | --- |
| Python can pack snapshots in budget | **Measured:** 3.2% of a frame at 500 entities, with real reads, on a constructed horde | Confirm on a real game, phase 2 |
| A Rust thread keeps the connection steady through Python stalls | Follows from releasing the GIL, not yet built or measured | Phase 1 |
| `renet` and `renetcode` are safe to expose | **Measured with the pre-filter of section 3:** 0 panics from 1.5M datagrams. Fuzzing can't prove absence, so `catch_unwind` stays as a backstop, and invites keep strangers off the path | Phase 1 fuzz test, kept in the suite |
| The crates build on all five wheel platforms | Inferred: no C in the dependency tree | Phase 1 |
| 20 Hz and 100 ms of interpolation feels fine | Common practice, not tested here | Phase 3 |
| A host can simulate, render and send at once | **Unknown.** #334's UI upload is already about 12 ms at 1080p | Phase 2 |
| Home upload can carry 3 guests | Estimate from section 3: 2.9 Mbit/s plain, about 1.3 with deltas, at 500 entities | Phase 5 |
| Clients can generate levels from a seed | Plausible since #324, untested across platforms; hence the hash and fallback | Phase 5 |
| Character movement can be replayed alone | **Measured: yes**, bit-exact against walls, for top-down. Corrections near enemies are expected | How it feels: phase 3 |

If the host can't keep up, the options in order are: lower the enemy cap, simulate at a
lower rate than 60 Hz, then price native replication with `tools/price_native_boundary.py`
as ADR 0004 requires. The transport is native by decision; nothing above the line moves
below it without that measurement.

**Open issues that interact with this:** #334 (GL UI cost on the host), #73 (input
buffering, which should sit before the command layer), #58 (replay; a session recording
format isn't part of this plan).

---

## 12. Questions that change this plan

Answered by the owner on 2026-11-01:

| Question | Answer | What it changes |
| --- | --- | --- |
| Player count | **4** | The designed case. 3 guests, as section 3 assumed |
| Joining mid-run | **No** | Admission closes at run start. No full world transfer |
| Whose progression | **Host: town and meta. Each player: their character** | Section 6, "Who owns what" |
| Drops | **Independent per player** | Section 6, "Drops are per player" |
| Operating systems | **Windows first, Linux second** | Windows must be tested, not only built |

Answered by the owner later the same day:

| Question | Answer | What it changes |
| --- | --- | --- |
| Which store | **Steam** | `SteamTransport` is the release path, and needs no relay of our own. Direct IP stays for development |
| Can a dropped player return | **Not at first, but plan to add it** | See below |
| What survives an abrupt end | **Guests keep what they earned**, saved as events arrive, without hurting performance | `QuickSaver` does this. Character events call `request`, and a run's end calls `flush` |
| Reference games | **Ravenswatch and Heroes of Hammerwatch** | See below |
| `Application.step` hooks | **Approved** | Phase 2 |
| Design choices in `.claude/decision-log.md` | **Approved** | None |

**Keep rejoining possible.** It isn't built now, but these keep the door open: replication has a
`add_peer` that sends everything a newcomer needs, player slots outlive a connection, and character
state doesn't live only in the connection. When it is added, a timed window fits better than an
open door: Heroes of Hammerwatch players [asked for one](https://steamcommunity.com/app/677120/discussions/0/2650805212049309026).

### What the reference games tell us

Checked against what's public on 2026-11-01. **No source was found for either game's actual netcode**,
so this plan doesn't claim to match it. What's usable:

- **Heroes of Hammerwatch has this exact save model**: [town progress for the host only, and character
  progress per player](https://www.co-optimus.com/game/4984/pc/heroes-of-hammerwatch.html).
- **Its "Connection Lost" was [blamed on a map-loading race](https://steamcommunity.com/app/677120/discussions/0/1651043958629398058)**,
  in an unofficial player report from 2018. So the scene-change barrier in phase 5 matters: nobody
  plays on until every player has finished loading, and a slow loader must not time out.
- **Ravenswatch players report [lobbies stuck on "wait", and "peer has left"](https://steamcommunity.com/app/2071280/discussions/0/3828663748262160134/?l=danish)**,
  and it [moved connection handling to Epic Online Services](https://gonintendo.com/contents/30991-ravenswatch-dark-tales-update-trailer).
  Both are reasons to treat lobby states as carefully as gameplay, and to always tell a player why
  something failed. Phase 1's join-deadlock fix and refusal messages are that kind of work.
- **Both support 4 players**, which matches this plan. Both are listed with drop-in, which this plan
  deliberately doesn't do yet.
