"""Invites, version checks and admission."""

from __future__ import annotations

import contextlib
import random
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

from pyguara import native
from pyguara.net import (
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
    SimulatedNetwork,
    UdpTransport,
    Versions,
)
from pyguara.net import transport as transport_module
from pyguara.net.session import SessionEvent, SessionFailed
from pyguara.net.transport import NET_PROTOCOL_VERSION, MessageDelivered, load_core

DT = 1 / 60
VERSIONS = Versions("0.6.0", "1.0", b"h" * 32)


def start(
    theirs: Versions = VERSIONS,
    conditions: LinkConditions | None = None,
    seed: int = 1,
) -> tuple[SimulatedNetwork, HostSession, ClientSession]:
    network = SimulatedNetwork(seed=seed, conditions=conditions)
    key = secrets.token_bytes(32)
    host = network.add_host(key)
    client = network.add_client(key, network.address_of(host), theirs.encode())
    return network, HostSession(host, VERSIONS), ClientSession(client)


def run(
    network: SimulatedNetwork, host: HostSession, client: ClientSession, seconds: float
) -> tuple[list[SessionEvent], list[SessionEvent]]:
    heard_host: list[SessionEvent] = []
    heard_client: list[SessionEvent] = []
    for _ in range(round(seconds / DT)):
        network.advance(DT)
        heard_host.extend(host.poll())
        heard_client.extend(client.poll())
    return heard_host, heard_client


@pytest.mark.parametrize("seed", range(10))
def test_matching_versions_are_admitted_even_on_a_bad_network(seed: int) -> None:
    network, host, client = start(
        conditions=LinkConditions(latency=0.05, jitter=0.03, loss=0.2), seed=seed
    )

    heard_host, heard_client = run(network, host, client, 8.0)

    assert [type(e) for e in heard_client] == [Joined]
    assert [e.versions for e in heard_host if isinstance(e, PlayerJoined)] == [VERSIONS]
    assert client.joined
    assert len(host.players) == 1


@pytest.mark.parametrize(
    ("theirs", "expected"),
    [
        (Versions("0.5.0", "1.0", b"h" * 32), ("0.6.0", "0.5.0")),
        (Versions("0.6.0", "0.9", b"h" * 32), ("1.0", "0.9")),
        (Versions("0.6.0", "1.0", b"x" * 32), ("files",)),
        (Versions("0.6.0", "1.0", b"h" * 32, protocol=99), ("99",)),
    ],
    ids=["engine", "game", "content", "protocol"],
)
def test_a_mismatch_is_refused_and_the_message_names_both_sides(
    theirs: Versions, expected: tuple[str, ...]
) -> None:
    network, host, client = start(theirs)

    heard_host, heard_client = run(network, host, client, 2.0)

    refused = [e for e in heard_client if isinstance(e, Refused)]
    assert len(refused) == 1
    for text in expected:
        assert text in refused[0].reason
    assert not [e for e in heard_host if isinstance(e, PlayerJoined)]
    assert not client.joined
    assert not host.players


@pytest.mark.parametrize("seed", range(10))
def test_a_refusal_is_read_even_on_a_bad_network(seed: int) -> None:
    """Which is why the host waits for the ack before disconnecting."""
    network, host, client = start(
        Versions("0.5.0", "1.0"),
        conditions=LinkConditions(latency=0.05, jitter=0.03, loss=0.2),
        seed=seed,
    )

    _, heard_client = run(network, host, client, 12.0)

    assert [e for e in heard_client if isinstance(e, Refused)]


def test_refused_client_is_eventually_disconnected() -> None:
    network, host, client = start(Versions("0.5.0", "1.0"))

    _, heard_client = run(network, host, client, 2.0)

    assert [type(e) for e in heard_client] == [Refused]
    assert client.send(Channel.EVENTS, b"x") is False


def test_a_peer_that_was_not_admitted_is_never_heard() -> None:
    network = SimulatedNetwork(seed=1)
    key = secrets.token_bytes(32)
    host_transport = network.add_host(key)
    client = network.add_client(
        key, network.address_of(host_transport), Versions("0.5.0", "1.0").encode()
    )
    host = HostSession(host_transport, VERSIONS)
    heard: list[SessionEvent] = []
    for _ in range(120):
        client.send(0, Channel.EVENTS, b"let me in")
        network.advance(DT)
        heard.extend(host.poll())

    assert not [e for e in heard if isinstance(e, MessageReceived)]


def test_an_unreadable_hello_is_refused_rather_than_raising() -> None:
    network = SimulatedNetwork(seed=1)
    key = secrets.token_bytes(32)
    host_transport = network.add_host(key)
    client = network.add_client(
        key, network.address_of(host_transport), secrets.token_bytes(256)
    )
    host = HostSession(host_transport, VERSIONS)
    session = ClientSession(client)

    _, heard = run(network, host, session, 2.0)

    assert [e for e in heard if isinstance(e, Refused)]
    assert not host.players


def test_a_client_cannot_write_to_the_sessions_own_channel() -> None:
    network, host, client = start()
    run(network, host, client, 1.0)
    client.send(Channel.CONTROL, b"\x01forged")
    client.send(Channel.EVENTS, b"honest")

    heard_host, _ = run(network, host, client, 0.5)

    messages = [e.data for e in heard_host if isinstance(e, MessageReceived)]
    assert messages == [b"honest"]


def test_messages_flow_once_admitted() -> None:
    network, host, client = start()
    run(network, host, client, 1.0)
    peer = next(iter(host.players))

    assert host.send(peer, Channel.EVENTS, b"down")
    assert client.send(Channel.EVENTS, b"up")
    heard_host, heard_client = run(network, host, client, 0.5)

    assert [e.data for e in heard_host if isinstance(e, MessageReceived)] == [b"up"]
    assert [e.data for e in heard_client if isinstance(e, MessageReceived)] == [b"down"]


def test_sending_to_someone_not_admitted_is_refused() -> None:
    network, host, client = start()
    run(network, host, client, 1.0)

    assert host.send(999, Channel.EVENTS, b"x") is False


def test_a_player_leaving_is_reported_and_a_kick_tells_them() -> None:
    network, host, client = start()
    run(network, host, client, 1.0)
    peer = next(iter(host.players))

    host.kick(peer)
    heard_host, heard_client = run(network, host, client, 0.5)

    assert [e.peer for e in heard_host if isinstance(e, PlayerLeft)] == [peer]
    assert [type(e) for e in heard_client] == [Left]
    assert not host.players
    assert not client.joined


def test_a_wrong_key_times_out_and_the_message_says_to_check_the_invite() -> None:
    network = SimulatedNetwork(seed=1)
    host = network.add_host(secrets.token_bytes(32))
    client = network.add_client(
        secrets.token_bytes(32), network.address_of(host), VERSIONS.encode()
    )
    session = ClientSession(client)
    heard: list[SessionEvent] = []
    for _ in range(60 * 12):
        network.advance(DT)
        heard.extend(session.poll())

    left = [e for e in heard if isinstance(e, Left)]
    assert len(left) == 1
    assert "invite" in left[0].reason


def test_players_get_slots_from_one_and_a_freed_slot_is_reused() -> None:
    network = SimulatedNetwork(seed=1)
    key = secrets.token_bytes(32)
    transport = network.add_host(key)
    host = HostSession(transport, VERSIONS)
    address = network.address_of(transport)
    clients = [
        ClientSession(network.add_client(key, address, VERSIONS.encode()))
        for _ in range(3)
    ]
    heard: list[SessionEvent] = []
    told: list[list[SessionEvent]] = [[], [], []]

    def run_for(seconds: float) -> None:
        for _ in range(round(seconds / DT)):
            network.advance(DT)
            heard.extend(host.poll())
            for client, log in zip(clients, told, strict=True):
                log.extend(client.poll())

    run_for(2.0)
    slots = [e.slot for e in heard if isinstance(e, PlayerJoined)]
    assert sorted(slots) == [1, 2, 3]
    assert sorted(e.slot for log in told for e in log if isinstance(e, Joined)) == [
        1,
        2,
        3,
    ]

    leaver = next(e for e in heard if isinstance(e, PlayerJoined) and e.slot == 2)
    host.kick(leaver.peer)
    run_for(0.5)
    assert host.slot_of(leaver.peer) is None
    heard.clear()
    clients.append(ClientSession(network.add_client(key, address, VERSIONS.encode())))
    told.append([])
    run_for(2.0)

    assert [e.slot for e in heard if isinstance(e, PlayerJoined)] == [2]


class ScriptedTransport:
    """Delivers exactly what a test says, in the order it says."""

    def __init__(self) -> None:
        self.incoming: list[object] = []

    def poll(self) -> list[object]:
        events, self.incoming = self.incoming, []
        return events

    def send(self, peer: int, channel: Channel, data: bytes) -> bool:
        return True

    def disconnect(self, peer: int, flush: bool = False) -> None:
        pass

    def stats(self, peer: int) -> None:
        return None

    def close(self) -> None:
        pass


def test_reliable_messages_that_overtake_the_welcome_are_kept_in_order() -> None:
    """Channels aren't ordered against each other, and a lost spawn is a lasting desync."""
    transport = ScriptedTransport()
    client = ClientSession(transport)  # type: ignore[arg-type]
    transport.incoming = [
        MessageDelivered(0, Channel.EVENTS, b"first"),
        MessageDelivered(0, Channel.SNAPSHOT, b"second"),
    ]
    assert client.poll() == []

    transport.incoming = [
        MessageDelivered(0, Channel.EVENTS, b"third"),
        MessageDelivered(0, Channel.CONTROL, b"\x01\x02"),
        MessageDelivered(0, Channel.EVENTS, b"fourth"),
    ]
    heard = client.poll()

    assert heard[0] == Joined(2)
    assert [e.data for e in heard[1:] if isinstance(e, MessageReceived)] == [
        b"first",
        b"second",
        b"third",
        b"fourth",
    ]


def test_messages_that_overtook_a_refusal_are_never_delivered() -> None:
    transport = ScriptedTransport()
    client = ClientSession(transport)  # type: ignore[arg-type]
    transport.incoming = [
        MessageDelivered(0, Channel.EVENTS, b"early"),
        MessageDelivered(0, Channel.CONTROL, b"\x02no"),
        MessageDelivered(0, Channel.EVENTS, b"late"),
    ]

    heard = client.poll()

    assert heard == [Refused("no")]


def test_too_many_messages_before_a_welcome_end_the_session_rather_than_lose_one() -> (
    None
):
    transport = ScriptedTransport()
    client = ClientSession(transport)  # type: ignore[arg-type]
    transport.incoming = [
        MessageDelivered(0, Channel.EVENTS, b"x") for _ in range(20_000)
    ]

    heard = client.poll()

    assert [type(e) for e in heard] == [SessionFailed]


def test_invite_round_trips_including_ipv6_and_hides_its_key_from_repr() -> None:
    for host in ("192.168.0.5", "example.com", "::1"):
        invite = Invite.create(host, 7777)
        assert Invite.parse(str(invite)) == invite
        assert invite.key.hex() not in repr(invite)
        assert str(invite).split("#")[1] not in repr(invite)


def test_invites_are_unique() -> None:
    assert Invite.create("a", 1).key != Invite.create("a", 1).key


@pytest.mark.parametrize(
    "text",
    [
        "",
        "nonsense",
        "pyguara://",
        "pyguara://#",
        "pyguara://host#AAAA",
        "pyguara://host:port#AAAA",
        "pyguara://host:0#AAAA",
        "pyguara://host:70000#AAAA",
        "pyguara://host:7000#AAAA",
        "pyguara://host:7000#!!!!",
        "pyguara://host:٣٣#AAAA",
    ],
)
def test_a_bad_invite_is_a_valueerror(text: str) -> None:
    with pytest.raises(ValueError):
        Invite.parse(text)


def test_a_damaged_invite_error_never_repeats_the_key() -> None:
    key = str(Invite.create("host", 7000)).split("#")[1]

    with pytest.raises(ValueError) as error:
        Invite.parse(f"pyguara://host:7000#{key[:-3]}")

    assert key[:10] not in str(error.value)


def test_random_invites_only_ever_raise_valueerror() -> None:
    rng = random.Random(1)
    alphabet = "pyguara:/#[]0123456789ABCDEFGH= \n\x00é"
    for _ in range(20_000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randrange(40)))
        if rng.random() < 0.5:
            text = "pyguara://" + text
        with contextlib.suppress(ValueError):
            Invite.parse(text)


def test_versions_round_trip_when_padded_as_the_wire_pads_them() -> None:
    encoded = VERSIONS.encode()

    assert len(encoded) <= 256
    assert Versions.decode(encoded.ljust(256, b"\0")) == VERSIONS


def test_the_longest_versions_fit_the_connections_user_data() -> None:
    assert len(Versions("e" * 64, "g" * 64).encode()) <= 256


def test_oversized_versions_are_a_caller_error() -> None:
    with pytest.raises(ValueError, match="version"):
        Versions("e" * 65, "g").encode()
    with pytest.raises(ValueError, match="hash"):
        Versions("e", "g", b"short").encode()


def test_hostile_user_data_decodes_to_none_or_a_value_but_never_raises() -> None:
    rng = random.Random(2)
    valid = VERSIONS.encode().ljust(256, b"\0")
    for _ in range(50_000):
        sample = bytearray(valid if rng.random() < 0.5 else rng.randbytes(256))
        for _ in range(rng.randrange(6)):
            sample[rng.randrange(256)] = rng.randrange(256)
        Versions.decode(bytes(sample[: rng.randrange(257)]))
    assert Versions.decode(b"") is None
    huge = b"PGH1" + bytes(4) + bytes(32) + b"\xff" + bytes(300)
    assert Versions.decode(huge) is None


def test_python_and_rust_agree_on_the_protocol_version() -> None:
    assert load_core().NET_PROTOCOL_VERSION == NET_PROTOCOL_VERSION


def test_a_stale_extension_fails_naming_make_native(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Stale:
        NET_PROTOCOL_VERSION = NET_PROTOCOL_VERSION - 1

    monkeypatch.setattr(transport_module.native, "require_extension", lambda _: Stale)

    with pytest.raises(RuntimeError, match="make native"):
        load_core()


def test_an_extension_older_than_networking_also_names_make_native(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        transport_module.native, "require_extension", lambda _: object()
    )

    with pytest.raises(RuntimeError, match="make native"):
        load_core()


def test_no_extension_import_is_fine_and_starting_a_session_explains(
    tmp_path: Path,
) -> None:
    """A single-player game on an uncovered platform must be unaffected."""
    script = """
import sys
sys.modules["pyguara.pyguara_core_rs"] = None
import pyguara.native as native
native._candidate_paths = lambda: []
import pyguara.net
assert "pyguara.pyguara_core_rs" not in {
    name for name, module in sys.modules.items() if module is not None
}
try:
    pyguara.net.UdpTransport.host(b"k" * 32, 0)
except RuntimeError as error:
    print("REFUSED", "networked multiplayer" in str(error))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "REFUSED True" in result.stdout


def test_the_no_native_switch_does_not_turn_networking_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A backend, not a store: ADR 0004, Decision 4."""
    monkeypatch.setenv("PYGUARA_NO_NATIVE", "1")

    assert native.require_extension("test") is not None
    transport = UdpTransport.host(secrets.token_bytes(32), 0, bind_ip="127.0.0.1")
    transport.close()
