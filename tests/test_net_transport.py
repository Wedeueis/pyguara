"""The transport, through a seeded network, on the real Rust core.

These fail rather than skip without the extension: `AGENTS.md` records how
skipped native suites hid untested code for a long time.
"""

from __future__ import annotations

import secrets
import struct

import pytest

from pyguara.net import Channel, LinkConditions, SimulatedNetwork
from pyguara.net.transport import (
    HOST_PEER,
    MessageDelivered,
    NativeTransport,
    PeerConnected,
    PeerDisconnected,
    TransportEvent,
)

DT = 1 / 60
BAD_NETWORK = LinkConditions(
    latency=0.05, jitter=0.03, loss=0.2, duplicate=0.02, reorder=0.05
)


def connected_pair(
    network: SimulatedNetwork,
) -> tuple[NativeTransport, NativeTransport, int]:
    """Connect a host and a client, and return them with the client's peer id."""
    key = secrets.token_bytes(32)
    host = network.add_host(key)
    client = network.add_client(key, network.address_of(host))
    peer = None
    client_up = False
    for _ in range(60 * 30):
        network.advance(DT)
        for event in host.poll():
            if isinstance(event, PeerConnected):
                peer = event.peer
        for event in client.poll():
            client_up = client_up or isinstance(event, PeerConnected)
        if peer is not None and client_up:
            return host, client, peer
    raise AssertionError("never connected")


def run_collecting(
    network: SimulatedNetwork, endpoint: NativeTransport, seconds: float
) -> list[TransportEvent]:
    """Advance the network and return what one endpoint heard."""
    events: list[TransportEvent] = []
    for _ in range(round(seconds / DT)):
        network.advance(DT)
        events.extend(endpoint.poll())
    return events


def bodies(events: list[TransportEvent], channel: Channel) -> list[bytes]:
    """The payloads delivered on one channel, in order."""
    return [
        e.data
        for e in events
        if isinstance(e, MessageDelivered) and e.channel == channel
    ]


@pytest.mark.parametrize("seed", range(40))
def test_reliable_stream_arrives_complete_and_in_order_at_20_percent_loss(
    seed: int,
) -> None:
    network = SimulatedNetwork(seed=seed, conditions=BAD_NETWORK)
    host, client, peer = connected_pair(network)
    sent = [struct.pack("<I", i) for i in range(300)]
    for message in sent:
        assert host.send(peer, Channel.EVENTS, message)

    received = bodies(run_collecting(network, client, 15.0), Channel.EVENTS)

    assert received == sent


@pytest.mark.parametrize("seed", range(10))
def test_reliable_stream_from_client_to_host_too(seed: int) -> None:
    network = SimulatedNetwork(seed=seed, conditions=BAD_NETWORK)
    host, client, _ = connected_pair(network)
    sent = [struct.pack("<I", i) for i in range(200)]
    for message in sent:
        assert client.send(HOST_PEER, Channel.EVENTS, message)

    assert bodies(run_collecting(network, host, 15.0), Channel.EVENTS) == sent


@pytest.mark.parametrize("seed", range(10))
def test_large_message_is_sliced_and_reassembled_under_loss(seed: int) -> None:
    network = SimulatedNetwork(seed=seed, conditions=BAD_NETWORK)
    host, client, peer = connected_pair(network)
    blob = secrets.token_bytes(256 * 1024)
    assert host.send(peer, Channel.LEVEL, blob)

    assert bodies(run_collecting(network, client, 20.0), Channel.LEVEL) == [blob]


def test_channels_do_not_block_each_other() -> None:
    network = SimulatedNetwork(seed=3)
    host, client, peer = connected_pair(network)
    assert host.send(peer, Channel.LEVEL, bytes(4 * 1024 * 1024))
    assert host.send(peer, Channel.EVENTS, b"urgent")
    network.advance(DT)
    network.advance(DT)

    events = client.poll()

    assert bodies(events, Channel.EVENTS) == [b"urgent"]
    assert bodies(events, Channel.LEVEL) == []


def test_unreliable_loses_messages_but_never_corrupts_them() -> None:
    network = SimulatedNetwork(seed=5, conditions=LinkConditions(loss=0.3))
    host, client, peer = connected_pair(network)
    events: list[TransportEvent] = []
    for tick in range(300):
        host.send(peer, Channel.SNAPSHOT, struct.pack("<I", tick) * 100)
        network.advance(DT)
        events.extend(client.poll())
    events.extend(run_collecting(network, client, 0.5))

    received = bodies(events, Channel.SNAPSHOT)

    assert 100 < len(received) < 300
    for message in received:
        assert message == message[:4] * 100


def test_same_seed_gives_the_same_delivery_pattern() -> None:
    """A failure has to replay from its seed, despite the core's random keys."""

    def delivered() -> list[int]:
        network = SimulatedNetwork(seed=11, conditions=BAD_NETWORK)
        host, client, peer = connected_pair(network)
        events: list[TransportEvent] = []
        for tick in range(200):
            host.send(peer, Channel.SNAPSHOT, struct.pack("<I", tick))
            network.advance(DT)
            events.extend(client.poll())
        return [
            struct.unpack("<I", body)[0] for body in bodies(events, Channel.SNAPSHOT)
        ]

    first = delivered()

    assert first == delivered()
    assert len(first) < 200


KEEPALIVE = 4


def test_a_lost_first_keepalive_cannot_deadlock_a_join() -> None:
    """`renetcode` alone never recovers here, while traffic is flowing.

    The client ignores payloads until a keepalive arrives, and each payload resets
    the host's keepalive timer, so the host would believe the player had joined
    while the client timed out. Losing one datagram must cost only a moment.
    """
    network = SimulatedNetwork(seed=1, conditions=LinkConditions(latency=0.02))
    key = secrets.token_bytes(32)
    host = network.add_host(key)
    address = network.address_of(host)
    client = network.add_client(key, address)
    lost: list[bytes] = []

    def lose_the_first_keepalive(source: str, _: str, data: bytes) -> bool:
        if source == address and data[0] & 0x0F == KEEPALIVE and not lost:
            lost.append(data)
            return True
        return False

    network.drop = lose_the_first_keepalive
    peer = None
    heard: list[TransportEvent] = []
    for _ in range(60 * 3):
        network.advance(DT)
        for event in host.poll():
            if isinstance(event, PeerConnected):
                peer = event.peer
        if peer is not None:
            # What a real session does at once: a welcome, then snapshots.
            host.send(peer, Channel.SNAPSHOT, b"snapshot")
            host.send(peer, Channel.EVENTS, b"event")
        heard.extend(client.poll())

    assert lost
    assert [e for e in heard if isinstance(e, PeerConnected)]
    assert bodies(heard, Channel.SNAPSHOT)
    assert not [e for e in heard if isinstance(e, PeerDisconnected)]


def test_the_host_reports_nobody_who_never_finished_the_handshake() -> None:
    """If the client can't hear us, both sides must agree it did not join."""
    network = SimulatedNetwork(seed=1)
    key = secrets.token_bytes(32)
    host = network.add_host(key)
    address = network.address_of(host)
    network.add_client(key, address)
    network.drop = (
        lambda source, _, data: source == address and data[0] & 0x0F == KEEPALIVE
    )

    heard = run_collecting(network, host, 12.0)

    assert heard == []


@pytest.mark.parametrize("seed", range(100))
def test_joining_while_the_host_sends_succeeds_at_20_percent_loss(seed: int) -> None:
    """Without the confirmation, 19 of these 100 seeds fail."""
    network = SimulatedNetwork(seed=seed, conditions=BAD_NETWORK)
    key = secrets.token_bytes(32)
    host = network.add_host(key)
    client = network.add_client(key, network.address_of(host))
    peer = None
    client_up = False
    for _ in range(60 * 8):
        network.advance(DT)
        for event in host.poll():
            if isinstance(event, PeerConnected):
                peer = event.peer
        if peer is not None:
            host.send(peer, Channel.SNAPSHOT, b"snapshot")
        for event in client.poll():
            client_up = client_up or isinstance(event, PeerConnected)
        if client_up and peer is not None:
            return
    raise AssertionError(f"host saw {peer}, client up: {client_up}")


def test_wrong_key_never_connects_and_the_host_sends_it_nothing() -> None:
    network = SimulatedNetwork(seed=1)
    host = network.add_host(secrets.token_bytes(32))
    host_address = network.address_of(host)
    stranger = network.add_client(secrets.token_bytes(32), host_address)
    sent_by_host: list[bytes] = []
    network.tap = lambda source, _, data: (
        sent_by_host.append(data) if source == host_address else None
    )

    events = run_collecting(network, host, 5.0)

    assert not [e for e in events if isinstance(e, PeerConnected)]
    assert sent_by_host == []
    assert not [e for e in stranger.poll() if isinstance(e, PeerConnected)]


@pytest.mark.parametrize(
    "key", [bytes(32), b"short", bytes(33)], ids=["all-zero", "short", "long"]
)
def test_a_bad_session_key_is_refused(key: bytes) -> None:
    network = SimulatedNetwork()
    with pytest.raises(ValueError, match="key"):
        network.add_host(key)
    with pytest.raises(ValueError, match="key"):
        network.add_client(key, "10.0.0.1:7000")


def test_nothing_on_the_wire_contains_the_message_or_the_key() -> None:
    network = SimulatedNetwork(seed=2)
    key = secrets.token_bytes(32)
    host = network.add_host(key)
    client = network.add_client(key, network.address_of(host))
    wire: list[bytes] = []
    network.tap = lambda _, __, data: wire.append(data)
    secret = b"a recognisable plaintext marker"
    peer = None
    for _ in range(600):
        network.advance(DT)
        for event in host.poll():
            if isinstance(event, PeerConnected):
                peer = event.peer
                host.send(peer, Channel.EVENTS, secret)
    assert peer is not None
    assert any(
        isinstance(e, MessageDelivered) and e.data == secret for e in client.poll()
    )
    assert wire
    for datagram in wire:
        assert secret not in datagram
        assert key not in datagram


def test_silent_peer_times_out_on_both_sides() -> None:
    network = SimulatedNetwork(seed=1)
    host, client, peer = connected_pair(network)

    network.conditions.loss = 1.0
    host_events = run_collecting(network, host, 9.0)
    assert not [e for e in host_events if isinstance(e, PeerDisconnected)]

    host_events = run_collecting(network, host, 2.0)
    client_events = client.poll()

    assert [e.peer for e in host_events if isinstance(e, PeerDisconnected)] == [peer]
    assert [e.reason for e in client_events if isinstance(e, PeerDisconnected)] == [
        "ConnectionTimedOut"
    ]


def test_connection_survives_a_loss_burst_shorter_than_the_timeout() -> None:
    network = SimulatedNetwork(seed=1)
    host, client, peer = connected_pair(network)
    network.conditions.loss = 1.0
    run_collecting(network, client, 6.0)
    network.conditions.loss = 0.0
    assert host.send(peer, Channel.EVENTS, b"still here")

    events = run_collecting(network, client, 1.0)

    assert bodies(events, Channel.EVENTS) == [b"still here"]
    assert not [e for e in events if isinstance(e, PeerDisconnected)]


def test_client_closing_tells_the_host_at_once() -> None:
    network = SimulatedNetwork(seed=1)
    host, client, peer = connected_pair(network)
    client.close()

    events = run_collecting(network, host, 0.2)

    assert [(e.peer, e.reason) for e in events if isinstance(e, PeerDisconnected)] == [
        (peer, "left")
    ]


def test_a_closed_session_can_be_rejoined() -> None:
    network = SimulatedNetwork(seed=1)
    key = secrets.token_bytes(32)
    host = network.add_host(key)
    address = network.address_of(host)
    first = network.add_client(key, address, address="10.0.0.9:7000")
    run_collecting(network, host, 1.0)
    first.close()
    run_collecting(network, host, 0.2)
    network.remove(first)

    network.add_client(key, address, address="10.0.0.9:7000")
    events = run_collecting(network, host, 1.0)

    assert [e for e in events if isinstance(e, PeerConnected)]


def test_a_full_game_denies_the_next_player_without_disturbing_the_others() -> None:
    network = SimulatedNetwork(seed=1)
    key = secrets.token_bytes(32)
    host = network.add_host(key, max_clients=1)
    address = network.address_of(host)
    network.add_client(key, address)
    run_collecting(network, host, 1.0)
    late = network.add_client(key, address)

    heard_by_host = []
    heard_by_late = []
    for _ in range(60):
        network.advance(DT)
        heard_by_host.extend(host.poll())
        heard_by_late.extend(late.poll())

    assert not [e for e in heard_by_host if isinstance(e, PeerConnected)]
    assert not [e for e in heard_by_host if isinstance(e, PeerDisconnected)]
    assert [e.reason for e in heard_by_late if isinstance(e, PeerDisconnected)] == [
        "ConnectionDenied"
    ]


def test_sending_to_a_stranger_is_refused_rather_than_fatal() -> None:
    network = SimulatedNetwork(seed=1)
    host, _, _ = connected_pair(network)

    assert host.send(12345, Channel.EVENTS, b"x") is False


def test_sending_before_connecting_is_refused() -> None:
    network = SimulatedNetwork(seed=1)
    key = secrets.token_bytes(32)
    host = network.add_host(key)
    client = network.add_client(key, network.address_of(host))

    assert client.send(HOST_PEER, Channel.EVENTS, b"x") is False


# A reliable channel accepts up to half its limit: see `bytes_to_check`.
EVENTS_LIMIT = 1024 * 1024
LARGEST_EVENT = EVENTS_LIMIT // 2 - 1200


def test_an_over_budget_reliable_send_is_refused_and_keeps_the_connection() -> None:
    """`renet` would disconnect here, so the core has to check first."""
    network = SimulatedNetwork(seed=1)
    host, client, peer = connected_pair(network)
    blob = bytes(LARGEST_EVENT)

    assert host.send(peer, Channel.EVENTS, blob)
    assert host.send(peer, Channel.EVENTS, bytes(2000)) is False

    events = run_collecting(network, client, 5.0)
    assert bodies(events, Channel.EVENTS) == [blob]
    assert not [e for e in events if isinstance(e, PeerDisconnected)]


def test_the_budget_frees_up_once_a_backlog_is_acknowledged() -> None:
    network = SimulatedNetwork(seed=1)
    host, client, peer = connected_pair(network)
    assert host.send(peer, Channel.EVENTS, bytes(LARGEST_EVENT))
    assert host.send(peer, Channel.EVENTS, bytes(2000)) is False

    run_collecting(network, client, 3.0)

    assert host.send(peer, Channel.EVENTS, bytes(2000))


@pytest.mark.parametrize(
    "size",
    [
        EVENTS_LIMIT,
        EVENTS_LIMIT - 1,
        EVENTS_LIMIT - 600,
        EVENTS_LIMIT // 2,
        LARGEST_EVENT,
    ],
)
def test_one_large_message_is_refused_or_delivered_but_never_fatal(size: int) -> None:
    """The receiver charges a sliced message as whole slices, against the same limit.

    So a message the sender accepts can end the connection at the other end, and a
    single large one is what reaches the limit before the receiver drains it.
    """
    network = SimulatedNetwork(seed=1)
    host, client, peer = connected_pair(network)
    accepted = host.send(peer, Channel.EVENTS, bytes(size))

    events = run_collecting(network, client, 10.0)

    assert not [e for e in events if isinstance(e, PeerDisconnected)]
    assert len(bodies(events, Channel.EVENTS)) == (1 if accepted else 0)


@pytest.mark.parametrize("size", [1201, 1200, 2401, 60_000])
def test_everything_a_channel_accepts_can_be_received(size: int) -> None:
    network = SimulatedNetwork(seed=1)
    host, client, peer = connected_pair(network)
    accepted = 0
    while host.send(peer, Channel.EVENTS, bytes(size)):
        accepted += 1
    assert accepted > 0

    events = run_collecting(network, client, 10.0)

    assert len(bodies(events, Channel.EVENTS)) == accepted
    assert not [e for e in events if isinstance(e, PeerDisconnected)]


def test_a_client_can_also_fill_its_channel_without_being_disconnected() -> None:
    network = SimulatedNetwork(seed=1)
    host, client, _ = connected_pair(network)
    accepted = 0
    while client.send(HOST_PEER, Channel.EVENTS, bytes(1201)):
        accepted += 1

    events = run_collecting(network, host, 5.0)

    assert accepted > 0
    assert len(bodies(events, Channel.EVENTS)) == accepted
    assert not [e for e in events if isinstance(e, PeerDisconnected)]


@pytest.mark.parametrize("channel", [5, 255])
def test_an_unknown_channel_is_an_error_not_a_panic(channel: int) -> None:
    network = SimulatedNetwork(seed=1)
    host, _, peer = connected_pair(network)

    with pytest.raises(ValueError, match="channel"):
        host.endpoint.send(peer, channel, b"x")


@pytest.mark.parametrize("dt", [-1.0, float("nan"), float("inf")])
def test_a_bad_time_step_is_an_error_not_a_panic(dt: float) -> None:
    network = SimulatedNetwork(seed=1)
    host, _, _ = connected_pair(network)

    with pytest.raises(ValueError, match="dt"):
        host.endpoint.tick(dt)


def test_stats_report_what_the_link_is_doing() -> None:
    network = SimulatedNetwork(seed=1, conditions=LinkConditions(latency=0.05))
    host, client, peer = connected_pair(network)
    for _ in range(120):
        host.send(peer, Channel.SNAPSHOT, bytes(100))
        network.advance(DT)
        client.poll()

    stats = host.stats(peer)

    assert stats is not None
    assert 0.06 < stats.rtt < 0.14
    assert stats.bytes_sent_per_second > 1000
    assert host.stats(12345) is None
