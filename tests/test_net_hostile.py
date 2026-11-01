"""Everything an attacker could send, against the real Rust core.

Three kinds of attacker, because they reach different code: a stranger with no
key reaches `renetcode`'s parser, a spoofer can forge a real player's address,
and an invited player who turns hostile can reach `renet` itself. The rule for
all of them is that nothing raises, and only the attacker can lose anything.

The crates are pinned because of what these tests guard: see
`rust/src/net/core.rs` and `network_multiplayer.md`, section 3.
"""

from __future__ import annotations

import random
import secrets
import tomllib
from pathlib import Path

import pytest

from pyguara.net import Channel, LinkConditions, SimulatedNetwork
from pyguara.net.transport import (
    MessageDelivered,
    NativeTransport,
    PeerConnected,
    PeerDisconnected,
    TransportEvent,
)

DT = 1 / 60
ATTACKER = "198.51.100.66:4444"


class Game:
    """A host with one honest player, connected on a perfect network."""

    def __init__(self, seed: int = 1) -> None:
        self.network = SimulatedNetwork(seed=seed)
        self.key = secrets.token_bytes(32)
        self.host = self.network.add_host(self.key, max_clients=64)
        self.host_address = self.network.address_of(self.host)
        self.player = self.network.add_client(self.key, self.host_address)
        self.player_address = self.network.address_of(self.player)
        self.player_id = self._connect(self.player)

    def _connect(self, client: NativeTransport) -> int:
        """Wait for both ends: a client finishes its handshake after the host."""
        peer = None
        client_up = False
        for _ in range(120):
            self.network.advance(DT)
            for event in self.host.poll():
                if isinstance(event, PeerConnected):
                    peer = event.peer
            for event in client.poll():
                client_up = client_up or isinstance(event, PeerConnected)
            if peer is not None and client_up:
                return peer
        raise AssertionError("never connected")

    def add_player(self) -> tuple[NativeTransport, int]:
        client = self.network.add_client(self.key, self.host_address)
        return client, self._connect(client)

    def assert_player_is_fine(self) -> None:
        """Prove the honest player is connected, in both directions."""
        token = secrets.token_bytes(8)
        assert self.host.send(self.player_id, Channel.EVENTS, token)
        assert self.player.send(0, Channel.EVENTS, token)
        heard_by_player: list[TransportEvent] = []
        heard_by_host: list[TransportEvent] = []
        for _ in range(30):
            self.network.advance(DT)
            heard_by_player.extend(self.player.poll())
            heard_by_host.extend(self.host.poll())
        assert not [e for e in heard_by_player if isinstance(e, PeerDisconnected)]
        assert self.player_id not in [
            e.peer for e in heard_by_host if isinstance(e, PeerDisconnected)
        ]
        for heard in (heard_by_player, heard_by_host):
            assert [
                e.data
                for e in heard
                if isinstance(e, MessageDelivered) and e.data == token
            ] == [token]


def varint(value: int) -> bytes:
    """Encode the form of `octets`' varint that always fits."""
    return (value | (0b11 << 62)).to_bytes(8, "big")


def empty_packet(sequence: int) -> bytes:
    """A valid `renet` packet carrying nothing, so a flood is all it can be."""
    return b"\x01" + varint(sequence) + bytes([Channel.SNAPSHOT]) + bytes(2)


def slice_packet(sequence: int, index: int, count: int) -> bytes:
    """A `renet` reliable-slice packet, well formed apart from what it claims."""
    payload = bytes(1200)
    return (
        b"\x02"
        + varint(sequence)
        + bytes([Channel.EVENTS])
        + varint(0)
        + varint(index)
        + varint(count)
        + varint(len(payload))
        + payload
    )


@pytest.mark.parametrize("nibble", range(9, 16))
def test_one_datagram_with_a_long_sequence_does_not_panic_the_host(nibble: int) -> None:
    """Panics unguarded `renetcode` 2.0.0 at `packet.rs:375`, before any auth."""
    game = Game()
    datagram = bytes([nibble << 4 | 1]) + bytes(64)

    game.network.inject(ATTACKER, game.host_address, datagram)
    game.network.inject(game.host_address, game.player_address, datagram)

    assert game.host.counters()["panics"] == 0
    assert game.host.counters()["implausible"] == 1
    game.assert_player_is_fine()


# One byte would make it 17 long, under `renetcode`'s own minimum of 18.
@pytest.mark.parametrize("sequence_bytes", range(2, 9))
def test_one_datagram_too_short_for_its_mac_does_not_panic_the_host(
    sequence_bytes: int,
) -> None:
    """Panics unguarded `renetcode` 2.0.0 at `crypto.rs:10`, before any auth."""
    game = Game()
    length = sequence_bytes + 16  # one short of what the header implies
    datagram = bytes([sequence_bytes << 4 | 1]) + bytes(length - 1)

    game.network.inject(ATTACKER, game.host_address, datagram)
    game.network.inject(game.host_address, game.player_address, datagram)

    assert game.host.counters()["panics"] == 0
    game.assert_player_is_fine()


def _datagrams(rng: random.Random, real: list[bytes], count: int) -> list[bytes]:
    out: list[bytes] = []
    for i in range(count):
        kind = i % 4
        if kind == 0:
            out.append(rng.randbytes(rng.randrange(0, 1600)))
        elif kind == 1:
            sample = bytearray(rng.choice(real))
            for _ in range(rng.randrange(1, 5)):
                sample[rng.randrange(len(sample))] ^= 1 << rng.randrange(8)
            out.append(bytes(sample))
        elif kind == 2:
            length = rng.choice((0, 1, 2, 17, 18, 19, 20, 24, 25, 40, 1078, 1400, 1401))
            body = bytearray(rng.randbytes(length))
            if body:
                body[0] = rng.randrange(256)
            out.append(bytes(body))
        else:
            out.append(rng.choice(real)[: rng.randrange(0, 60)])
    return out


@pytest.mark.parametrize("seed", range(3))
def test_fuzzed_datagrams_from_a_stranger_change_nothing(seed: int) -> None:
    game = Game(seed)
    real: list[bytes] = []
    game.network.tap = lambda _, __, data: real.append(data)
    for _ in range(60):
        game.network.advance(DT)
    game.network.tap = None
    assert real

    rng = random.Random(seed)
    for number, datagram in enumerate(_datagrams(rng, real, 30_000)):
        game.network.inject(ATTACKER, game.host_address, datagram)
        game.network.inject(game.host_address, game.player_address, datagram)
        if number % 5000 == 0:
            game.network.advance(DT)

    assert game.host.counters()["panics"] == 0
    assert game.player.counters()["panics"] == 0
    assert game.host.counters()["implausible"] > 0
    assert not [e for e in game.host.poll() if isinstance(e, PeerConnected)]
    game.assert_player_is_fine()


def test_forged_datagrams_in_a_players_name_cannot_remove_them() -> None:
    """UDP source addresses are spoofable, so they must earn nothing."""
    game = Game()
    rng = random.Random(9)

    # Far over the per-peer budget, and each one claims to be the real player.
    for _ in range(20_000):
        game.network.inject(game.player_address, game.host_address, rng.randbytes(64))

    assert game.host.counters()["peer_over_budget"] == 0
    assert game.host.counters()["panics"] == 0
    game.assert_player_is_fine()


def test_forged_packets_never_reach_the_message_layer() -> None:
    game = Game()
    rng = random.Random(4)
    for _ in range(5000):
        body = bytes([rng.randrange(1, 8) | (rng.randrange(0, 9) << 4)])
        body += rng.randbytes(rng.randrange(40, 200))
        game.network.inject(game.player_address, game.host_address, body)
    game.network.advance(DT)

    events = game.host.poll()

    assert not [e for e in events if isinstance(e, MessageDelivered)]
    game.assert_player_is_fine()


def test_a_replayed_datagram_is_not_delivered_twice() -> None:
    game = Game()
    captured: list[bytes] = []
    game.network.tap = lambda source, _, data: (
        captured.append(data) if source == game.player_address else None
    )
    assert game.player.send(0, Channel.SNAPSHOT, b"once")
    heard: list[TransportEvent] = []
    for _ in range(5):
        game.network.advance(DT)
        heard.extend(game.host.poll())
    game.network.tap = None
    assert [e for e in heard if isinstance(e, MessageDelivered)]

    for datagram in captured * 3:
        game.network.inject(game.player_address, game.host_address, datagram)
    game.network.advance(DT)

    assert not [e for e in game.host.poll() if isinstance(e, MessageDelivered)]


def test_a_stolen_handshake_cannot_be_used_from_another_address() -> None:
    game = Game()
    network = game.network
    late = secrets.token_bytes(32)
    request: list[bytes] = []
    network.tap = lambda _, __, data: request.append(data) if not request else None
    newcomer_host = network.add_host(late, address="10.0.1.1:7000")
    network.add_client(late, "10.0.1.1:7000", address="10.0.1.2:7000")
    network.advance(DT)
    network.tap = None
    assert request

    network.inject(ATTACKER, "10.0.1.1:7000", request[0])
    network.advance(DT)
    network.advance(DT)

    connected = [e for e in newcomer_host.poll() if isinstance(e, PeerConnected)]
    assert len(connected) <= 1


def test_unauthenticated_flood_spends_a_shared_budget_and_stops_there() -> None:
    game = Game()
    rng = random.Random(1)

    for _ in range(2000):
        game.network.inject(ATTACKER, game.host_address, b"\x00" + rng.randbytes(1077))

    assert game.host.counters()["unauth_over_budget"] > 0
    game.assert_player_is_fine()


def test_a_client_ignores_datagrams_from_anywhere_but_its_host() -> None:
    game = Game()

    game.network.inject(ATTACKER, game.player_address, bytes(64))

    assert game.player.counters()["wrong_source"] == 1


def test_mismatched_slice_counts_from_an_invited_player_drop_only_them() -> None:
    """Panics unguarded `renet` 2.0.1 at `slice_constructor.rs:41`."""
    game = Game()
    attacker, attacker_id = game.add_player()
    assert attacker.endpoint._inject_payload(slice_packet(1, 0, 2))
    assert attacker.endpoint._inject_payload(slice_packet(2, 500, 1000))

    heard: list[TransportEvent] = []
    for _ in range(10):
        game.network.advance(DT)
        heard.extend(game.host.poll())

    assert game.host.counters()["panics"] == 1
    assert [e.peer for e in heard if isinstance(e, PeerDisconnected)] == [attacker_id]
    game.assert_player_is_fine()


@pytest.mark.parametrize("seed", range(3))
def test_structured_garbage_from_an_invited_player_harms_nobody_else(
    seed: int,
) -> None:
    game = Game(seed)
    rng = random.Random(seed)

    for _ in range(40):
        attacker, _ = game.add_player()
        for _ in range(rng.randrange(1, 40)):
            kind = rng.randrange(6)
            body = bytes([kind]) + rng.randbytes(rng.randrange(0, 600))
            attacker.endpoint._inject_payload(body)
        game.network.advance(DT)
        game.host.poll()
        game.network.remove(attacker)

    game.assert_player_is_fine()


def test_a_flooding_player_is_throttled_and_then_removed() -> None:
    game = Game()
    attacker, attacker_id = game.add_player()
    heard: list[TransportEvent] = []
    sequence = 0
    for _ in range(40):
        for _ in range(2000):
            sequence += 1
            attacker.endpoint._inject_payload(empty_packet(sequence))
        game.network.advance(DT)
        heard.extend(game.host.poll())

    assert game.host.counters()["peer_over_budget"] > 0
    assert attacker_id in [e.peer for e in heard if isinstance(e, PeerDisconnected)]
    game.assert_player_is_fine()


def test_a_client_cannot_make_the_host_allocate_past_its_channel_limit() -> None:
    """A slice header can claim a million slices. `renet` must refuse first."""
    game = Game()
    attacker, attacker_id = game.add_player()
    assert attacker.endpoint._inject_payload(slice_packet(1, 0, 900_000))

    heard: list[TransportEvent] = []
    for _ in range(5):
        game.network.advance(DT)
        heard.extend(game.host.poll())

    assert [e.peer for e in heard if isinstance(e, PeerDisconnected)] == [attacker_id]
    game.assert_player_is_fine()


def test_hostile_traffic_under_a_bad_network_still_leaves_the_player_connected() -> (
    None
):
    game = Game(7)
    game.network.conditions = LinkConditions(latency=0.05, jitter=0.03, loss=0.05)
    rng = random.Random(7)
    for _ in range(300):
        game.network.inject(ATTACKER, game.host_address, rng.randbytes(64))
        game.network.inject(game.player_address, game.host_address, rng.randbytes(64))
        game.network.advance(DT)

    assert game.host.counters()["panics"] == 0
    game.network.conditions = LinkConditions()
    game.network.advance(1.0)
    game.host.poll()
    game.player.poll()
    game.assert_player_is_fine()


def test_the_release_profile_unwinds() -> None:
    """`panic = "abort"` would turn every guarded panic back into a host crash."""
    manifest = tomllib.loads(Path("Cargo.toml").read_text())

    assert manifest["profile"]["release"].get("panic", "unwind") == "unwind"


def test_the_guarded_crates_are_pinned_exactly() -> None:
    """A new version needs the parsers re-read and this suite re-run."""
    dependencies = tomllib.loads(Path("Cargo.toml").read_text())["dependencies"]

    assert dependencies["renet"].startswith("=")
    assert dependencies["renetcode"].startswith("=")
