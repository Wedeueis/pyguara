"""The Steam core, through the seeded network: `renet` keyed by Steam ID.

The first half re-runs every test in `test_net_transport.py` that does not
depend on `renetcode`'s handshake, with `connected_pair` swapped for a Steam
pair -- so both cores are held to one specification for channels, slicing,
backpressure, timeouts and stats. The second half is what only the Steam core
has: admitting by Steam ID, refusing strangers, revoking a player.

Steam itself is not simulated. What crosses this network is what the core
would hand to Steam's messages; Steam's authentication of the sender is
assumed, which is what makes a Steam ID usable as an identity at all.
"""

from __future__ import annotations

import random
from collections.abc import Iterator

import pytest

from pyguara.net import Channel, SimulatedNetwork
from pyguara.net.transport import (
    HOST_PEER,
    NativeTransport,
    PeerConnected,
    PeerDisconnected,
)
from tests import test_net_transport as udp

HOST_ID = 76561198000000001
GUEST_ID = 76561198000000002
STRANGER_ID = 76561198000000666
DT = udp.DT
HELLO, WELCOME, PAYLOAD, BYE, KEEPALIVE, REFUSED = range(1, 7)


def steam_pair(
    network: SimulatedNetwork,
) -> tuple[NativeTransport, NativeTransport, int]:
    """Connect a closed Steam host and an allowed guest."""
    host = network.add_steam_host(HOST_ID)
    host.endpoint.allow(GUEST_ID)
    client = network.add_steam_client(GUEST_ID, HOST_ID)
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


@pytest.fixture(autouse=True)
def _steam_pairs(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(udp, "connected_pair", steam_pair)
    yield


SHARED = [
    "test_reliable_stream_arrives_complete_and_in_order_at_20_percent_loss",
    "test_reliable_stream_from_client_to_host_too",
    "test_large_message_is_sliced_and_reassembled_under_loss",
    "test_channels_do_not_block_each_other",
    "test_unreliable_loses_messages_but_never_corrupts_them",
    "test_same_seed_gives_the_same_delivery_pattern",
    "test_silent_peer_times_out_on_both_sides",
    "test_connection_survives_a_loss_burst_shorter_than_the_timeout",
    "test_client_closing_tells_the_host_at_once",
    "test_sending_to_a_stranger_is_refused_rather_than_fatal",
    "test_an_over_budget_reliable_send_is_refused_and_keeps_the_connection",
    "test_the_budget_frees_up_once_a_backlog_is_acknowledged",
    "test_one_large_message_is_refused_or_delivered_but_never_fatal",
    "test_everything_a_channel_accepts_can_be_received",
    "test_a_client_can_also_fill_its_channel_without_being_disconnected",
    "test_an_unknown_channel_is_an_error_not_a_panic",
    "test_a_bad_time_step_is_an_error_not_a_panic",
    "test_stats_report_what_the_link_is_doing",
]
for _name in SHARED:
    globals()[_name] = getattr(udp, _name)


def _run(
    network: SimulatedNetwork, *endpoints: NativeTransport, seconds: float
) -> list[list[object]]:
    heard: list[list[object]] = [[] for _ in endpoints]
    for _ in range(round(seconds / DT)):
        network.advance(DT)
        for log, endpoint in zip(heard, endpoints, strict=True):
            log.extend(endpoint.poll())
    return heard


def _reasons(events: list[object]) -> list[str]:
    return [e.reason for e in events if isinstance(e, PeerDisconnected)]


def test_the_host_receives_the_guests_user_data() -> None:
    network = SimulatedNetwork(seed=1)
    host = network.add_steam_host(HOST_ID)
    host.endpoint.allow(GUEST_ID)
    network.add_steam_client(GUEST_ID, HOST_ID, user_data=b"v1:abc")

    (heard,) = _run(network, host, seconds=0.5)

    assert [(e.peer, e.user_data) for e in heard if isinstance(e, PeerConnected)] == [
        (GUEST_ID, b"v1:abc")
    ]


def test_a_stranger_is_refused_and_the_host_reports_nothing() -> None:
    network = SimulatedNetwork(seed=1)
    host = network.add_steam_host(HOST_ID)
    stranger = network.add_steam_client(STRANGER_ID, HOST_ID)

    heard_by_host, heard_by_stranger = _run(network, host, stranger, seconds=1.0)

    assert heard_by_host == []
    assert _reasons(heard_by_stranger) == ["not invited to this room"]
    assert host.counters()["wrong_source"] >= 1


def test_an_open_room_admits_anyone() -> None:
    network = SimulatedNetwork(seed=1)
    host = network.add_steam_host(HOST_ID, open_room=True)
    network.add_steam_client(STRANGER_ID, HOST_ID)

    (heard,) = _run(network, host, seconds=0.5)

    assert [e.peer for e in heard if isinstance(e, PeerConnected)] == [STRANGER_ID]


def test_a_full_room_denies_the_next_player_without_disturbing_the_first() -> None:
    network = SimulatedNetwork(seed=1)
    host = network.add_steam_host(HOST_ID, max_clients=1)
    host.endpoint.allow(GUEST_ID)
    host.endpoint.allow(STRANGER_ID)
    first = network.add_steam_client(GUEST_ID, HOST_ID)
    _run(network, host, first, seconds=0.5)
    late = network.add_steam_client(STRANGER_ID, HOST_ID)

    heard_by_host, heard_by_first, heard_by_late = _run(
        network, host, first, late, seconds=1.0
    )

    assert not [
        e for e in heard_by_host if isinstance(e, PeerConnected | PeerDisconnected)
    ]
    assert _reasons(heard_by_first) == []
    assert _reasons(heard_by_late) == ["ConnectionDenied"]


def test_revoking_a_player_drops_them_and_only_them() -> None:
    network = SimulatedNetwork(seed=1)
    host = network.add_steam_host(HOST_ID)
    host.endpoint.allow(GUEST_ID)
    host.endpoint.allow(STRANGER_ID)
    kept = network.add_steam_client(STRANGER_ID, HOST_ID)
    dropped = network.add_steam_client(GUEST_ID, HOST_ID)
    _run(network, host, kept, dropped, seconds=0.5)

    host.endpoint.revoke(GUEST_ID)
    heard_by_host, heard_by_kept, heard_by_dropped = _run(
        network, host, kept, dropped, seconds=1.0
    )

    assert [
        (e.peer, e.reason) for e in heard_by_host if isinstance(e, PeerDisconnected)
    ] == [(GUEST_ID, "removed from the room")]
    assert _reasons(heard_by_dropped) == ["DisconnectedByServer"]
    assert _reasons(heard_by_kept) == []


def test_a_lost_welcome_costs_a_resend_not_the_join() -> None:
    network = SimulatedNetwork(seed=1)
    lost = {"welcomes": 0}

    def drop_first_welcomes(source: str, _: str, data: bytes) -> bool:
        if (
            source == str(HOST_ID)
            and data[:1] == bytes([WELCOME])
            and lost["welcomes"] < 3
        ):
            lost["welcomes"] += 1
            return True
        return False

    network.drop = drop_first_welcomes
    host, client, _ = steam_pair(network)

    assert lost["welcomes"] == 3
    assert client.send(HOST_PEER, Channel.EVENTS, b"made it")


def test_no_host_ends_the_join_with_the_session_s_reason() -> None:
    network = SimulatedNetwork(seed=1)
    client = network.add_steam_client(GUEST_ID, HOST_ID)

    (heard,) = _run(network, client, seconds=11.0)

    assert _reasons(heard) == ["ConnectionRequestTimedOut"]


def test_a_client_ignores_everyone_but_its_host() -> None:
    network = SimulatedNetwork(seed=1)
    host, client, _ = steam_pair(network)

    network.inject(str(STRANGER_ID), str(GUEST_ID), bytes([BYE]) + b"fake")
    (heard,) = _run(network, client, seconds=0.5)

    assert _reasons(heard) == []
    assert client.counters()["wrong_source"] == 1


def test_a_client_can_rejoin_after_closing() -> None:
    network = SimulatedNetwork(seed=1)
    host, first, _ = steam_pair(network)
    first.close()
    _run(network, host, seconds=0.5)
    network.remove(first)

    network.add_steam_client(GUEST_ID, HOST_ID)
    (heard,) = _run(network, host, seconds=0.5)

    assert [e.peer for e in heard if isinstance(e, PeerConnected)] == [GUEST_ID]


@pytest.mark.parametrize("seed", range(5))
def test_garbage_from_an_admitted_peer_costs_only_that_peer(seed: int) -> None:
    rng = random.Random(seed)
    network = SimulatedNetwork(seed=seed)
    host = network.add_steam_host(HOST_ID)
    host.endpoint.allow(GUEST_ID)
    host.endpoint.allow(STRANGER_ID)
    good = network.add_steam_client(GUEST_ID, HOST_ID)
    network.add_steam_client(STRANGER_ID, HOST_ID)
    _run(network, host, good, seconds=0.5)

    for _ in range(2000):
        size = rng.randrange(0, 1500)
        tag = rng.choice([PAYLOAD, HELLO, WELCOME, KEEPALIVE, 0, 0xFF])
        network.inject(
            str(STRANGER_ID), str(HOST_ID), bytes([tag]) + rng.randbytes(size)
        )
    assert host.send(GUEST_ID, Channel.EVENTS, b"still fine")
    _, heard_by_good = _run(network, host, good, seconds=1.0)

    assert [e.data for e in heard_by_good if hasattr(e, "data")] == [b"still fine"]
    assert _reasons(heard_by_good) == []


def test_refusals_to_strangers_are_rate_limited() -> None:
    network = SimulatedNetwork(seed=1)
    host = network.add_steam_host(HOST_ID)
    sent: list[bytes] = []
    network.tap = (
        lambda source, _, data: sent.append(data) if source == str(HOST_ID) else None
    )

    for i in range(5000):
        network.inject(str(STRANGER_ID + i), str(HOST_ID), bytes([HELLO]))
    network.advance(DT)

    refusals = [d for d in sent if d[:1] == bytes([REFUSED])]
    assert 0 < len(refusals) <= 400
    assert host.counters()["unauth_over_budget"] > 0
