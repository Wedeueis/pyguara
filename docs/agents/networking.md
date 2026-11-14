# Networking

Moved out of `AGENTS.md` on 2026-11-14, unchanged, so that file stays short
enough to read every session. `AGENTS.md` keeps the rules; this has the
reasons and the detail.

`pyguara.net` is opt-in: a single-player game imports none of it, and it imports
fine with no extension. It is a backend, not a store, so `PYGUARA_NO_NATIVE=1`
does not turn it off. The transport, session, replication, prediction and game
events exist; projectiles are the rest of phase 4 of
`project/backlog/active/network_multiplayer.md`.

**Everything decoded from the network is untrusted, and that includes messages
from an invited player.** The Rust core authenticates packets and survives hostile
ones, but it does not make a value sensible. A decoder bounds-checks lengths, ids
and enums, rejects non-finite floats, and never raises into the frame loop. Never
unpickle network data.

**`renet` and `renetcode` are pinned exactly, because both can be crashed remotely
as shipped**, and `rust/src/net/core.rs` guards the specific versions. Before moving
either, re-read their parsers and run `tests/test_net_hostile.py`. ADR 0007 lists
each problem and its guard.

**Don't test a stall with `time.sleep` or a Python busy loop.** The first releases
the GIL and the second offers it every 5 ms, so neither proves a thread is
independent of Python. And watch round trip past the end of a stall: it only updates
when an ack lands, so held-back acks leave it frozen at a good value. An earlier
version of `tests/integration/test_net_udp.py` passed with the thread deliberately
broken for both reasons.

**A host never accepts a position from a client, only commands**, and one per tick
however many arrive. `velocity_of` runs on untrusted commands on the host, so it has to
limit what it returns. Velocity must be a pure function of the command, or a replay has
nothing to re-run.

```bash
uv run python tools/net_probe.py simulate --latency-ms 50 --loss 0.02
```

**Capture `net_horde` after changing replication:** `tools/agent_view.py net_horde`
draws the host and client side by side over a simulated bad network, with the state
hash counts on screen. Its first capture found a desync that 121 passing tests had
missed, because they all spawned entities after joining rather than before.

A simulated network proves the logic, the way `agent_view` proves the render path.
It cannot show how a real connection behaves, or whether playing over one feels
good. See `docs/guides/network-probe.md`.
