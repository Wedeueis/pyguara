"""Shots over the network: each sent once, flown by every client, ended by the host.

These use the real session and the real Rust core. They check what makes the
arrangement worth having: every client sees every shot exactly once, where the host
fired it; a shot stopped on the host stops on the client at the same place; a bullet
in flight costs no bandwidth; and a player's own shot shows at once without being shown
a second time when the host's copy arrives.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field

import pytest

from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.action_combat import Health, Hurtbox
from pyguara.kits.projectiles import Projectile, ProjectileSystem
from pyguara.kits.projectiles.net import (
    NO_SLOT,
    NetShot,
    ProjectileClient,
    ProjectileEnded,
    ProjectileFired,
    ProjectileHost,
    ProjectileKey,
    register_projectiles,
)
from pyguara.net import (
    ClientDriver,
    ClientSession,
    HostDriver,
    HostSession,
    LinkConditions,
    QuantisedVector,
    Replicated,
    ReplicationClient,
    ReplicationHost,
    ReplicationSchema,
    SimulatedNetwork,
    Versions,
)

DT = 1 / 60
VERSIONS = Versions("test", "test")
BAD_NETWORK = LinkConditions(
    latency=0.05, jitter=0.03, loss=0.2, duplicate=0.02, reorder=0.1
)
KINDS = ("bolt", "pellet")
SPEED = 600.0


def make_schema() -> ReplicationSchema:
    schema = ReplicationSchema()
    schema.register(Transform, position=QuantisedVector(step=0.25))
    register_projectiles(
        schema,
        KINDS,
        position=QuantisedVector(step=0.25, wide=True),
        velocity=QuantisedVector(step=0.25),
    )
    return schema


@dataclass(frozen=True)
class Sighting:
    render: float
    position: Vector2
    shot: NetShot


@dataclass
class Player:
    session: ClientSession
    replication: ReplicationClient
    driver: ClientDriver
    dispatcher: EventDispatcher
    projectiles: ProjectileSystem
    shots: ProjectileClient
    seen: dict[ProjectileKey, list[Sighting]] = field(default_factory=dict)
    ended: list[ProjectileEnded] = field(default_factory=list)

    def shown(self) -> list[Projectile]:
        return self.projectiles.get_active()

    def record(self) -> None:
        render = self.replication.render_tick
        for projectile in self.shown():
            assert isinstance(projectile.payload, NetShot)
            self.seen.setdefault(projectile.payload.key, []).append(
                Sighting(render or 0.0, projectile.position, projectile.payload)
            )


class Game:
    """A host and its players, stepped together with an explicit clock."""

    def __init__(
        self,
        seed: int = 1,
        conditions: LinkConditions | None = None,
        players: int = 1,
    ) -> None:
        self.network = SimulatedNetwork(seed=seed, conditions=conditions)
        self.key = secrets.token_bytes(32)
        transport = self.network.add_host(self.key)
        self.address = self.network.address_of(transport)
        self.session = HostSession(transport, VERSIONS)
        self.world = EntityManager()
        self.dispatcher = EventDispatcher()
        self.index: SpatialHash[str] = SpatialHash(accelerate=False)
        self.fixed_tick = 0
        self.replication = ReplicationHost(self.world, make_schema(), self.session.send)
        self.driver = HostDriver(self, self.session, self.replication)
        self.projectiles = ProjectileSystem(
            self.world, self.dispatcher, self.index, capacity=1024
        )
        self.shots = ProjectileHost(self.projectiles, self.replication, self)
        self.simulate: Callable[[], None] | None = None
        self.players = [self.add_player() for _ in range(players)]

    def add_player(self) -> Player:
        world = EntityManager()
        dispatcher = EventDispatcher()

        def spawn() -> Entity:
            entity = world.create_entity()
            entity.add_component(Transform())
            return entity

        transport = self.network.add_client(self.key, self.address, VERSIONS.encode())
        session = ClientSession(transport)
        replication = ReplicationClient(
            world, make_schema(), {"marker": spawn}, on_event=dispatcher.dispatch
        )
        driver = ClientDriver(session, replication)
        projectiles = ProjectileSystem(
            world, dispatcher, SpatialHash(accelerate=False), capacity=1024
        )
        shots = ProjectileClient(projectiles, dispatcher, replication, DT)
        player = Player(session, replication, driver, dispatcher, projectiles, shots)
        dispatcher.subscribe(ProjectileEnded, player.ended.append)
        return player

    def frame(self) -> None:
        self.network.advance(DT)
        self.driver.before_fixed_updates(DT)
        for player in self.players:
            player.driver.before_fixed_updates(DT)
        if self.simulate is not None:
            self.simulate()
        self.projectiles.update(DT)
        self.fixed_tick += 1
        self.driver.after_fixed_updates(DT)
        for player in self.players:
            player.driver.after_fixed_updates(DT)
            player.shots.update(DT)
            player.record()

    def connect(self) -> None:
        # Something to snapshot, so every client's delayed view starts running.
        marker = self.world.create_entity()
        marker.add_component(Transform())
        marker.add_component(Replicated("marker"))
        for _ in range(240):
            self.frame()
            if (
                all(p.session.joined for p in self.players)
                and len(self.session.players) == len(self.players)
                and all(p.replication.render_tick is not None for p in self.players)
            ):
                return
        raise AssertionError("players did not join")

    def run(self, frames: int) -> None:
        for _ in range(frames):
            self.frame()

    def fire(
        self, kind: str = "bolt", slot: int | None = None, **options: object
    ) -> Projectile:
        options.setdefault("life", 3.0)
        projectile = self.shots.spawn(
            kind, Vector2(0, 0), Vector2(SPEED, 0), slot=slot, **options
        )
        assert projectile is not None
        return projectile

    def target(self, x: float) -> Entity:
        entity = self.world.create_entity()
        entity.add_component(Transform(position=Vector2(x, 0)))
        entity.add_component(Health(current=100.0, max_health=100.0))
        entity.add_component(Hurtbox(team="enemies"))
        self.index.insert(entity.id, Vector2(x, 0))
        return entity


def test_every_client_sees_every_shot_once_where_it_was_fired() -> None:
    game = Game(seed=4, conditions=BAD_NETWORK, players=2)
    game.connect()
    fired: dict[ProjectileKey, str] = {}

    def volley() -> None:
        for n in range(2):
            kind = KINDS[(game.fixed_tick + n) % 2]
            game.fire(kind)
            fired[ProjectileKey(NO_SLOT, game.fixed_tick, n)] = kind

    game.simulate = volley
    game.run(150)
    game.simulate = None
    game.run(120)

    assert len(fired) == 300
    for player in game.players:
        assert set(player.seen) == set(fired)
        for key, sightings in player.seen.items():
            assert sightings[0].shot.kind == fired[key]
            assert not sightings[0].shot.predicted
            # Each sighting is where the host's copy was at the client's view.
            for sighting in sightings:
                expected = SPEED * (sighting.render - key.tick) * DT
                assert sighting.position.y == 0.0
                assert sighting.position.x == pytest.approx(expected, abs=SPEED * DT)


def test_a_hit_on_the_host_stops_the_clients_copy_where_it_landed() -> None:
    game = Game(seed=2)
    game.connect()
    game.target(100.0)
    game.fire(hit_radius=4.0)

    game.run(90)

    (player,) = game.players
    assert not player.shown()
    (ended,) = player.ended
    assert ended.position.x == pytest.approx(100.0, abs=0.25)
    # The copy was never drawn past the target by more than a frame's flight.
    (sightings,) = player.seen.values()
    assert max(s.position.x for s in sightings) <= 100.0 + SPEED * DT


def test_a_shot_that_expires_ends_on_its_own_on_both_sides() -> None:
    game = Game(seed=3)
    game.connect()
    game.fire(life=0.5)

    game.run(30)
    (player,) = game.players
    assert len(player.shown()) == 1
    game.run(60)

    assert not game.projectiles.get_active()
    assert not player.shown()
    assert player.ended == []


def test_clearing_the_host_clears_every_client() -> None:
    game = Game(seed=5, players=2)
    game.connect()
    for _ in range(5):
        game.fire(life=10.0)
    game.run(30)
    assert all(len(p.shown()) == 5 for p in game.players)

    game.projectiles.clear()
    game.run(30)

    assert all(p.shown() == [] for p in game.players)


def test_bullets_in_flight_cost_no_bandwidth() -> None:
    def traffic(bullets: int) -> tuple[int, int]:
        game = Game(seed=6)
        game.connect()
        sent: list[int] = []
        game.network.tap = lambda source, destination, data: sent.append(len(data))
        for _ in range(bullets):
            game.fire(life=8.0)
        game.run(60)
        burst = sum(sent)
        sent.clear()
        game.run(240)
        assert len(game.players[0].shown()) == bullets
        return burst, sum(sent)

    quiet_burst, quiet = traffic(0)
    busy_burst, busy = traffic(200)

    # Each shot is sent once, and is small...
    assert busy_burst - quiet_burst < 200 * 40
    # ...and the same game with 200 bullets flying sends what it does with none.
    assert abs(busy - quiet) <= quiet * 0.01


def test_an_own_shot_shows_at_once_and_once() -> None:
    game = Game(seed=7, conditions=BAD_NETWORK)
    game.connect()
    (player,) = game.players
    (peer,) = game.session.players
    slot = game.session.slot_of(peer)
    assert slot == 1

    def fire_both() -> None:
        tick = game.fixed_tick
        shown = player.shots.fire(slot, tick, "bolt", Vector2(0, 0), Vector2(SPEED, 0))
        assert shown is not None
        game.fire(slot=slot)

    game.simulate = fire_both
    game.run(1)
    game.simulate = None
    assert len(player.shown()) == 1
    assert player.shown()[0].payload.predicted
    game.run(150)

    (key,) = player.seen
    assert key == ProjectileKey(slot, key.tick, 0)
    assert all(s.shot.predicted for s in player.seen[key])
    assert player.shots.mispredicted == 0
    assert player.shots.unpredicted == 0


def test_a_replayed_tick_does_not_show_its_shot_again() -> None:
    game = Game(seed=8)
    game.connect()
    (player,) = game.players
    tick = game.fixed_tick + 5
    for replayed in (tick, tick + 1, tick, tick + 1):
        player.shots.fire(1, replayed, "bolt", Vector2(0, 0), Vector2(SPEED, 0))

    assert len(player.shown()) == 2


def test_an_own_shot_the_host_never_fired_is_taken_away() -> None:
    game = Game(seed=9)
    game.connect()
    (player,) = game.players
    player.shots.fire(
        1, game.fixed_tick, "bolt", Vector2(0, 0), Vector2(SPEED, 0), life=30.0
    )

    game.run(120)

    assert player.shown() == []
    assert player.shots.mispredicted == 1


def test_an_own_shot_the_client_did_not_predict_still_appears() -> None:
    game = Game(seed=10)
    game.connect()
    (player,) = game.players
    # Predicted for a later tick than the host fires on, so the two never match.
    player.shots.fire(1, game.fixed_tick + 50, "bolt", Vector2(0, 0), Vector2(SPEED, 0))

    def host_only() -> None:
        game.fire(slot=1)

    game.simulate = host_only
    game.run(1)
    game.simulate = None
    game.run(60)

    unpredicted = [k for k, seen in player.seen.items() if not seen[0].shot.predicted]
    assert len(unpredicted) == 1
    assert player.shots.unpredicted == 1


def test_an_own_shot_stops_at_a_target_the_client_sees() -> None:
    game = Game(seed=11)
    game.connect()
    (player,) = game.players
    world = EntityManager()
    index: SpatialHash[str] = SpatialHash(accelerate=False)
    target = world.create_entity()
    target.add_component(Transform(position=Vector2(60, 0)))
    target.add_component(Health(current=100.0, max_health=100.0))
    target.add_component(Hurtbox(team="enemies"))
    index.insert(target.id, Vector2(60, 0))
    projectiles = ProjectileSystem(world, EventDispatcher(), index)
    shots = ProjectileClient(projectiles, EventDispatcher(), player.replication, DT)

    shots.fire(
        1, 0, "bolt", Vector2(0, 0), Vector2(SPEED, 0), hit_radius=4.0, team="shells"
    )
    shots.update(0.2)

    assert projectiles.get_active() == []
    assert target.get_component(Health).current == 100.0


def test_another_players_shot_passes_what_it_meets_until_the_host_says() -> None:
    world = EntityManager()
    index: SpatialHash[str] = SpatialHash(accelerate=False)
    target = world.create_entity()
    target.add_component(Transform(position=Vector2(60, 0)))
    target.add_component(Health(current=100.0, max_health=100.0))
    target.add_component(Hurtbox(team="enemies"))
    index.insert(target.id, Vector2(60, 0))
    projectiles = ProjectileSystem(world, EventDispatcher(), index)
    dispatcher = EventDispatcher()
    game = Game(seed=12)
    shots = ProjectileClient(projectiles, dispatcher, game.players[0].replication, DT)

    dispatcher.dispatch(
        ProjectileFired(2, 0, 0, "bolt", Vector2(0, 0), Vector2(SPEED, 0), 2.0)
    )
    shots.update(DT)
    shots.update(0.2)
    assert len(projectiles.get_active()) == 1

    dispatcher.dispatch(ProjectileEnded(2, 0, 0, Vector2(60, 0)))
    assert projectiles.get_active() == []


def test_an_end_naming_no_shot_is_ignored() -> None:
    dispatcher = EventDispatcher()
    game = Game(seed=13)
    projectiles = ProjectileSystem(
        EntityManager(), EventDispatcher(), SpatialHash(accelerate=False)
    )
    shots = ProjectileClient(projectiles, dispatcher, game.players[0].replication, DT)

    dispatcher.dispatch(ProjectileEnded(3, 99, 7, Vector2(1, 1)))
    shots.update(DT)

    assert projectiles.get_active() == []


def test_the_host_refuses_a_system_already_told_about_ends() -> None:
    game = Game(seed=14, players=0)

    with pytest.raises(ValueError, match="on_end"):
        ProjectileHost(game.projectiles, game.replication, game)


def test_the_host_refuses_a_schema_without_shots() -> None:
    world = EntityManager()
    projectiles = ProjectileSystem(world, EventDispatcher(), SpatialHash())
    replication = ReplicationHost(world, ReplicationSchema(), lambda *a: True)

    with pytest.raises(ValueError, match="register_projectiles"):
        ProjectileHost(projectiles, replication, Game(seed=15, players=0))


def test_an_out_of_range_slot_is_refused() -> None:
    game = Game(seed=16, players=0)

    with pytest.raises(ValueError, match="slot"):
        game.fire(slot=NO_SLOT)
