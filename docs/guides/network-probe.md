# Testing a real network path

`tools/net_probe.py` sends what a game session sends, 60 Hz commands, 20 Hz snapshots and a
reliable echo, and reports what arrived. A simulation can't tell you how a real connection
behaves, so run this between two machines.

## Quick check on one machine

```bash
uv run python tools/net_probe.py simulate --latency-ms 50 --jitter-ms 20 --loss 0.05
```

## Between two machines

You need PyGuara checked out on both, with `uv sync` run, and the same commit on each.

On the host:

```bash
uv run python tools/net_probe.py host --port 7777 --public-host <address> --json host.json
```

It prints the exact `join` command for the other machine, invite included. Copy it across
somewhere private, because the invite is the session's key. Each side prints a report of what
it received.

### What address to use

| Situation | `--public-host` | Router changes |
| --- | --- | --- |
| Same home network | The host's LAN address, such as `192.168.0.5` | None |
| Tailscale on both machines | The host's Tailscale address, `100.x.y.z` | None |
| A cheap cloud server as the host | The server's public IP. Open UDP 7777 in its firewall | None |
| A friend's machine, across the internet | Your public IP | Forward **UDP** 7777 to the host |

A cloud server is the simplest real internet path, since it needs no router changes. Tailscale
is nearly as easy, but may relay traffic, so its numbers can look worse than a direct path.
Same-network Wi-Fi is worth running too, for jitter, but it isn't the internet.

If your router's WAN address starts with `100.64`-`100.127`, or differs from what a "what is my
IP" site shows, you're behind carrier-grade NAT and port forwarding can't work.

### If the host runs in WSL2

WSL2 has its own network behind Windows NAT, so another machine can't reach it directly. Either
set `networkingMode=mirrored` in `.wslconfig` and run `wsl --shutdown`, or run the probe's host
side from Windows itself. Allow the UDP port through Windows Firewall either way. Mirrored mode
needs Windows 11.

## Reading the report

| Field | Healthy for this game | What a bad number means |
| --- | --- | --- |
| `link rtt` | Under about 100 ms | The path is long. It's the floor for every interaction |
| `stream loss` | Under about 2% | Above about 5%, expect visible corrections |
| `reordered`, `duplicated` | Rare | Harmless in small numbers, since snapshots carry ticks |
| `arrival jitter` | A few ms over a frame | Sets how much interpolation delay is needed |
| `worst gap` | Under about 200 ms | A stall: Wi-Fi, a saturated uplink, or the machine itself |
| `datagram sizes that arrived` | All six sizes, up to 1200 | A missing large size means the path's MTU is small, and the snapshot size must drop |

Those limits are starting points from common practice, not measurements from this engine.

The `reliable echo` includes frame polling and the socket thread's ticks at both ends, so it
reads about 50 ms higher than `link rtt` even on loopback.

## What to run

Enough to answer the plan's probe 4. Save each side's JSON.

1. **A short check**: `--seconds 60`, to confirm it connects at all.
2. **A long run**: `--seconds 1800`. Long enough to catch periodic stalls and a NAT mapping that
   expires, which a short run won't show.
3. **With something else on the line**: start a large upload on the host during a run. That's
   the normal home-uplink failure.
4. **On Wi-Fi**, if a player would be on it.
5. **A join with the wrong invite**, to confirm it fails with a useful message.

## What it can't tell you

Whether a game feels good. Only people playing can judge that. It also tests one direct path
and says nothing about whether other players' routers will let them host: see section 8 of the
plan.
