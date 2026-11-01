#!/usr/bin/env python3
"""Measure a network path, or a simulated one, the way a game would load it.

An agent cannot play a game, and a person cannot read a packet trace, so this
sends what a session sends and reports numbers: 60 Hz commands from the client,
20 Hz snapshots from the host, and a reliable echo for true round trip. It uses
the real transport, so a run also exercises everything a session depends on.

On one machine, with chosen conditions:

    uv run python tools/net_probe.py simulate --latency-ms 50 --loss 0.02

Between two machines, which is what a simulation cannot stand in for:

    uv run python tools/net_probe.py host --port 7777 --public-host 203.0.113.5
    uv run python tools/net_probe.py join "pyguara://203.0.113.5:7777#..."

Each side reports what it received, so read both reports. Pass `--json FILE` to
keep one. See `docs/guides/network-probe.md` for what to run and how to read it.
"""

from __future__ import annotations

import argparse
import json
import secrets
import struct
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyguara.net import (  # noqa: E402
    Channel,
    ClientSession,
    HostSession,
    Invite,
    Joined,
    Left,
    LinkConditions,
    MessageReceived,
    PlayerJoined,
    PlayerLeft,
    Refused,
    SessionFailed,
    SimulatedNetwork,
    UdpTransport,
    Versions,
)

VERSIONS = Versions("net_probe", "1")
FRAME = 1 / 60
COMMAND_BYTES = 64
SNAPSHOT_BYTES = 1100
SNAPSHOT_EVERY_FRAMES = 3
ECHO_EVERY_FRAMES = 30
SIZE_PROBE_EVERY_FRAMES = 15
# Up to `renet`'s slice size, which is the largest that stays one datagram.
SIZE_PROBES = (600, 900, 1000, 1100, 1150, 1200)

_HEADER = struct.Struct("<BId")
_STREAM, _SIZE_PROBE, _ECHO_REQUEST, _ECHO_REPLY = range(4)


@dataclass
class Report:
    """What one side measured about the traffic it received."""

    role: str
    seconds: float = 0.0
    expected_stream: int = 0
    received_stream: int = 0
    duplicates: int = 0
    reordered: int = 0
    loss: float = 0.0
    arrival_jitter_ms: float = 0.0
    worst_gap_ms: float = 0.0
    echo_round_trips: int = 0
    echo_rtt_ms_median: float = 0.0
    echo_rtt_ms_p95: float = 0.0
    echo_rtt_ms_worst: float = 0.0
    link_rtt_ms: float = 0.0
    link_packet_loss: float = 0.0
    send_kbit_per_second: float = 0.0
    size_probes_received: dict[str, int] = field(default_factory=dict)
    disconnects: list[str] = field(default_factory=list)
    guard_counters: dict[str, int] = field(default_factory=dict)


class Meter:
    """Turns received probe traffic into a `Report`, trusting none of it."""

    def __init__(self, role: str) -> None:
        self.report = Report(role)
        self._seen: set[int] = set()
        self._highest = -1
        self._last_arrival: float | None = None
        self._gaps: list[float] = []
        self._rtts: list[float] = []

    def on_message(self, now: float, data: bytes, reply: object) -> None:
        """Account for one message.

        Args:
            now: This machine's clock.
            data: The message. Malformed ones are ignored.
            reply: Called with bytes to send an echo back reliably.
        """
        if len(data) < _HEADER.size:
            return
        kind, sequence, sent_at = _HEADER.unpack_from(data)
        if kind == _STREAM:
            self._on_stream(now, sequence)
        elif kind == _SIZE_PROBE:
            sizes = self.report.size_probes_received
            sizes[str(len(data))] = sizes.get(str(len(data)), 0) + 1
        elif kind == _ECHO_REQUEST:
            reply(_HEADER.pack(_ECHO_REPLY, sequence, sent_at))  # type: ignore[operator]
        elif kind == _ECHO_REPLY:
            self._rtts.append((now - sent_at) * 1000)

    def _on_stream(self, now: float, sequence: int) -> None:
        if sequence in self._seen:
            self.report.duplicates += 1
            return
        self._seen.add(sequence)
        if sequence < self._highest:
            self.report.reordered += 1
        self._highest = max(self._highest, sequence)
        if self._last_arrival is not None:
            self._gaps.append((now - self._last_arrival) * 1000)
        self._last_arrival = now

    def finish(self, seconds: float, transport: object, peer: int | None) -> Report:
        """Fill in the totals and return the report."""
        report = self.report
        report.seconds = round(seconds, 1)
        report.received_stream = len(self._seen)
        report.expected_stream = self._highest + 1
        if report.expected_stream:
            report.loss = round(1 - len(self._seen) / report.expected_stream, 4)
        if self._gaps:
            ordered = sorted(self._gaps)
            median = ordered[len(ordered) // 2]
            report.arrival_jitter_ms = round(
                sum(abs(g - median) for g in ordered) / len(ordered), 2
            )
            report.worst_gap_ms = round(ordered[-1], 1)
        if self._rtts:
            ordered = sorted(self._rtts)
            report.echo_round_trips = len(ordered)
            report.echo_rtt_ms_median = round(ordered[len(ordered) // 2], 1)
            report.echo_rtt_ms_p95 = round(ordered[int(len(ordered) * 0.95)], 1)
            report.echo_rtt_ms_worst = round(ordered[-1], 1)
        if peer is not None:
            stats = transport.stats(peer)  # type: ignore[attr-defined]
            if stats is not None:
                report.link_rtt_ms = round(stats.rtt * 1000, 1)
                report.link_packet_loss = round(stats.packet_loss, 4)
                report.send_kbit_per_second = round(
                    stats.bytes_sent_per_second * 8 / 1000, 1
                )
        report.guard_counters = transport.counters()  # type: ignore[attr-defined]
        return report


def _stream_message(sequence: int, now: float, size: int) -> bytes:
    return _HEADER.pack(_STREAM, sequence, now).ljust(size, b"\0")


class Sender:
    """Sends what a session would, from one side, once a frame."""

    def __init__(self, send: object, channel: Channel, size: int, every: int) -> None:
        self._send = send
        self._channel = channel
        self._size = size
        self._every = every
        self._frame = 0
        self._sequence = 0
        self._echo = 0

    def frame(self, now: float) -> None:
        """Advance a frame, and send whatever falls due."""
        self._frame += 1
        send = self._send
        if self._frame % self._every == 0:
            message = _stream_message(self._sequence, now, self._size)
            send(self._channel, message)  # type: ignore[operator]
            self._sequence += 1
        if self._frame % ECHO_EVERY_FRAMES == 0:
            echo = _HEADER.pack(_ECHO_REQUEST, self._echo, now)
            send(Channel.EVENTS, echo)  # type: ignore[operator]
            self._echo += 1
        if self._frame % SIZE_PROBE_EVERY_FRAMES == 0:
            size = SIZE_PROBES[
                (self._frame // SIZE_PROBE_EVERY_FRAMES) % len(SIZE_PROBES)
            ]
            probe = _HEADER.pack(_SIZE_PROBE, 0, now).ljust(size, b"\0")
            send(self._channel, probe)  # type: ignore[operator]


def _print(report: Report, path: str | None) -> None:
    print(f"\n--- {report.role} received ---")
    print(
        f"  stream: {report.received_stream}/{report.expected_stream} "
        f"(loss {report.loss:.2%}), {report.reordered} reordered, "
        f"{report.duplicates} duplicated"
    )
    print(
        f"  arrival: jitter {report.arrival_jitter_ms} ms, "
        f"worst gap {report.worst_gap_ms} ms"
    )
    print(
        f"  reliable echo round trip: median {report.echo_rtt_ms_median} ms, "
        f"p95 {report.echo_rtt_ms_p95} ms, worst {report.echo_rtt_ms_worst} ms "
        f"({report.echo_round_trips} samples)"
    )
    print(f"  link: rtt {report.link_rtt_ms} ms, loss {report.link_packet_loss:.2%}")
    print(f"  sending: {report.send_kbit_per_second} kbit/s")
    print(f"  datagram sizes that arrived: {report.size_probes_received or 'none'}")
    if report.disconnects:
        print(f"  disconnects: {report.disconnects}")
    print(f"  guards: {report.guard_counters}")
    if path:
        Path(path).write_text(json.dumps(asdict(report), indent=2))
        print(f"  wrote {path}")


def run_host(args: argparse.Namespace) -> int:
    """Host, wait for one player, then measure for `--seconds`."""
    key = secrets.token_bytes(32)
    transport = UdpTransport.host(key, args.port)
    port = int(transport.local_address.rsplit(":", 1)[1])
    invite = Invite(args.public_host, port, key)
    print(f"Listening on UDP port {port}. On the other machine, run:\n")
    print(f'  uv run python tools/net_probe.py join "{invite}"\n', flush=True)
    session = HostSession(transport, VERSIONS)
    meter = Meter("host")
    player: int | None = None
    sender: Sender | None = None
    began: float | None = None
    deadline = time.monotonic() + args.wait

    def send(channel: Channel, data: bytes) -> None:
        if player is not None:
            session.send(player, channel, data)

    def reply(data: bytes) -> None:
        send(Channel.EVENTS, data)

    try:
        while True:
            frame_start = time.monotonic()
            now = time.perf_counter()
            for event in session.poll():
                if isinstance(event, PlayerJoined) and player is None:
                    player = event.peer
                    began = frame_start
                    sender = Sender(
                        send, Channel.SNAPSHOT, SNAPSHOT_BYTES, SNAPSHOT_EVERY_FRAMES
                    )
                    print(f"Player joined. Measuring for {args.seconds} s.", flush=True)
                elif isinstance(event, MessageReceived) and sender is not None:
                    meter.on_message(now, event.data, reply)
                elif isinstance(event, PlayerLeft):
                    meter.report.disconnects.append(event.reason)
                    print(f"Player left: {event.reason}", flush=True)
                    return _finish_host(
                        meter, began, transport, None, args, frame_start
                    )
                elif isinstance(event, SessionFailed):
                    print(f"FAILED: {event.reason}", flush=True)
                    return 1
            if began is None and frame_start > deadline:
                print("Nobody joined. Is the port reachable from the other machine?")
                return 1
            if began is not None and frame_start - began > args.seconds + 2:
                return _finish_host(meter, began, transport, player, args, frame_start)
            if sender is not None:
                sender.frame(now)
            time.sleep(max(0.0, FRAME - (time.monotonic() - frame_start)))
    finally:
        session.close()


def _finish_host(
    meter: Meter,
    began: float | None,
    transport: UdpTransport,
    player: int | None,
    args: argparse.Namespace,
    now: float,
) -> int:
    _print(
        meter.finish(now - (began if began is not None else now), transport, player),
        args.json,
    )
    return 0


def run_join(args: argparse.Namespace) -> int:
    """Join, and measure for `--seconds` or until the host ends it."""
    invite = Invite.parse(args.invite)
    transport = UdpTransport.client(
        invite.key, secrets.randbits(63), invite.host, invite.port, VERSIONS.encode()
    )
    print(f"Connecting to {invite.host}:{invite.port} ...", flush=True)
    session = ClientSession(transport)
    meter = Meter("client")
    began: float | None = None
    sender: Sender | None = None

    def send(channel: Channel, data: bytes) -> None:
        session.send(channel, data)

    def reply(data: bytes) -> None:
        session.send(Channel.EVENTS, data)

    try:
        while True:
            frame_start = time.monotonic()
            now = time.perf_counter()
            for event in session.poll():
                if isinstance(event, Joined):
                    began = frame_start
                    sender = Sender(send, Channel.COMMANDS, COMMAND_BYTES, 1)
                    print(f"Joined. Measuring for {args.seconds} s.", flush=True)
                elif isinstance(event, MessageReceived):
                    meter.on_message(now, event.data, reply)
                elif isinstance(event, Refused | Left | SessionFailed):
                    print(f"Ended: {event.reason}", flush=True)
                    if began is None:
                        return 1
                    meter.report.disconnects.append(event.reason)
                    _print(
                        meter.finish(frame_start - began, transport, None), args.json
                    )
                    return 0
            if began is not None and frame_start - began > args.seconds:
                _print(meter.finish(frame_start - began, transport, 0), args.json)
                return 0
            if sender is not None:
                sender.frame(now)
            time.sleep(max(0.0, FRAME - (time.monotonic() - frame_start)))
    finally:
        session.close()


def run_simulate(args: argparse.Namespace) -> int:
    """Run both sides in this process, on a seeded network."""
    network = SimulatedNetwork(
        seed=args.seed,
        conditions=LinkConditions(
            latency=args.latency_ms / 1000,
            jitter=args.jitter_ms / 1000,
            loss=args.loss,
            duplicate=args.duplicate,
            reorder=args.reorder,
        ),
    )
    key = secrets.token_bytes(32)
    host_transport = network.add_host(key)
    client_transport = network.add_client(
        key, network.address_of(host_transport), VERSIONS.encode()
    )
    host = HostSession(host_transport, VERSIONS)
    client = ClientSession(client_transport)
    host_meter = Meter("host")
    client_meter = Meter("client")
    player = None
    host_sender = client_sender = None
    frames = 0
    limit = round(args.seconds / FRAME)
    joined_at = None

    def host_send(channel: Channel, data: bytes) -> None:
        if player is not None:
            host.send(player, channel, data)

    def host_reply(data: bytes) -> None:
        host_send(Channel.EVENTS, data)

    def client_reply(data: bytes) -> None:
        client.send(Channel.EVENTS, data)

    while frames < limit:
        network.advance(FRAME)
        now = network.now
        for event in host.poll():
            if isinstance(event, PlayerJoined):
                player = event.peer
                host_sender = Sender(
                    host_send,
                    Channel.SNAPSHOT,
                    SNAPSHOT_BYTES,
                    SNAPSHOT_EVERY_FRAMES,
                )
            elif isinstance(event, MessageReceived):
                host_meter.on_message(now, event.data, host_reply)
        for event in client.poll():
            if isinstance(event, Joined):
                joined_at = now
                client_sender = Sender(client.send, Channel.COMMANDS, COMMAND_BYTES, 1)
            elif isinstance(event, MessageReceived):
                client_meter.on_message(now, event.data, client_reply)
            elif isinstance(event, Refused | Left | SessionFailed):
                print(f"Ended: {event.reason}")
                return 1
        if host_sender is not None:
            host_sender.frame(now)
        if client_sender is not None:
            client_sender.frame(now)
        if joined_at is not None:
            frames += 1
        elif network.now > 30:
            print("Never joined.")
            return 1
    print(f"Joined after {joined_at:.2f} s of simulated time.")
    _print(host_meter.finish(args.seconds, host_transport, player), None)
    _print(client_meter.finish(args.seconds, client_transport, 0), args.json)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the command line and run."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    host = commands.add_parser("host", help="host, and print an invite")
    host.add_argument("--port", type=int, default=7777)
    host.add_argument(
        "--public-host",
        default="127.0.0.1",
        help="the address the other machine will reach this one at",
    )
    host.add_argument("--seconds", type=float, default=60.0)
    host.add_argument("--wait", type=float, default=600.0, help="how long to wait")
    host.add_argument("--json", help="also write the report here")
    host.set_defaults(run=run_host)

    join = commands.add_parser("join", help="join using an invite")
    join.add_argument("invite")
    join.add_argument("--seconds", type=float, default=60.0)
    join.add_argument("--json", help="also write the report here")
    join.set_defaults(run=run_join)

    simulate = commands.add_parser("simulate", help="both sides, on a seeded network")
    simulate.add_argument("--latency-ms", type=float, default=50.0)
    simulate.add_argument("--jitter-ms", type=float, default=10.0)
    simulate.add_argument("--loss", type=float, default=0.02)
    simulate.add_argument("--duplicate", type=float, default=0.0)
    simulate.add_argument("--reorder", type=float, default=0.0)
    simulate.add_argument("--seconds", type=float, default=10.0)
    simulate.add_argument("--seed", type=int, default=1)
    simulate.add_argument("--json", help="also write the client's report here")
    simulate.set_defaults(run=run_simulate)

    args = parser.parse_args(argv)
    return int(args.run(args))


if __name__ == "__main__":
    sys.exit(main())
