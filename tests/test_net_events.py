"""Game events reaching every client, through a seeded network.

A host's hits, kills and heals have to agree on every screen. These use the real
session and the real Rust core, and check the three things that make events worth
having: each arrives exactly once and in order, it lands on the delayed timeline with
the snapshot it belongs to, and an entity it names is the client's own entity.
"""

from __future__ import annotations

import enum
import secrets
import struct
from dataclasses import dataclass, field

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.net import (
    Channel,
    Choice,
    ClientDriver,
    ClientSession,
    EntityRef,
    EnumField,
    EventRelay,
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
    UInt16,
    Versions,
)

DT = 1 / 60
VERSIONS = Versions("test", "test")
BAD_NETWORK = LinkConditions(
    latency=0.05, jitter=0.03, loss=0.2, duplicate=0.02, reorder=0.1
)
SKILLS = ("shot", "multishot", "caltrops")


class Kind(enum.Enum):
    PHYSICAL = enum.auto()
    ENERGY = enum.auto()


@dataclass
class Hit:
    target: str | None
    amount: float
    kind: Kind = Kind.PHYSICAL
    killed: bool = False
    timestamp: float = 0.0
    source: object = None


@dataclass
class SkillUsed:
    user: str | None
    skill: str


@dataclass
class Restarted:
    pass


@dataclass
class Picky:
    value: int

    def __post_init__(self) -> None:
        if self.value == 7:
            raise ValueError("seven is refused")


@dataclass
class Unsent:
    value: int = 0


def make_schema(skills: tuple[str, ...] = SKILLS) -> ReplicationSchema:
    schema = ReplicationSchema()
    schema.register(Transform, position=QuantisedVector(step=0.25))
    schema.register_event(
        Hit,
        target=EntityRef(),
        amount=Quantised(step=0.01, wide=True),
        kind=EnumField(Kind),
        killed=Flag(),
    )
    schema.register_event(SkillUsed, user=EntityRef(), skill=Choice(skills))
    schema.register_event(Restarted)
    schema.register_event(Picky, value=UInt16())
    return schema


@dataclass
class Player:
    session: ClientSession
    replication: ReplicationClient
    driver: ClientDriver
    world: EntityManager
    heard: list[object] = field(default_factory=list)


class Game:
    """A host and its players, stepped together with an explicit clock."""

    def __init__(
        self,
        seed: int = 1,
        conditions: LinkConditions | None = None,
        players: int = 1,
        client_schema: ReplicationSchema | None = None,
    ) -> None:
        self.network = SimulatedNetwork(seed=seed, conditions=conditions)
        self.key = secrets.token_bytes(32)
        transport = self.network.add_host(self.key)
        self.address = self.network.address_of(transport)
        self.session = HostSession(transport, VERSIONS)
        self.world = EntityManager()
        self.dispatcher = EventDispatcher()
        self.fixed_tick = 0
        self.replication = ReplicationHost(
            self.world, make_schema(), self.session.send, digest_every=1
        )
        self.driver = HostDriver(self, self.session, self.replication)
        self.client_schema = client_schema
        self.players = [self.add_player() for _ in range(players)]

    def add_player(self) -> Player:
        world = EntityManager()
        heard: list[object] = []

        def spawn() -> Entity:
            entity = world.create_entity()
            entity.add_component(Transform())
            return entity

        transport = self.network.add_client(self.key, self.address, VERSIONS.encode())
        session = ClientSession(transport)
        replication = ReplicationClient(
            world,
            self.client_schema or make_schema(),
            {"enemy": spawn},
            on_event=heard.append,
        )
        driver = ClientDriver(session, replication)
        return Player(session, replication, driver, world, heard)

    def spawn(self, x: float = 0.0) -> Entity:
        entity = self.world.create_entity()
        entity.add_component(Transform(position=Vector2(x, 0.0)))
        entity.add_component(Replicated("enemy"))
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

    def connect(self) -> None:
        for _ in range(240):
            self.frame()
            if all(p.session.joined for p in self.players) and len(
                self.session.players
            ) == len(self.players):
                return
        raise AssertionError("players did not join")

    def run(self, frames: int) -> None:
        for _ in range(frames):
            self.frame()

    def send(self, event: object, slot: int | None = None) -> None:
        self.replication.send_event(event, self.fixed_tick + 1, slot)

    def local(self, player: Player, host_entity: Entity) -> str:
        net_id = self.replication.net_id_of(host_entity.id)
        assert net_id is not None
        return player.replication.entities()[net_id].id


def started(**options: object) -> Game:
    game = Game(**options)  # type: ignore[arg-type]
    game.connect()
    return game


# --- The schema ---------------------------------------------------------------


def test_an_event_must_be_a_dataclass() -> None:
    class Plain:
        pass

    with pytest.raises(ValueError, match="must be a dataclass"):
        ReplicationSchema().register_event(Plain)


def test_an_event_registers_once() -> None:
    schema = ReplicationSchema()
    schema.register_event(Restarted)
    with pytest.raises(ValueError, match="already registered"):
        schema.register_event(Restarted)


def test_a_misspelt_field_names_the_right_one() -> None:
    with pytest.raises(ValueError, match="did you mean 'amount'"):
        ReplicationSchema().register_event(
            Hit, target=EntityRef(), amonut=Quantised(0.1)
        )


def test_a_field_without_a_default_must_be_sent() -> None:
    with pytest.raises(ValueError, match="Hit.amount has no default"):
        ReplicationSchema().register_event(Hit, target=EntityRef())


def test_a_field_with_a_default_can_stay_home() -> None:
    schema = ReplicationSchema()
    schema.register_event(Hit, target=EntityRef(), amount=Quantised(0.1))
    layout = schema.event_layout(Hit)
    assert layout is not None
    values = layout.decode(layout.encode(Hit("e", 2.5), lambda _: 3), 0)
    event = layout.build(values, lambda net_id: f"local-{net_id}")
    assert event == Hit("local-3", 2.5)


def test_an_event_too_large_is_refused() -> None:
    fields = {f"f{i}": UInt16() for i in range(300)}
    Wide = dataclass(type("Wide", (), {"__annotations__": dict.fromkeys(fields, int)}))
    with pytest.raises(ValueError, match="too large"):
        ReplicationSchema().register_event(Wide, **fields)  # type: ignore[arg-type]


def test_events_change_the_fingerprint_and_their_absence_does_not() -> None:
    plain = ReplicationSchema()
    plain.register(Transform, position=QuantisedVector(step=0.25))
    again = ReplicationSchema()
    again.register(Transform, position=QuantisedVector(step=0.25))
    assert plain.fingerprint() == again.fingerprint()
    again.register_event(Restarted)
    assert plain.fingerprint() != again.fingerprint()


def test_a_choices_values_are_in_the_fingerprint() -> None:
    assert (
        make_schema(SKILLS).fingerprint()
        != make_schema(("shot", "caltrops", "multishot")).fingerprint()
    )


def test_a_choice_sends_its_position() -> None:
    choice = Choice(SKILLS)
    assert choice.encode("caltrops") == (2,)
    assert choice.decode((1,)) == "multishot"


def test_a_choice_counts_a_value_it_does_not_list() -> None:
    choice = Choice(SKILLS)
    assert choice.encode("fireball") == (0,)
    assert choice.saturated == 1


def test_a_choice_refuses_a_position_past_its_values() -> None:
    with pytest.raises(ValueError):
        Choice(SKILLS).decode((3,))


@pytest.mark.parametrize("values", [(), ("a", "a"), tuple(str(i) for i in range(257))])
def test_a_choice_needs_distinct_values_that_fit(values: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        Choice(values)


@pytest.mark.parametrize("wire", [-2, 65536, 2**31 - 1])
def test_an_entity_ref_refuses_what_cannot_be_a_network_id(wire: int) -> None:
    with pytest.raises(ValueError):
        EntityRef().decode((wire,))


def test_an_entity_ref_carries_none_and_the_whole_id_range() -> None:
    ref = EntityRef()
    assert ref.decode(ref.encode(None)) is None
    assert ref.decode(ref.encode(0)) == 0
    assert ref.decode(ref.encode(65535)) == 65535


# --- Over the network -----------------------------------------------------------


def test_an_event_reaches_the_client_naming_its_own_entity() -> None:
    game = started()
    enemy = game.spawn()
    game.run(30)
    game.send(Hit(enemy.id, 12.5, Kind.ENERGY))
    game.run(30)
    player = game.players[0]
    assert player.heard == [Hit(game.local(player, enemy), 12.5, Kind.ENERGY)]
    assert game.local(player, enemy) != enemy.id


def test_an_event_waits_for_the_delayed_view_to_reach_its_tick() -> None:
    game = started()
    game.spawn()
    game.run(30)
    player = game.players[0]
    tick = game.fixed_tick + 1
    game.send(Restarted())
    held = 0
    for _ in range(120):
        game.frame()
        render = player.replication.render_tick
        assert render is not None
        assert bool(player.heard) == (render >= tick)
        if not player.heard and game.fixed_tick > tick:
            held += 1
    assert player.heard == [Restarted()]
    # It arrived well before it was applied: the view runs about 6 ticks behind.
    assert held >= 5


def test_an_event_is_applied_with_the_snapshot_it_belongs_to() -> None:
    """The hit number appears with the health drop, not a frame before it."""
    game = started()
    enemy = game.spawn(0.0)
    game.run(30)
    player = game.players[0]
    seen: list[float] = []

    def watch(event: object) -> None:
        seen.append(player.replication.render_tick or 0.0)
        player.heard.append(event)

    player.replication._on_event = watch  # noqa: SLF001

    def move_and_hit() -> None:
        enemy.get_component(Transform).position = Vector2(100.0, 0.0)
        game.send(Hit(enemy.id, 1.0))

    hit_tick = game.fixed_tick + 1
    game.frame(move_and_hit)
    game.run(60)
    assert len(seen) == 1
    assert hit_tick <= seen[0] < hit_tick + 1


def test_a_kill_names_the_enemy_even_though_it_is_removed_that_tick() -> None:
    game = started()
    enemy = game.spawn()
    game.run(30)
    player = game.players[0]
    local_id = game.local(player, enemy)

    def kill() -> None:
        game.send(Hit(enemy.id, 99.0, killed=True))
        game.world.remove_entity(enemy.id)

    game.frame(kill)
    game.run(60)
    assert player.heard == [Hit(local_id, 99.0, killed=True)]
    assert player.replication.entities() == {}


def test_an_event_can_name_an_entity_spawned_the_same_tick() -> None:
    game = started()
    game.run(30)
    player = game.players[0]
    spawned: list[Entity] = []

    def spawn_and_announce() -> None:
        spawned.append(game.spawn())
        game.send(SkillUsed(spawned[0].id, "multishot"))

    game.frame(spawn_and_announce)
    game.run(60)
    assert player.heard == [SkillUsed(game.local(player, spawned[0]), "multishot")]


def test_an_entity_that_does_not_replicate_arrives_as_none() -> None:
    game = started()
    loner = game.world.create_entity()
    game.run(30)
    game.send(Hit(loner.id, 3.0))
    game.send(Hit(None, 4.0))
    game.run(60)
    assert game.players[0].heard == [Hit(None, 3.0), Hit(None, 4.0)]


def test_an_event_for_one_slot_reaches_only_that_player() -> None:
    game = started(players=2)
    game.run(30)
    slots = {game.session.slot_of(peer) for peer in game.session.players}
    assert slots == {1, 2}  # The host is slot 0.
    game.send(SkillUsed(None, "shot"), slot=1)
    game.send(Restarted())
    game.run(60)
    by_slot = {}
    for player in game.players:
        # Which slot each client is, from what it heard.
        by_slot[len(player.heard)] = player.heard
    assert by_slot[2] == [SkillUsed(None, "shot"), Restarted()]
    assert by_slot[1] == [Restarted()]


def test_every_event_arrives_once_and_in_order_over_a_bad_network() -> None:
    game = started(conditions=BAD_NETWORK, players=2, seed=7)
    enemies = [game.spawn(float(i)) for i in range(5)]
    game.run(60)
    sent: list[tuple[int, float]] = []
    for i in range(300):
        index = i % len(enemies)

        def hit(index: int = index, amount: float = float(i)) -> None:
            game.send(Hit(enemies[index].id, amount))
            sent.append((index, amount))

        game.frame(hit)
    game.network.conditions = LinkConditions()
    game.run(240)
    for player in game.players:
        local = {game.local(player, e): i for i, e in enumerate(enemies)}
        heard = [(local[e.target], e.amount) for e in player.heard]  # type: ignore[attr-defined]
        assert heard == sent
        assert player.replication.malformed == 0
        assert player.replication.digests_mismatched == 0
        assert player.replication.digests_matched > 0


def test_state_digests_still_match_while_events_flow() -> None:
    game = started()
    game.spawn()
    for _ in range(120):
        game.frame(lambda: game.send(Restarted()))
    game.run(60)
    replication = game.players[0].replication
    assert replication.digests_mismatched == 0
    assert replication.digests_matched > 10


def test_sending_an_unregistered_event_says_so() -> None:
    game = started()
    with pytest.raises(ValueError, match="Unsent isn't registered"):
        game.send(Unsent())


def test_a_client_with_other_events_refuses_rather_than_misreading() -> None:
    other = make_schema(("shot", "caltrops", "multishot"))
    game = Game(client_schema=other)
    game.connect()
    game.run(30)
    game.send(SkillUsed(None, "caltrops"))
    game.run(60)
    player = game.players[0]
    assert player.replication.failed is not None
    assert player.heard == []


def test_an_event_the_client_cannot_build_is_counted_not_raised() -> None:
    game = started()
    game.run(30)
    refused = Picky(8)
    refused.value = 7  # Valid on the host; the client's own check refuses it.
    game.send(refused)
    game.send(Picky(8))
    game.run(60)
    player = game.players[0]
    assert player.heard == [Picky(8)]
    assert player.replication.malformed == 1


def test_a_client_without_a_handler_reads_and_drops_events() -> None:
    world = EntityManager()
    replication = ReplicationClient(world, make_schema(), {})
    message = struct.pack("<BIB", 0xE6, 10, 2)  # Restarted, at tick 10
    assert replication.handle_message(Channel.EVENTS, message)
    replication.update(1.0)
    assert replication.malformed == 0


@pytest.mark.parametrize(
    "message",
    [
        struct.pack("<BIB", 0xE6, 10, 9),  # no such event type
        struct.pack("<BIB", 0xE6, 10, 3),  # Picky, with its value missing
        struct.pack("<BIBH", 0xE6, 10, 2, 0),  # Restarted, with trailing bytes
        struct.pack("<BIBiB", 0xE6, 10, 1, 70000, 0),  # past the network ids
        struct.pack("<BIBiB", 0xE6, 10, 1, -1, 3),  # a skill past the choices
        struct.pack("<BIBiiBB", 0xE6, 10, 0, -1, 5, 2, 0),  # a Kind past its members
        struct.pack("<BIBiiBB", 0xE6, 10, 0, -1, 5, 0, 2),  # a flag that is 2
        struct.pack("<BI", 0xE6, 10),  # cut short
    ],
)
def test_a_hostile_event_is_dropped_and_counted(message: bytes) -> None:
    heard: list[object] = []
    replication = ReplicationClient(
        EntityManager(), make_schema(), {}, on_event=heard.append
    )
    assert replication.handle_message(Channel.EVENTS, message)
    replication.update(10.0)
    assert replication.malformed == 1
    assert heard == []


def test_an_unlisted_choice_is_counted_on_the_host() -> None:
    game = started()
    game.send(SkillUsed(None, "fireball"))
    assert game.replication.saturated() == 1


# --- The relay -----------------------------------------------------------------


def test_the_relay_sends_what_the_host_dispatches() -> None:
    game = started()
    enemy = game.spawn()
    game.run(30)
    relay = EventRelay(game.dispatcher, game.replication, game)
    game.frame(lambda: game.dispatcher.dispatch(Hit(enemy.id, 5.0)))
    game.dispatcher.dispatch(Unsent())  # not registered: stays on the host
    relay.close()
    game.frame(lambda: game.dispatcher.dispatch(Restarted()))
    game.run(60)
    player = game.players[0]
    assert player.heard == [Hit(game.local(player, enemy), 5.0)]


def test_the_relay_stamps_the_tick_after_the_fixed_update() -> None:
    game = started()
    game.run(30)
    sent: list[int] = []
    game.replication.send_event = (  # type: ignore[method-assign]
        lambda event, tick, slot=None: sent.append(tick)
    )
    EventRelay(game.dispatcher, game.replication, game)
    game.dispatcher.dispatch(Restarted())
    assert sent == [game.fixed_tick + 1]


def test_the_relay_can_address_one_player() -> None:
    game = started(players=2)
    game.run(30)
    EventRelay(
        game.dispatcher,
        game.replication,
        game,
        slot_of=lambda event: 2 if isinstance(event, SkillUsed) else None,
    )
    game.frame(lambda: game.dispatcher.dispatch(SkillUsed(None, "shot")))
    game.run(60)
    assert sorted(len(p.heard) for p in game.players) == [0, 1]
