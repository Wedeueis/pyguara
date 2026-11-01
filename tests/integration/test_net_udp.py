"""The real socket and its thread, on loopback.

The sans-IO suites cover the logic. This covers what they cannot: a real UDP
path between two processes, and the thread keeping the connection alive while
Python is not running.
"""

from __future__ import annotations

import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from pyguara.net import (
    Channel,
    HostSession,
    Invite,
    MessageReceived,
    PlayerJoined,
    PlayerLeft,
    UdpTransport,
    Versions,
)
from pyguara.net.session import SessionEvent
from pyguara.net.transport import HOST_PEER, MessageDelivered, PeerConnected

pytestmark = pytest.mark.integration

PEER_SCRIPT = str(Path(__file__).parent / "net_peer.py")
VERSIONS = Versions("test", "test")


def host_on_loopback() -> tuple[UdpTransport, Invite]:
    key = secrets.token_bytes(32)
    transport = UdpTransport.host(key, 0, bind_ip="127.0.0.1")
    port = int(transport.local_address.rsplit(":", 1)[1])
    return transport, Invite("127.0.0.1", port, key)


def wait_for(condition: object, seconds: float = 10.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():  # type: ignore[operator]
            return
        time.sleep(0.002)
    raise AssertionError("timed out")


def test_host_and_client_exchange_messages_over_loopback() -> None:
    host, invite = host_on_loopback()
    client = UdpTransport.client(invite.key, 7, invite.host, invite.port)
    events: list[object] = []

    def heard(kind: type) -> bool:
        events.extend(host.poll())
        return any(isinstance(e, kind) for e in events)

    wait_for(lambda: heard(PeerConnected))
    wait_for(lambda: client.send(HOST_PEER, Channel.EVENTS, b"hello"))
    wait_for(lambda: heard(MessageDelivered))

    message = next(e for e in events if isinstance(e, MessageDelivered))
    assert message.data == b"hello"
    assert host.endpoint.is_running()

    client.close()
    host.close()
    assert not host.endpoint.is_running()
    assert not client.endpoint.is_running()


def test_a_large_message_crosses_a_real_socket_intact() -> None:
    host, invite = host_on_loopback()
    client = UdpTransport.client(invite.key, 7, invite.host, invite.port)
    wait_for(lambda: bool(host.poll()))
    blob = secrets.token_bytes(2 * 1024 * 1024)
    wait_for(lambda: host.send(7, Channel.LEVEL, blob))
    received: list[bytes] = []

    def arrived() -> bool:
        received.extend(
            e.data for e in client.poll() if isinstance(e, MessageDelivered)
        )
        return bool(received)

    wait_for(arrived, seconds=20)

    assert received == [blob]
    client.close()
    host.close()


def test_a_second_process_connects_and_exchanges_messages() -> None:
    host_transport, invite = host_on_loopback()
    host = HostSession(host_transport, VERSIONS)
    peer = subprocess.Popen(  # noqa: S603
        [sys.executable, PEER_SCRIPT, str(invite), "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        events: list[SessionEvent] = []

        def heard(kind: type) -> bool:
            events.extend(host.poll())
            return any(isinstance(e, kind) for e in events)

        wait_for(lambda: heard(PlayerJoined), seconds=20)
        player = next(e.peer for e in events if isinstance(e, PlayerJoined))
        for number in range(50):
            assert host.send(player, Channel.EVENTS, b"%d" % number)
        assert host.send(player, Channel.EVENTS, b"done")

        wait_for(lambda: heard(MessageReceived), seconds=10)
        assert any(
            isinstance(e, MessageReceived) and e.data == b"thanks" for e in events
        )
        output, errors = peer.communicate(timeout=15)
        assert peer.returncode == 0, errors
        assert "received 51" in output
        wait_for(lambda: heard(PlayerLeft), seconds=2)
    finally:
        peer.kill()
        host.close()


def test_the_peer_keeps_acknowledging_while_python_is_stalled() -> None:
    """The plan's claim about the thread, measured from the other side.

    Merely staying connected would prove nothing: a 2-second stall is well inside
    the 10-second timeout even with no thread at all. So the host sends reliable
    messages throughout and watches the measured round trip, until after the stall
    ends too: it only updates when an ack lands, so acks held back would leave it
    frozen at a good value for the whole stall and show up only when they finally
    arrive, two seconds old.
    """
    host_transport, invite = host_on_loopback()
    host = HostSession(host_transport, VERSIONS)
    peer = subprocess.Popen(  # noqa: S603
        [sys.executable, PEER_SCRIPT, str(invite), "2.0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines: list[str] = []
    stalling = threading.Event()
    resumed = threading.Event()

    def read_output() -> None:
        assert peer.stdout is not None
        for line in peer.stdout:
            lines.append(line.strip())
            if "stalling" in line:
                stalling.set()
            if "resumed" in line:
                resumed.set()

    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    try:
        events: list[SessionEvent] = []

        def joined() -> bool:
            events.extend(host.poll())
            return any(isinstance(e, PlayerJoined) for e in events)

        wait_for(joined, seconds=20)
        player = next(e.peer for e in events if isinstance(e, PlayerJoined))
        assert stalling.wait(timeout=10)

        sent = 0
        worst_rtt = 0.0
        began = time.monotonic()
        resumed_at = None
        while time.monotonic() - began < 10:
            now = time.monotonic()
            if resumed_at is None and resumed.is_set():
                resumed_at = now
            if resumed_at is not None and now - resumed_at > 0.5:
                break
            assert host.send(player, Channel.EVENTS, bytes(500))
            sent += 1
            host.poll()
            stats = host_transport.stats(player)
            assert stats is not None
            # Skip the start: the smoothed values are still settling.
            if now - began > 0.5:
                worst_rtt = max(worst_rtt, stats.rtt)
            time.sleep(0.01)

        assert resumed_at is not None
        assert resumed_at - began > 1.5, "the stall did not happen"
        assert worst_rtt < 0.2, f"acks waited on Python: rtt {worst_rtt:.3f}s"
        assert player in host.players

        assert host.send(player, Channel.EVENTS, b"done")
        peer.wait(timeout=15)
        reader.join(timeout=5)
        assert peer.returncode == 0, lines
        assert f"received {sent + 1}" in lines
    finally:
        peer.kill()
        host.close()


def test_closing_is_prompt_and_the_other_side_hears_at_once() -> None:
    host, invite = host_on_loopback()
    client = UdpTransport.client(invite.key, 7, invite.host, invite.port)
    wait_for(lambda: bool(host.poll()))
    time.sleep(0.05)

    began = time.perf_counter()
    client.close()
    assert time.perf_counter() - began < 0.5

    events: list[object] = []

    def gone() -> bool:
        events.extend(host.poll())
        return any(type(e).__name__ == "PeerDisconnected" for e in events)

    wait_for(gone, seconds=1.0)
    host.close()


def test_dropping_a_transport_without_closing_stops_its_thread() -> None:
    host, _ = host_on_loopback()
    endpoint = host.endpoint
    assert endpoint.is_running()
    del host
    endpoint.close()

    assert not endpoint.is_running()


def test_the_driving_calls_are_refused_once_a_thread_is_driving() -> None:
    host, _ = host_on_loopback()
    try:
        with pytest.raises(RuntimeError, match="socket thread"):
            host.endpoint.tick(0.01)
        with pytest.raises(RuntimeError, match="socket thread"):
            host.endpoint.receive("127.0.0.1:1", b"x")
    finally:
        host.close()


def test_the_port_being_taken_is_an_oserror() -> None:
    host, invite = host_on_loopback()
    try:
        with pytest.raises(OSError):
            UdpTransport.host(invite.key, invite.port, bind_ip="127.0.0.1")
    finally:
        host.close()


def test_garbage_on_the_real_socket_does_not_kill_the_thread() -> None:
    import random
    import socket

    host, invite = host_on_loopback()
    client = UdpTransport.client(invite.key, 7, invite.host, invite.port)
    wait_for(lambda: bool(host.poll()))
    attacker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rng = random.Random(1)
    for _ in range(3000):
        length = rng.choice((0, 1, 18, 19, 64, 1400, 1401, 2047))
        body = bytearray(rng.randbytes(length))
        if body:
            body[0] = rng.randrange(256)
        attacker.sendto(bytes(body), ("127.0.0.1", invite.port))
    attacker.close()

    assert host.endpoint.is_running()
    assert host.counters()["panics"] == 0
    assert host.counters()["implausible"] > 0
    wait_for(lambda: host.send(7, Channel.EVENTS, b"alive"))
    received: list[bytes] = []

    def arrived() -> bool:
        received.extend(
            e.data for e in client.poll() if isinstance(e, MessageDelivered)
        )
        return b"alive" in received

    wait_for(arrived, seconds=3)
    client.close()
    host.close()


def test_the_probe_tool_runs_a_simulated_session() -> None:
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "tools/net_probe.py",
            "simulate",
            "--seconds",
            "3",
            "--loss",
            "0.05",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "host received" in result.stdout
    assert "client received" in result.stdout
    assert "'panics': 0" in result.stdout
