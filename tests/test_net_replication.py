"""A client's world matching the host's, through a seeded network.

These use the real session and the real Rust core. The convergence tests are the point:
after loss stops, every client must hold exactly what the host says it should.
"""

from __future__ import annotations

import enum
import math
import random
import secrets
import struct
from dataclasses import dataclass, field

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.component import StrictComponent
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.net import (
    Angle,
    Channel,
    ClientDriver,
    ClientSession,
    EnumField,
    Flag,
    HostDriver,
    HostSession,
    LinkConditions,
    Quantised,
    QuantisedVector,
    Replicated,
    ReplicationClient,
    ReplicationHost,
    ReplicationSchema,
    SimulatedNetwork,
    UInt8,
    UInt16,
    Versions,
)
from pyguara.net.replication import FIRST_RESERVED_KIND

DT = 1 / 60
VERSIONS = Versions("test", "test")
STEP = 0.25
BAD_NETWORK = LinkConditions(
    latency=0.05, jitter=0.03, loss=0.2, duplicate=0.02, reorder=0.1
)


@dataclass(slots=True)
class Vitals(StrictComponent):
    current: int = 100

    def __post_init__(self) -> None:
        StrictComponent.__init__(self)


def make_schema() -> ReplicationSchema:
    schema = ReplicationSchema()
    schema.register(Transform, position=QuantisedVector(step=STEP), rotation=Angle(16))
    schema.register(Vitals, current=UInt16())
    return schema


@dataclass
class Player:
    session: ClientSession
    replication: ReplicationClient
    driver: ClientDriver
    world: EntityManager
    other_messages: list[object] = field(default_factory=list)


class Game:
    """A host and its players, stepped together with an explicit clock."""

    def __init__(
        self,
        seed: int = 1,
        conditions: LinkConditions | None = None,
        players: int = 1,
        **host_options: object,
    ) -> None:
        self.network = SimulatedNetwork(seed=seed, conditions=conditions)
        self.key = secrets.token_bytes(32)
        transport = self.network.add_host(self.key)
        self.address = self.network.address_of(transport)
        self.session = HostSession(transport, VERSIONS)
        self.world = EntityManager()
        self.fixed_tick = 0
        host_options.setdefault("digest_every", 1)
        self.replication = ReplicationHost(
            self.world,
            make_schema(),
            self.session.send,
            **host_options,  # type: ignore[arg-type]
        )
        self.driver = HostDriver(self, self.session, self.replication)
        self.players = [self.add_player() for _ in range(players)]

    def add_player(self) -> Player:
        world = EntityManager()

        def spawn() -> Entity:
            entity = world.create_entity()
            entity.add_component(Transform())
            entity.add_component(Vitals())
            return entity

        transport = self.network.add_client(self.key, self.address, VERSIONS.encode())
        session = ClientSession(transport)
        replication = ReplicationClient(world, make_schema(), {"enemy": spawn})
        player = Player(session, replication, None, world)  # type: ignore[arg-type]
        player.driver = ClientDriver(
            session, replication, on_event=player.other_messages.append
        )
        return player

    def spawn(self, x: float = 0.0, y: float = 0.0, owner: int | None = None) -> Entity:
        entity = self.world.create_entity()
        entity.add_component(Transform(position=Vector2(x, y)))
        entity.add_component(Vitals())
        entity.add_component(Replicated("enemy", owner=owner))
        return entity

    def frame(self, simulate: object = None) -> None:
        self.network.advance(DT)
        self.driver.before_fixed_updates(DT)
        for player in self.players:
            player.driver.before_fixed_updates(DT)
        if simulate is not None:
            simulate()  # type: ignore[operator]
        self.fixed_tick += 1
        self.driver.after_fixed_updates(DT)
        for player in self.players:
            player.driver.after_fixed_updates(DT)

    def run(self, seconds: float, simulate: object = None) -> None:
        for _ in range(round(seconds / DT)):
            self.frame(simulate)

    def join(self, seconds: float = 8.0) -> None:
        for _ in range(round(seconds / DT)):
            self.frame()
            if all(p.session.joined for p in self.players) and len(
                self.session.players
            ) == len(self.players):
                return
        raise AssertionError("players never joined")

    def heal_network(self, seconds: float = 3.0) -> None:
        """Stop all loss, then let reliable traffic and snapshots settle."""
        self.network.conditions = LinkConditions()
        self.run(seconds)


def host_entities(game: Game, slot: int | None) -> list[Entity]:
    return [
        e
        for e in game.world.get_entities_with(Replicated)
        if slot is None
        or e.get_component(Replicated).owner is None
        or e.get_component(Replicated).owner == slot
    ]


def snap(value: float) -> float:
    return round(value / STEP) * STEP


def state_of(entity: Entity) -> tuple[float, float, int]:
    transform = entity.get_component(Transform)
    return (
        snap(transform.position.x),
        snap(transform.position.y),
        entity.get_component(Vitals).current,
    )


def assert_converged(game: Game, player: Player, slot: int | None = None) -> None:
    """Exactly what the host says this player should have, and no more."""
    theirs = sorted(state_of(e) for e in player.replication.entities().values())
    ours = sorted(state_of(e) for e in host_entities(game, slot))
    assert theirs == ours
    assert player.replication.digests_mismatched == 0


def churn(game: Game, rng: random.Random, alive: list[Entity]) -> None:
    """Spawn, kill and move, as a horde does."""
    if rng.random() < 0.3:
        alive.append(game.spawn(rng.uniform(0, 500), rng.uniform(0, 500)))
    if alive and rng.random() < 0.2:
        game.world.remove_entity(alive.pop(rng.randrange(len(alive))).id)
    for entity in alive:
        transform = entity.get_component(Transform)
        transform.position += Vector2(rng.uniform(-3, 3), rng.uniform(-3, 3))
        transform.rotation = rng.uniform(0, math.tau)
        if rng.random() < 0.01:
            entity.get_component(Vitals).current = rng.randrange(1000)


@pytest.mark.parametrize("seed", range(10))
def test_a_client_converges_after_loss_stops(seed: int) -> None:
    game = Game(seed, conditions=BAD_NETWORK)
    game.join()
    rng = random.Random(seed)
    alive = [game.spawn(rng.uniform(0, 500), 0) for _ in range(40)]

    game.run(8.0, lambda: churn(game, rng, alive))
    game.heal_network()

    assert len(alive) > 5
    assert_converged(game, game.players[0])
    assert game.players[0].replication.digests_matched > 0


@pytest.mark.parametrize(
    "conditions",
    [
        LinkConditions(),
        LinkConditions(latency=0.05),
        LinkConditions(latency=0.1, jitter=0.02, loss=0.02),
        LinkConditions(latency=0.2, jitter=0.05, loss=0.1),
        LinkConditions(latency=0.05, jitter=0.1, reorder=0.3, reorder_delay=0.3),
    ],
    ids=["perfect", "50ms", "100ms-2pct", "200ms-10pct", "heavy-reorder"],
)
def test_convergence_across_the_condition_matrix(conditions: LinkConditions) -> None:
    game = Game(4, conditions=conditions)
    game.join()
    rng = random.Random(4)
    alive = [game.spawn(i * 10.0) for i in range(30)]

    game.run(5.0, lambda: churn(game, rng, alive))
    game.heal_network()

    assert_converged(game, game.players[0])


def test_digests_agree_while_running_on_a_perfect_network() -> None:
    game = Game(2)
    game.join()
    rng = random.Random(2)
    alive = [game.spawn(i * 5.0) for i in range(20)]

    game.run(5.0, lambda: churn(game, rng, alive))

    replication = game.players[0].replication
    assert replication.digests_matched > 50
    assert replication.digests_mismatched == 0


def test_a_tampered_client_state_is_caught_by_the_digest() -> None:
    """The digest has to be able to fail, or a clean run proves nothing."""
    game = Game(2)
    game.join()
    game.spawn(10.0)
    game.run(1.0)
    replication = game.players[0].replication
    assert replication.digests_mismatched == 0

    remote = next(iter(replication._remotes.values()))
    sample = remote.history[-1]
    remote.history[-1] = type(sample)(sample.tick, b"tampered", sample.values)
    # Hold the remote's newest record still: `update` keeps comparing it to the next.
    tampered_tick = sample.tick
    message = struct.pack("<BIII", 0xE5, tampered_tick, 1, 0)
    replication.handle_message(Channel.SNAPSHOT, message)

    assert replication.digests_mismatched == 1


def test_a_snapshot_for_an_entity_with_no_spawn_invents_nothing() -> None:
    game = Game(1)
    client = game.players[0].replication
    record = struct.pack("<BIHH", 0xE1, 100, 77, 0b10) + struct.pack("<H", 5)

    client.handle_message(Channel.SNAPSHOT, record)
    client.update(DT)

    assert client.entities() == {}
    assert client.unknown_records == 1
    assert client.malformed == 0


def test_a_late_snapshot_cannot_bring_a_dead_enemy_back() -> None:
    game = Game(1)
    game.join()
    enemy = game.spawn(50.0)
    game.run(1.0)
    client = game.players[0].replication
    assert len(client.entities()) == 1
    net_id = next(iter(client.entities()))
    late = struct.pack("<BIHH", 0xE1, game.fixed_tick, net_id, 0b10) + struct.pack(
        "<H", 1
    )

    game.world.remove_entity(enemy.id)
    game.run(0.5)
    assert client.entities() == {}
    client.handle_message(Channel.SNAPSHOT, late)
    game.run(0.5)

    assert client.entities() == {}
    assert client.unknown_records >= 1


def test_an_older_snapshot_does_not_overwrite_a_newer_one() -> None:
    game = Game(1)
    game.join()
    enemy = game.spawn(0.0)
    game.run(1.0)
    client = game.players[0].replication
    net_id = next(iter(client.entities()))
    before = client.stale_records
    old = struct.pack("<BIHH", 0xE1, 1, net_id, 0b10) + struct.pack("<H", 999)

    client.handle_message(Channel.SNAPSHOT, old)
    game.run(0.5)

    assert client.stale_records == before + 1
    assert state_of(client.entities()[net_id]) == state_of(enemy)


def test_a_spawn_and_despawn_in_one_frame_tells_nobody() -> None:
    game = Game(1)
    game.join()
    game.run(0.5)
    sent: list[bytes] = []
    real_send = game.replication._send

    def recording(peer: int, channel: Channel, data: bytes) -> bool:
        sent.append(data)
        return real_send(peer, channel, data)

    game.replication._send = recording  # type: ignore[assignment]

    enemy = game.spawn(1.0)
    game.world.remove_entity(enemy.id)
    game.frame()

    assert not [m for m in sent if m[0] in (0xE2, 0xE3)]


def test_spawn_and_despawn_run_on_the_delayed_timeline_not_on_arrival() -> None:
    game = Game(1)
    game.join()
    game.run(0.5)
    enemy = game.spawn(5.0)
    client = game.players[0].replication

    while not client.latest_records():
        game.frame()
    assert client.entities() == {}, "drawn before the motion around it"
    game.run(0.3)
    assert len(client.entities()) == 1

    game.world.remove_entity(enemy.id)
    while client.latest_records():
        game.frame()
    assert len(client.entities()) == 1, "removed ahead of the motion around it"
    game.run(0.3)
    assert client.entities() == {}


def test_motion_is_smooth_and_about_100ms_behind() -> None:
    game = Game(1, conditions=LinkConditions(latency=0.02))
    game.join()
    enemy = game.spawn(0.0)
    speed = 2.0  # units per tick
    transform = enemy.get_component(Transform)

    def move() -> None:
        transform.position += Vector2(speed, 0)

    game.run(1.0, move)
    client = game.players[0].replication
    seen = next(iter(client.entities().values())).get_component(Transform)
    steps = []
    lag = []
    for _ in range(120):
        before = seen.position.x
        game.frame(move)
        steps.append(seen.position.x - before)
        lag.append(transform.position.x - seen.position.x)

    assert max(steps) < speed * 1.6
    assert min(steps) > speed * 0.4
    # 6 ticks of interpolation plus 20 ms each way plus up to one snapshot of 3 ticks.
    assert speed * 4 < sum(lag) / len(lag) < speed * 16


def test_one_lost_snapshot_does_not_stutter() -> None:
    game = Game(1)
    game.join()
    enemy = game.spawn(0.0)
    transform = enemy.get_component(Transform)
    speed = 2.0

    def move() -> None:
        transform.position += Vector2(speed, 0)

    game.run(1.0, move)
    seen = next(iter(game.players[0].replication.entities().values())).get_component(
        Transform
    )
    host_address = game.address
    lost: list[bytes] = []

    def lose_one_snapshot(source: str, _: str, data: bytes) -> bool:
        if source == host_address and len(data) > 30 and not lost:
            lost.append(data)
            return True
        return False

    game.network.drop = lose_one_snapshot
    steps = []
    for _ in range(30):
        before = seen.position.x
        game.frame(move)
        steps.append(seen.position.x - before)

    assert lost
    assert min(steps) > 0
    assert max(steps) < speed * 2


def test_a_teleport_is_drawn_at_once_rather_than_as_a_streak() -> None:
    game = Game(1)
    game.join()
    enemy = game.spawn(0.0)
    game.run(1.0)
    seen = next(iter(game.players[0].replication.entities().values())).get_component(
        Transform
    )
    enemy.get_component(Transform).position = Vector2(3000, 0)

    positions = []
    for _ in range(40):
        game.frame()
        positions.append(seen.position.x)

    assert positions[-1] == 3000
    assert not [x for x in positions if 1 < x < 2999]


def test_drops_are_seen_only_by_their_owner() -> None:
    game = Game(1, players=3)
    game.join()
    assert sorted(game.session.slot_of(p) for p in game.session.players) == [1, 2, 3]
    own = [game.spawn(float(slot), owner=slot) for slot in (1, 2, 3)]
    shared = game.spawn(100.0)

    game.run(1.0)

    for slot, player in zip((1, 2, 3), _players_by_slot(game), strict=True):
        states = sorted(state_of(e) for e in player.replication.entities().values())
        assert states == sorted([state_of(own[slot - 1]), state_of(shared)]), (
            f"slot {slot} sees the wrong drops"
        )
        assert_converged(game, player, slot)
        assert player.replication.digests_matched > 0


def _players_by_slot(game: Game) -> list[Player]:
    """Match each client to its slot, from what its `Joined` said."""
    by_slot: dict[int, Player] = {}
    for player in game.players:
        joined = [e for e in player.other_messages if type(e).__name__ == "Joined"]
        by_slot[joined[0].slot] = player  # type: ignore[attr-defined]
    return [by_slot[slot] for slot in sorted(by_slot)]


def test_a_drop_never_reaches_a_client_that_does_not_own_it_even_on_the_wire() -> None:
    """Nothing to find in a hacked client, or a packet capture."""
    game = Game(1, players=2)
    game.join()
    game.run(0.2)
    sent_to: dict[int, list[bytes]] = {}
    real_send = game.replication._send

    def recording(peer: int, channel: Channel, data: bytes) -> bool:
        sent_to.setdefault(peer, []).append(data)
        return real_send(peer, channel, data)

    game.replication._send = recording  # type: ignore[assignment]
    game.spawn(1.0, owner=1)
    game.run(0.5)

    other = next(p for p in game.session.players if game.session.slot_of(p) == 2)
    owner = next(p for p in game.session.players if game.session.slot_of(p) == 1)
    assert [m for m in sent_to[owner] if m[0] == 0xE2]
    assert not [m for m in sent_to[other] if m[0] in (0xE1, 0xE2, 0xE3)]


def test_collecting_a_drop_removes_it_only_for_its_owner() -> None:
    game = Game(1, players=2)
    game.join()
    drop = game.spawn(1.0, owner=1)
    game.run(0.5)
    owner = _players_by_slot(game)[0]
    other = _players_by_slot(game)[1]
    assert len(owner.replication.entities()) == 1
    assert other.replication.entities() == {}

    game.world.remove_entity(drop.id)
    game.run(0.5)

    assert owner.replication.entities() == {}
    assert other.replication.unknown_records == 0


def test_a_player_joining_before_the_run_receives_everything_already_spawned() -> None:
    game = Game(1, players=0)
    enemies = [game.spawn(i * 3.0) for i in range(5)]
    game.run(0.5)
    player = game.add_player()
    game.players.append(player)

    game.join()
    game.run(1.0)

    assert len(enemies) == len(player.replication.entities())
    assert_converged(game, player)


@pytest.mark.parametrize("seed", range(20))
def test_a_world_spawned_before_joining_arrives_whole_on_a_bad_network(
    seed: int,
) -> None:
    """Spawns are sent as the player is admitted, so they can overtake its welcome.

    A demo found this: the session dropped what arrived first, so a client could join
    and never see the 200 enemies that already existed.
    """
    game = Game(seed, conditions=LinkConditions(latency=0.05, jitter=0.02, loss=0.2))
    enemies = [game.spawn(i * 2.0) for i in range(200)]
    game.run(0.2)

    game.join(15.0)
    game.heal_network()

    assert len(game.players[0].replication.entities()) == len(enemies)
    assert_converged(game, game.players[0])


def test_a_leaving_player_harms_nobody_else() -> None:
    game = Game(1, players=2)
    game.join()
    game.spawn(1.0)
    game.run(0.5)
    leaver = game.players.pop()
    leaver.session.close()
    game.run(0.5)
    game.spawn(2.0)
    game.run(1.0)

    assert game.replication._peers.keys() == game.session.players
    assert_converged(game, game.players[0])


def test_a_replaced_component_is_read_from_its_replacement() -> None:
    """Parts are held by reference for speed, which a replacement would make stale."""
    game = Game(1)
    game.join()
    enemy = game.spawn(0.0)
    game.run(0.5)

    enemy.remove_component(Vitals)
    enemy.add_component(Vitals(current=7))
    game.run(0.5)

    remote = next(iter(game.players[0].replication.entities().values()))
    assert remote.get_component(Vitals).current == 7


def test_a_component_added_after_the_spawn_starts_replicating() -> None:
    game = Game(1)
    game.join()
    enemy = game.world.create_entity()
    enemy.add_component(Replicated("enemy"))
    enemy.add_component(Transform(position=Vector2(9, 0)))
    game.run(0.3)
    enemy.add_component(Vitals(current=3))
    game.run(0.5)

    remote = next(iter(game.players[0].replication.entities().values()))
    assert remote.get_component(Vitals).current == 3
    assert remote.get_component(Transform).position.x == 9


def test_a_freed_id_is_not_reused_while_a_late_record_could_still_arrive() -> None:
    game = Game(1, players=0)
    first = game.spawn()
    game.replication.step(1)
    first_id = game.replication._tracked[first.id].net_id
    game.world.remove_entity(first.id)

    second = game.spawn()
    game.replication.step(2)

    assert game.replication._tracked[second.id].net_id != first_id


def test_a_freed_id_comes_back_after_its_quarantine() -> None:
    game = Game(1, players=0)
    first = game.spawn()
    game.replication.step(1)
    first_id = game.replication._tracked[first.id].net_id
    game.world.remove_entity(first.id)
    game.replication.step(1 + 30 * 60 + 2)

    second = game.spawn()

    assert game.replication._tracked[second.id].net_id == first_id


def test_running_out_of_ids_is_counted_not_fatal() -> None:
    game = Game(1, players=0)
    game.replication._next_id = 65536

    game.spawn()

    assert game.replication.unreplicated == 1
    assert game.replication.tracked_count == 0


@pytest.mark.parametrize("name", ["", "x" * 65])
def test_a_prefab_name_that_cannot_be_sent_is_counted_not_fatal(name: str) -> None:
    game = Game(1, players=0)
    entity = game.world.create_entity()

    entity.add_component(Replicated(name))

    assert game.replication.unreplicated == 1
    assert game.replication.tracked_count == 0


def test_over_budget_snapshots_rotate_so_nothing_starves() -> None:
    game = Game(1, max_snapshot_bytes=200)
    game.join()
    enemies = [game.spawn(i * 1.0) for i in range(100)]
    game.run(0.5)

    for enemy in enemies:
        enemy.get_component(Vitals).current = 42
    game.run(3.0)

    client = game.players[0].replication
    assert game.replication.skipped_records > 0
    assert len(client.entities()) == len(enemies)
    assert {e.get_component(Vitals).current for e in client.entities().values()} == {42}


def test_a_large_snapshot_is_split_into_messages_that_each_fit_a_datagram() -> None:
    game = Game(1)
    game.join()
    for i in range(500):
        game.spawn(i * 1.0)
    sizes: list[int] = []
    real_send = game.replication._send

    def recording(peer: int, channel: Channel, data: bytes) -> bool:
        if channel == Channel.SNAPSHOT:
            sizes.append(len(data))
        return real_send(peer, channel, data)

    game.replication._send = recording  # type: ignore[assignment]
    game.run(1.0)

    assert max(sizes) <= 1100
    assert len(game.players[0].replication.entities()) == 500


def test_a_refused_reliable_send_is_held_and_delivered_in_order() -> None:
    """A lost spawn would be a permanent desync, so it must wait for room."""
    world = EntityManager()
    sent: list[bytes] = []
    accept = [False]

    def send(peer: int, channel: Channel, data: bytes) -> bool:
        if channel == Channel.EVENTS:
            if not accept[0]:
                return False
            sent.append(data)
        return True

    host = ReplicationHost(world, make_schema(), send)
    host.add_peer(5, 1)
    for i in range(3):
        entity = world.create_entity()
        entity.add_component(Transform(position=Vector2(i, 0)))
        entity.add_component(Replicated("enemy"))
    host.step(1)
    assert sent == []

    accept[0] = True
    host.step(2)

    assert [m[0] for m in sent] == [0xE4, 0xE2, 0xE2, 0xE2]
    assert [struct.unpack_from("<H", m, 5)[0] for m in sent[1:]] == [0, 1, 2]


def test_a_peer_that_cannot_keep_up_is_reported() -> None:
    world = EntityManager()
    behind: list[int] = []
    host = ReplicationHost(
        world,
        make_schema(),
        lambda peer, channel, data: channel != Channel.EVENTS,
        on_backlog=behind.append,
    )
    host.add_peer(5, 1)
    for _ in range(9000):
        entity = world.create_entity()
        entity.add_component(Replicated("enemy"))
    host.step(1)

    assert behind == [5]


def test_a_game_message_is_left_for_the_game() -> None:
    game = Game(1)
    game.join()
    game.run(0.1)
    client = game.players[0].replication

    assert client.handle_message(Channel.EVENTS, b"\x01damage") is False
    assert client.handle_message(Channel.EVENTS, b"") is False
    assert client.malformed == 0


def test_game_messages_reach_the_game_through_the_driver() -> None:
    game = Game(1)
    game.join()
    peer = next(iter(game.session.players))
    game.session.send(peer, Channel.EVENTS, b"\x01damage")
    game.run(0.2)

    assert [
        e.data  # type: ignore[attr-defined]
        for e in game.players[0].other_messages
        if type(e).__name__ == "MessageReceived"
    ] == [b"\x01damage"]


def test_a_different_schema_stops_the_client_and_says_why() -> None:
    game = Game(1)
    other = ReplicationSchema()
    other.register(Transform, position=QuantisedVector(step=1.0, wide=True))
    player = game.players[0]
    player.replication._schema = other
    game.join()
    game.spawn(1.0)

    game.run(1.0)

    assert player.replication.failed is not None
    assert "schema" in player.replication.failed
    assert player.replication.entities() == {}


def test_a_name_from_the_network_can_only_choose_among_the_spawners() -> None:
    game = Game(1)
    client = game.players[0].replication
    called: list[str] = []
    client._spawners = {"enemy": lambda: called.append("enemy")}  # type: ignore[assignment,return-value,func-returns-value]
    name = b"../../evil"
    message = struct.pack("<BIHB", 0xE2, 10, 1, len(name)) + name + struct.pack("<H", 0)

    client.handle_message(Channel.EVENTS, message)
    for _ in range(30):
        client.update(DT)

    assert called == []
    assert client.entities() == {}
    assert client.malformed == 1


def test_a_failing_spawner_does_not_end_the_frame() -> None:
    def boom() -> Entity:
        raise RuntimeError("spawner bug")

    client = ReplicationClient(EntityManager(), make_schema(), {"enemy": boom})
    name = b"enemy"
    message = struct.pack("<BIHB", 0xE2, 10, 1, len(name)) + name + struct.pack("<H", 0)

    client.handle_message(Channel.EVENTS, message)
    for _ in range(30):
        client.update(DT)

    assert client.malformed == 1
    assert client.entities() == {}


@pytest.mark.parametrize("seed", range(3))
def test_hostile_messages_never_raise_and_never_invent_entities(seed: int) -> None:
    game = Game(seed)
    game.join()
    game.spawn(1.0)
    real: list[tuple[Channel, bytes]] = []
    real_send = game.replication._send

    def recording(peer: int, channel: Channel, data: bytes) -> bool:
        real.append((channel, data))
        return real_send(peer, channel, data)

    game.replication._send = recording  # type: ignore[assignment]
    game.spawn(2.0)
    game.run(0.5)
    assert real

    client = ReplicationClient(EntityManager(), make_schema(), {})
    rng = random.Random(seed)
    for _ in range(40_000):
        channel, data = rng.choice(real)
        kind = rng.randrange(3)
        if kind == 0:
            body = bytearray(data)
            for _ in range(rng.randrange(1, 6)):
                body[rng.randrange(len(body))] = rng.randrange(256)
            data = bytes(body)
        elif kind == 1:
            data = data[: rng.randrange(len(data) + 1)]
        else:
            data = bytes([rng.randrange(0xE0, 0x100)]) + rng.randbytes(
                rng.randrange(60)
            )
        client.handle_message(rng.choice(list(Channel)), data)
        if rng.random() < 0.01:
            client.update(DT)

    assert client.entities() == {}
    assert client.malformed > 0


def test_replication_kinds_stay_above_the_games_range() -> None:
    assert FIRST_RESERVED_KIND == 0xE0


def test_saturation_is_counted_rather_than_wrapping() -> None:
    codec = QuantisedVector(step=1.0)

    assert codec.encode(Vector2(40000, -40000)) == (32767, -32768)
    assert codec.saturated == 2


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_value_on_the_host_sends_zero_and_is_counted(bad: float) -> None:
    for codec, value in (
        (Quantised(step=0.5), bad),
        (Angle(), bad),
        (UInt8(), bad),
    ):
        assert codec.encode(value) == (0,)
        assert codec.saturated == 1


def test_angles_round_trip_and_blend_the_short_way_round() -> None:
    codec = Angle(bits=16)
    almost_full = math.tau - 0.1

    assert codec.decode(codec.encode(almost_full)) == pytest.approx(
        almost_full, abs=1e-3
    )
    blended = codec.blend(almost_full, 0.1, 0.5)
    assert math.cos(blended) == pytest.approx(1.0, abs=1e-6)


class Mood(enum.Enum):
    CALM = "calm"
    ANGRY = "angry"


def test_enum_and_flag_reject_values_they_cannot_hold() -> None:
    enum_codec = EnumField(Mood)
    assert enum_codec.decode(enum_codec.encode(Mood.ANGRY)) is Mood.ANGRY
    with pytest.raises(ValueError):
        enum_codec.decode((9,))
    flag = Flag()
    assert flag.decode(flag.encode(True)) is True
    with pytest.raises(ValueError):
        flag.decode((2,))


def test_the_fingerprint_changes_with_the_layout() -> None:
    a = ReplicationSchema()
    a.register(Transform, position=QuantisedVector(step=1.0))
    b = ReplicationSchema()
    b.register(Transform, position=QuantisedVector(step=1.0, wide=True))
    c = ReplicationSchema()
    c.register(Transform, position=QuantisedVector(step=1.0))

    assert a.fingerprint() != b.fingerprint()
    assert a.fingerprint() == c.fingerprint()


def test_a_bad_schema_is_refused_when_it_is_written() -> None:
    schema = ReplicationSchema()
    schema.register(Transform, position=QuantisedVector(step=1.0))
    with pytest.raises(ValueError, match="already"):
        schema.register(Transform, rotation=Angle())
    with pytest.raises(ValueError, match="field"):
        schema.register(Vitals)
    with pytest.raises(ValueError, match="step"):
        Quantised(step=0)
