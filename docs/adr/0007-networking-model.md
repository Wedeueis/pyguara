# ADR 0007: Networking is a listen server over an authenticated Rust transport

- **Status:** accepted
- **Date:** 2026-11-01
- **Plan:** `project/backlog/active/network_multiplayer.md`, which carries the
  measurements and the phases this ADR only summarises

## Context

The first user is Reclaimer, an online co-op action RPG with hordes and heavy
projectile counts, for about 4 players. One player hosts from their own machine.

## Decisions

**1. A listen server, and the host decides everything.** Clients send input and
display state, predict their own character, and interpolate everyone else.

Lockstep was rejected. It needs bit-identical results across machines, which nothing
has tested for pymunk or for floats across x86 and ARM, and which the Python and
native stores do not give (ADR 0004, Decision 5). Everyone also waits for the slowest
player, and every machine has to run the whole horde.

**2. Rust below the line, Python above it.** Sockets, packets and reliability are
native. Anything that reads or writes ECS components stays Python unless a measurement
earns a port. Moving snapshot encoding to Rust was priced at 1.2-1.9x, because the
component reads are half its cost and cannot move, so it stays in Python.

The reason for the Rust transport is not speed. A thread that never needs the GIL keeps
acknowledging while Python stalls, and memory safety suits parsing data from the
internet.

**3. A backend, not a store.** It has no Python counterpart, so it loads through
`native.require_extension()` and `PYGUARA_NO_NATIVE=1` does not turn it off (ADR 0004,
Decision 4). `pyguara.net` imports cleanly without the extension and fails with a clear
message only when a session starts.

**4. `renet` and `renetcode`, behind a hardening layer.** Both are pure Rust and already
sans-IO. They delivered everything in order on all 200 seeds at up to 40% loss, and they
replace a reliability layer we would otherwise have to write and fuzz. `quinn-proto` was
rejected because `ring` brings C and assembly, which ADR 0006 has so far avoided.

Neither is safe as shipped, and each of these was reproduced against the versions
`Cargo.toml` pins exactly:

| Problem | Who can trigger it | Guard in `rust/src/net/core.rs` |
| --- | --- | --- |
| One datagram with a sequence length over 8 panics `renetcode` | Anyone, before any authentication | `plausible()` |
| One datagram too short for its MAC panics `renetcode` | Anyone, before any authentication | `plausible()` |
| Slices of one message claiming different `num_slices` panic `renet` | Someone holding the invite | `catch_unwind`, dropping that peer |
| One malformed packet disconnects a peer in bare `renet` | Anyone, if `renet` were exposed | Only `renetcode`-authenticated bytes reach it |
| A lost first keepalive deadlocks a join while traffic flows: the host admits a player whose client times out. 19 of 100 seeded joins at 20% loss | The network itself | The client confirms, and the host holds traffic and reports nothing until it does |
| A message the sender accepts can overflow the receiver, which charges whole slices against the same limit and disconnects | Any large send | Reliable sends only fill half a channel's limit |
| A reliable message overtakes the session's welcome, on another channel, and is dropped: a client could join and never see 200 existing enemies | Loss during a join | `ClientSession` holds early messages until it is admitted |

These were not reported upstream, by the owner's decision. **So a new version of either
crate needs its parsers re-read and `tests/test_net_hostile.py` re-run**, and a fix cannot
be assumed.

**5. Joining takes an invite, carrying a random 256-bit session key.** A client mints its
own connect token under that key, so only invited players can connect and traffic is
encrypted. An all-zero key, which is what `renetcode`'s Unsecure mode uses, is refused.

- The token's server address is a fixed placeholder on both sides. Secure mode checks it
  against the host's public addresses, and a host behind NAT does not know its own.
- Token time counts from zero with a 10-year expiry, so no wall clock is compared and a
  guest's wrong clock cannot refuse them. A replayed token gains nothing: its keys are
  sealed inside, and one token cannot be used from a second address.

There is no forward secrecy: anyone holding the invite who also recorded the handshake can
read that session. So an invite is a secret, and a new one is made per session.

**6. Only authenticated traffic counts against a peer.** A UDP source address is spoofable,
so throttling or kicking by address before the MAC check would let a stranger remove a real
player with forged packets. Unauthenticated datagrams share one global budget, which can
delay a joiner and nothing else.

**7. A sans-IO core under one mutex.** The core takes datagrams and a time step, and returns
datagrams and messages, with no socket, thread or clock inside. A seeded in-process network
can therefore drive the code that ships. The socket thread and Python share it through a
`Mutex` held for microseconds, rather than through queues in each direction.

**8. Snapshots are complete states, read directly from components.** No movement system calls
`notify_component_changed`, so replication can't rely on it. A lost snapshot costs nothing, because
the next one is whole, which gives a client convergence for free. Delta encoding stays out until a
measurement asks for it: at 500 entities a client costs 0.88 Mbit/s.

**9. Spawns and despawns run on the delayed timeline.** They are applied when the render clock
reaches their tick, in order, so things appear and vanish in step with the motion around them. A
spawn that has arrived but not been applied keeps its records.

**10. Visibility is per player, decided by `Replicated.owner`.** A drop's entity is never sent to
anyone but its owner, which saves bandwidth and leaves nothing to find in a hacked client.

## Consequences

- Protocol changes need `make native`, and a stale build is easy to miss, so `pyguara.net`
  compares a protocol version with the extension and names `make native` in the error.
- A joining player waits about one round trip longer, for the confirmation.
- A reliable channel's usable backlog is half its configured limit.
- A game message picks up frame-rate latency on top of the network's: on loopback, a
  reliable echo takes 50-67 ms against a 7 ms link round trip, from polling once a frame and
  the socket thread's 8 ms tick at each end. Phase 3 should measure what that does to input,
  and the thread could flush a send at once if it matters.
- Prediction and the rest are later phases of the plan.
