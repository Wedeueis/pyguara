"""Your own character responding at once, with the host still in charge.

These use the real session, the real Rust core, a real physics world for the walls and the
real movement step. What matters most: after any amount of bad network, host and client hold
exactly the same state, and nothing a client sends can move it faster than one command a tick.
"""

from __future__ import annotations

import math
import random
import secrets
import struct
from dataclasses import dataclass
from typing import Any

import pytest

from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.component import StrictComponent
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.topdown_movement import TopDownBody, TopDownPrediction, TopDownSystem
from pyguara.net import (
    Channel,
    ClientDriver,
    ClientSession,
    CommandSchema,
    Flag,
    HostDriver,
    HostSession,
    LinkConditions,
    MessageReceived,
    PredictionClient,
    PredictionHost,
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
from pyguara.physics.backends.pymunk_impl import PymunkEngine
from pyguara.physics.character_mover import CharacterMover
from pyguara.physics.components import Collider, RigidBody
from pyguara.physics.physics_system import PhysicsSystem
from pyguara.physics.types import BodyType, ShapeType

DT = 1 / 60
SPEED = 180.0
VERSIONS = Versions("test", "test")
# Round trip of 100 ms and 2% loss: the plan's bar for phase 3.
PLAN_NETWORK = LinkConditions(latency=0.05, jitter=0.01, loss=0.02)
BAD_NETWORK = LinkConditions(
    latency=0.08, jitter=0.03, loss=0.2, duplicate=0.02, reorder=0.1
)
WALLS = (
    (200, -10, 460, 20),
    (200, 310, 460, 20),
    (-10, 150, 20, 340),
    (410, 150, 20, 340),
    (200, 150, 40, 40),
)


@dataclass(frozen=True, slots=True)
class Move:
    x: float = 0.0
    y: float = 0.0


NEUTRAL = Move()


@dataclass(slots=True)
class Vitals(StrictComponent):
    current: int = 100

    def __post_init__(self) -> None:
        StrictComponent.__init__(self)


def velocity_of(command: Move) -> Vector2:
    """Limited, since on the host a command is untrusted."""
    direction = Vector2(command.x, command.y)
    if direction.magnitude > 1.0:
        direction = direction.normalize()
    return direction * SPEED


def command_schema() -> CommandSchema[Move]:
    return CommandSchema(Move, x=Quantised(step=1 / 64), y=Quantised(step=1 / 64))


def state_schema() -> ReplicationSchema:
    schema = ReplicationSchema()
    schema.register(Transform, position=QuantisedVector(step=0.25))
    schema.register(Vitals, current=UInt16())
    return schema


def build_world() -> tuple[EntityManager, PymunkEngine]:
    world = EntityManager()
    engine = PymunkEngine()
    engine.initialize(Vector2(0, 0))
    physics = PhysicsSystem(engine, world, EventDispatcher())
    for x, y, w, h in WALLS:
        wall = world.create_entity()
        wall.add_component(Transform(position=Vector2(x, y)))
        wall.add_component(RigidBody(body_type=BodyType.STATIC))
        wall.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[w, h]))
    physics.update(DT)
    return world, engine


def add_character(world: EntityManager) -> Entity:
    entity = world.create_entity()
    entity.add_component(Transform())
    entity.add_component(TopDownBody())
    entity.add_component(Vitals())
    entity.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[20, 20]))
    return entity


class Player:
    def __init__(self, game: Game) -> None:
        self.world, self.engine = build_world()
        self.mover = CharacterMover(self.engine)
        transport = game.network.add_client(game.key, game.address, VERSIONS.encode())
        self.session = ClientSession(transport)
        self.prediction = PredictionClient(
            command_schema(), NEUTRAL, self.session.send, DT
        )
        self.own: Entity | None = None
        self.others = 0
        self.replication = ReplicationClient(
            self.world,
            state_schema(),
            {"player": lambda: add_character(self.world)},
            predicted_components=(Transform,),
            on_controlled=self.on_controlled,
        )
        self.driver = ClientDriver(
            self.session, self.replication, prediction=self.prediction
        )

    def on_controlled(self, entity: Entity | None) -> None:
        self.own = entity
        self.prediction.bind(
            None
            if entity is None
            else TopDownPrediction(entity, self.mover, velocity_of)
        )

    def state(self) -> tuple[float, ...]:
        """The simulated state, without any correction still fading on screen."""
        assert self.prediction._sim is not None
        return self.prediction._sim

    def body(self) -> TopDownPrediction:
        assert self.own is not None
        return TopDownPrediction(self.own, self.mover, velocity_of)


class Game:
    """A host and its players, stepped together with an explicit clock."""

    def __init__(
        self,
        players: int = 1,
        conditions: LinkConditions | None = None,
        seed: int = 1,
    ) -> None:
        self.network = SimulatedNetwork(seed=seed, conditions=conditions)
        self.key = secrets.token_bytes(32)
        transport = self.network.add_host(self.key)
        self.address = self.network.address_of(transport)
        self.session = HostSession(transport, VERSIONS)
        self.world, self.engine = build_world()
        self.mover = CharacterMover(self.engine)
        self.topdown = TopDownSystem(self.world, self.engine, SpatialHash(cell_size=48))
        self.fixed_tick = 0
        self.replication = ReplicationHost(
            self.world, state_schema(), self.session.send, digest_every=4
        )
        self.host_prediction = PredictionHost(
            command_schema(), NEUTRAL, self.session.send
        )
        self.characters: dict[int, Entity] = {}
        self.driver = HostDriver(
            self,
            self.session,
            self.replication,
            on_event=self.on_host_event,
            prediction=self.host_prediction,
        )
        self.players = [Player(self) for _ in range(players)]
        self.max_step = 0.0
        # Each character's state as each tick began, before its command.
        self.history: dict[int, dict[int, tuple[float, ...]]] = {}

    def on_host_event(self, event: object) -> None:
        slot = getattr(event, "slot", None)
        if slot is None or type(event).__name__ != "PlayerJoined":
            return
        entity = add_character(self.world)
        entity.get_component(Transform).position = Vector2(60, 150)
        entity.add_component(Replicated("player", controller=slot))
        self.characters[slot] = entity
        self.host_prediction.bind(
            slot, TopDownPrediction(entity, self.mover, velocity_of)
        )

    def frame(self, commands: Any = None, ticks: int = 1) -> None:
        """One frame: `commands(player)` says what a player wants on each tick."""
        self.network.advance(DT * ticks)
        self.driver.before_fixed_updates(DT * ticks)
        for player in self.players:
            player.driver.before_fixed_updates(DT * ticks)
        for _ in range(ticks):
            for slot, entity in self.characters.items():
                self.history.setdefault(slot, {})[self.fixed_tick] = self.host_state(
                    slot
                )
                command = self.host_prediction.take(slot, self.fixed_tick)
                entity.get_component(TopDownBody).velocity = velocity_of(command)
            self.topdown.update(DT)
            self.fixed_tick += 1
            for player in self.players:
                wanted = NEUTRAL if commands is None else commands(player)
                player.prediction.step(wanted)
        self.driver.after_fixed_updates(DT * ticks)
        for player in self.players:
            player.driver.after_fixed_updates(DT * ticks)

    def run(self, seconds: float, commands: Any = None) -> None:
        for _ in range(round(seconds / DT)):
            self.frame(commands)

    def join(self, seconds: float = 15.0) -> None:
        for _ in range(round(seconds / DT)):
            self.frame()
            if all(p.prediction.tick is not None for p in self.players):
                return
        raise AssertionError("players never started predicting")

    def character(self, slot: int = 1) -> Entity:
        return self.characters[slot]

    def host_state(self, slot: int = 1) -> tuple[float, ...]:
        return TopDownPrediction(
            self.character(slot), self.mover, velocity_of
        ).capture()

    def settle(self, seconds: float = 3.0) -> None:
        self.network.conditions = LinkConditions()
        self.run(seconds)


def wander(seed: int = 7) -> Any:
    """Changes direction every so often, and runs into walls."""
    rng = random.Random(seed)
    current = {"move": Move(1.0, 0.0), "left": 0}

    def commands(player: Player) -> Move:
        if current["left"] <= 0:
            angle = rng.uniform(0, math.tau)
            current["move"] = Move(math.cos(angle), math.sin(angle))
            current["left"] = rng.randint(10, 70)
        current["left"] -= 1
        return current["move"]

    return commands


def test_the_character_moves_on_the_same_tick_as_the_input() -> None:
    game = Game(conditions=PLAN_NETWORK)
    game.join()
    game.run(1.0)
    player = game.players[0]
    player.prediction.begin_frame()
    before = player.body().capture()
    player.prediction.step(Move(1.0, 0.0))
    after = player.body().capture()
    # Nothing has been sent, so this can only have come from local prediction.
    assert after[0] + after[2] == pytest.approx(
        before[0] + before[2] + SPEED * DT, abs=1e-9
    )


@pytest.mark.parametrize("conditions", [PLAN_NETWORK, BAD_NETWORK], ids=["plan", "bad"])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_host_and_client_end_in_exactly_the_same_state(
    conditions: LinkConditions, seed: int
) -> None:
    game = Game(conditions=conditions, seed=seed)
    game.join()
    game.run(8.0, wander(seed))
    game.settle()
    assert game.players[0].state() == game.host_state()
    assert game.players[0].prediction.malformed == 0
    assert game.host_prediction.malformed == 0


def test_without_loss_nothing_ever_needs_correcting() -> None:
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    corrections = player.prediction.corrections
    replayed = player.prediction.replayed_ticks
    late = game.host_prediction.late_commands
    game.run(10.0, wander())
    assert player.prediction.corrections == corrections
    assert player.prediction.replayed_ticks == replayed
    assert game.host_prediction.late_commands == late


@pytest.mark.parametrize("round_trip", [0.2, 0.4, 0.8])
def test_a_slow_link_finds_enough_lead_on_its_own(round_trip: float) -> None:
    """Every command starting out too late must not leave the client stuck behind."""
    game = Game(conditions=LinkConditions(latency=round_trip / 2))
    game.join()
    game.run(3.0)
    player = game.players[0]
    corrections = player.prediction.corrections
    late = game.host_prediction.late_commands
    game.run(5.0, wander())
    # Commands only cross one way, so that's the lead they need.
    assert player.prediction.tick - game.fixed_tick >= round_trip / 2 * 60
    assert player.prediction.corrections == corrections
    assert game.host_prediction.late_commands == late


def test_the_lead_holds_steady_on_the_plans_network() -> None:
    game = Game(conditions=PLAN_NETWORK)
    game.join()
    game.run(3.0)
    player = game.players[0]
    adjustments = player.prediction.tick_adjustments
    game.run(30.0, wander())
    assert player.prediction.tick_adjustments - adjustments <= 5
    assert player.prediction.tick - game.fixed_tick <= 14


def test_the_client_simulates_what_the_host_decodes_not_what_it_asked_for() -> None:
    """A third isn't a multiple of the step, so the two differ unless this is handled."""
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    corrections = player.prediction.corrections
    game.run(1.0, lambda _: Move(1 / 3, 1 / 7))
    game.run(1.0)
    assert player.prediction.corrections == corrections
    assert player.state() == game.host_state()


def test_a_push_from_the_host_is_corrected_and_glides() -> None:
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    transform = game.character().get_component(Transform)
    transform.position = transform.position + Vector2(10, 0)
    assert player.own is not None
    shown = player.own.get_component(Transform)
    start = shown.position.x
    seen = []
    for _ in range(40):
        game.frame()
        seen.append(shown.position.x)
    assert player.prediction.corrections >= 1
    assert player.prediction.largest_correction == pytest.approx(10)
    jumps = [abs(b - a) for a, b in zip([start, *seen], seen, strict=False)]
    assert max(jumps) < 5, "the correction should be spread over frames"
    assert seen[-1] == pytest.approx(start + 10, abs=0.1)
    game.run(1.0)
    assert player.state() == game.host_state()


def test_a_large_correction_is_shown_at_once() -> None:
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    game.character().get_component(Transform).position = Vector2(350, 60)
    game.run(0.5)
    assert player.own is not None
    assert player.own.get_component(Transform).position == Vector2(350, 60)


def test_what_is_only_for_display_never_reaches_the_simulation() -> None:
    """If the fading offset leaked into the state, every replay would be off by it."""
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    transform = game.character().get_component(Transform)
    transform.position = transform.position + Vector2(20, 0)
    while player.prediction.corrections == 0 or player.state() == game.host_state():
        game.frame()
        if player.prediction.corrections:
            break
    assert player.own is not None
    shown = player.own.get_component(Transform).position.x
    player.prediction.begin_frame()
    simulated = player.own.get_component(Transform).position.x
    assert simulated != shown
    assert simulated == pytest.approx(transform.position.x)
    player.prediction.end_frame(DT)


def test_snapshots_leave_the_own_position_alone_but_not_the_rest() -> None:
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    assert player.own is not None
    game.character().get_component(Vitals).current = 42
    game.run(0.3, lambda _: Move(0.0, 1.0))
    assert player.own.get_component(Vitals).current == 42
    assert player.prediction.tick > game.fixed_tick
    # Running ahead, so its position must lead the host's, not trail 100 ms behind it.
    assert (
        player.own.get_component(Transform).position.y
        > game.character().get_component(Transform).position.y
    )


def test_players_predict_themselves_and_interpolate_each_other() -> None:
    game = Game(players=4, conditions=PLAN_NETWORK)
    game.join()
    game.run(5.0, wander())
    game.settle()
    host_states = {game.host_state(slot) for slot in game.characters}
    assert len(game.characters) == 4
    for player in game.players:
        assert player.own is not None
        assert player.state() in host_states
        assert player.replication.digests_mismatched == 0
        assert player.replication.digests_matched > 0
    positions = {
        round(game.character(slot).get_component(Transform).position.x * 4)
        for slot in game.characters
    }
    for player in game.players:
        seen = {
            round(entity.get_component(Transform).position.x * 4)
            for entity in player.replication.entities().values()
        }
        assert seen == positions


@pytest.mark.parametrize("ticks", [2, 3])
def test_a_slow_frame_rate_still_needs_no_corrections(ticks: int) -> None:
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    for _ in range(60):
        game.frame(ticks=ticks)
    player = game.players[0]
    corrections = player.prediction.corrections
    motion = wander()
    for _ in range(300):
        game.frame(motion, ticks=ticks)
    assert player.prediction.corrections == corrections


def test_frames_with_no_fixed_update_change_nothing() -> None:
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    before = player.state()
    for _ in range(10):
        player.prediction.begin_frame()
        player.prediction.end_frame(DT / 4)
    assert player.state() == before


def test_a_character_going_and_coming_back_rebinds() -> None:
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    game.host_prediction.bind(1, None)
    old = game.characters.pop(1)
    game.world.remove_entity(old.id)
    game.run(1.0)
    assert player.own is None
    assert player.prediction.tick is None
    player.prediction.step(Move(1.0, 0.0))  # Nothing to move, and must not raise.

    entity = add_character(game.world)
    entity.get_component(Transform).position = Vector2(300, 60)
    entity.add_component(Replicated("player", controller=1))
    game.characters[1] = entity
    game.host_prediction.bind(1, TopDownPrediction(entity, game.mover, velocity_of))
    game.run(2.0, lambda _: Move(0.0, 1.0))
    game.run(1.0)
    assert player.own is not None
    assert player.state() == game.host_state()


def test_a_player_cut_off_stops_on_the_host_and_recovers() -> None:
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    game.character().get_component(Transform).position = Vector2(60, 60)
    game.run(0.5)
    game.run(0.3, lambda _: Move(1.0, 0.0))
    game.network.conditions = LinkConditions(latency=0.05, loss=1.0)
    game.run(0.5, lambda _: Move(1.0, 0.0))
    transform = game.character().get_component(Transform)
    stopped_at = transform.position
    game.run(1.0, lambda _: Move(1.0, 0.0))
    assert transform.position == stopped_at, "a silent player must not keep running"

    game.network.conditions = LinkConditions(latency=0.05)
    game.run(2.0, lambda _: Move(0.0, 1.0))
    game.run(2.0)
    assert game.players[0].state() == game.host_state()


def test_a_client_that_stalls_catches_back_up() -> None:
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    original = player.driver
    # The host carries on for two seconds while this client does nothing at all.
    game.players = []
    game.run(2.0)
    game.players = [player]
    assert original is player.driver
    game.run(3.0, wander())
    game.run(1.0)
    assert player.state() == game.host_state()
    assert player.prediction.tick > game.fixed_tick


def test_top_down_prediction_steps_exactly_as_the_system_does() -> None:
    """Including a collider that doesn't sit on the entity's origin."""
    world, engine = build_world()
    system = TopDownSystem(world, engine, SpatialHash(cell_size=48))
    mover = CharacterMover(engine)
    first = add_character(world)
    second = add_character(world)
    for entity in (first, second):
        entity.get_component(Transform).position = Vector2(60, 150)
        entity.get_component(Collider).offset = Vector2(3, 5)
    predicted = TopDownPrediction(second, mover, velocity_of)
    rng = random.Random(3)
    # Far enough, and in enough directions, to keep hitting walls.
    for _ in range(1500):
        command = Move(rng.uniform(-1, 1), rng.uniform(-1, 1))
        second_transform = second.get_component(Transform)
        kept = second_transform.position
        second_body = second.get_component(TopDownBody)
        kept_velocity = second_body.velocity
        kept_remainder = second_body._remainder
        first.get_component(TopDownBody).velocity = velocity_of(command)
        second_body.velocity = Vector2(0, 0)
        system.update(DT)
        second_transform.position = kept
        second_body.velocity = kept_velocity
        second_body._remainder = kept_remainder
        predicted.advance(command, DT)
        assert second_transform.position == first.get_component(Transform).position
        assert second_body._remainder == first.get_component(TopDownBody)._remainder


def test_a_correction_while_moving_replays_the_newer_commands() -> None:
    """Without the replay, or with the wrong commands, the next state would disagree too."""
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    transform = game.character().get_component(Transform)
    transform.position = Vector2(60, 60)
    game.run(1.0)
    assert player.state()[:2] == (60, 60)
    # Alternating, so a replay using anything but the real commands lands elsewhere.
    game.run(0.3, lambda _: Move(1.0, 0.0))
    transform.position = transform.position + Vector2(5, 0)
    corrections = player.prediction.corrections
    replayed = player.prediction.replayed_ticks
    game.run(0.5, lambda _: Move(0.0, 1.0))
    assert player.prediction.corrections == corrections + 1
    assert player.prediction.replayed_ticks > replayed


class Recording(TopDownPrediction):
    """Notes the tick prediction says each advance is, and the state it starts from."""

    def __init__(self, player: Player) -> None:
        assert player.own is not None
        super().__init__(player.own, player.mover, velocity_of)
        self.prediction = player.prediction
        self.advances: list[tuple[int, tuple[float, ...]]] = []

    def advance(self, command: Any, dt: float) -> None:
        tick = self.prediction.advancing
        assert tick is not None
        self.advances.append((tick, self.capture()))
        super().advance(command, dt)


def record(player: Player) -> Recording:
    body = Recording(player)
    # Swapped in place, so nothing about the prediction under way is reset.
    player.prediction._body = body
    return body


def test_each_advance_names_the_host_tick_it_simulates_while_catching_up() -> None:
    """Catching up makes one step advance several ticks, which `tick` can't name."""
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    body = record(player)
    replayed = player.prediction.replayed_ticks
    # What a report of commands arriving late sets. Set directly, since late commands
    # also bring corrections, and this is about the steps alone.
    player.prediction._catch_up = 5
    game.frame(wander())
    assert len(body.advances) == 6
    assert [tick for tick, _ in body.advances] == list(
        range(body.advances[0][0], body.advances[0][0] + 6)
    )
    game.run(1.0, wander())

    assert player.prediction.replayed_ticks == replayed
    host = game.history[1]
    checked = [(tick, state) for tick, state in body.advances if tick in host]
    assert len(checked) > 50
    assert all(state == host[tick] for tick, state in checked)


def test_each_replayed_advance_names_the_host_tick_it_simulates() -> None:
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    transform = game.character().get_component(Transform)
    game.run(0.3, lambda _: Move(1.0, 0.0))
    transform.position = transform.position + Vector2(5, 0)
    body = record(player)
    corrections = player.prediction.corrections
    replayed = player.prediction.replayed_ticks
    while player.prediction.corrections == corrections:
        # Only the frame the correction lands in is kept: before it, the client
        # rightly predicted ticks the push then changed.
        body.advances.clear()
        game.frame(lambda _: Move(0.0, 1.0))
    replays = player.prediction.replayed_ticks - replayed
    assert replays > 0
    game.run(0.5, lambda _: Move(0.0, 1.0))

    host = game.history[1]
    checked = [(tick, state) for tick, state in body.advances if tick in host]
    assert len(checked) > replays
    assert all(state == host[tick] for tick, state in checked)


def test_nothing_is_advancing_between_steps() -> None:
    game = Game()
    game.join()
    game.run(0.5, wander())
    assert game.players[0].prediction.advancing is None


def test_after_a_stall_the_lead_goes_straight_to_where_it_should_be() -> None:
    """Acting on measurements from before the correction reached the host overshoots."""
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    settled = player.prediction.tick - game.fixed_tick
    game.players = []
    game.run(2.0)
    game.players = [player]
    worst = 0
    for _ in range(180):
        game.frame()
        worst = max(worst, player.prediction.tick - game.fixed_tick)
    assert worst <= settled + 2
    assert player.prediction.tick - game.fixed_tick == pytest.approx(settled, abs=2)


@pytest.mark.parametrize("extra", [6, 100], ids=["small", "large"])
def test_a_client_too_far_ahead_comes_back(extra: int) -> None:
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    player = game.players[0]
    settled = player.prediction.tick - game.fixed_tick
    player.prediction._tick += extra
    adjustments = player.prediction.tick_adjustments
    motion = wander()
    # Measurements from before the change mustn't send it swinging the other way.
    for _ in range(240):
        game.frame(motion)
        assert player.prediction.tick - game.fixed_tick >= 0
    assert player.prediction.tick_adjustments - adjustments <= extra
    game.run(1.0)
    assert player.prediction.tick - game.fixed_tick == pytest.approx(settled, abs=2)
    assert player.state() == game.host_state()


def test_a_message_from_before_the_clients_last_change_is_ignored() -> None:
    host = FakeHost()
    schema = command_schema()

    def message(newest: int, epoch: int, command: Move) -> bytes:
        return struct.pack("<BIBB", 0xE6, newest, epoch, 1) + schema.encode(command)

    new = Move(1.0, 0.0)
    old = Move(0.0, 1.0)
    host.prediction.handle_message(77, Channel.COMMANDS, message(5, 3, new))
    host.prediction.handle_message(77, Channel.COMMANDS, message(6, 2, old))
    assert host.prediction.take(1, 5) == new
    assert 6 not in host.prediction._players[1].commands


def test_a_rewind_forgets_what_was_sent_for_later_ticks() -> None:
    host = FakeHost()
    schema = command_schema()

    def message(newest: int, epoch: int, command: Move) -> bytes:
        return struct.pack("<BIBB", 0xE6, newest, epoch, 1) + schema.encode(command)

    before = Move(1.0, 0.0)
    host.prediction.handle_message(77, Channel.COMMANDS, message(50, 0, before))
    host.prediction.handle_message(77, Channel.COMMANDS, message(10, 1, Move()))
    assert 50 not in host.prediction._players[1].commands
    assert host.prediction._players[1].newest == 10


def test_epochs_keep_working_past_their_wrap() -> None:
    host = FakeHost()
    schema = command_schema()
    command = Move(1.0, 0.0)
    for tick, epoch in enumerate([254, 255, 0, 1]):
        message = struct.pack("<BIBB", 0xE6, tick, epoch, 1) + schema.encode(command)
        host.prediction.handle_message(77, Channel.COMMANDS, message)
    assert host.prediction._players[1].epoch == 1
    assert host.prediction.take(1, 3) == command


def test_feedback_about_a_previous_character_doesnt_steer_the_next() -> None:
    player, _ = started_client()
    prediction = player.prediction
    body = player.body()
    old_epoch = prediction._epoch
    adjustments = prediction.tick_adjustments
    prediction.bind(body)
    tick = prediction._last_state_tick + 1
    state = struct.pack("<4d", *body.capture())
    for offset in range(2):
        message = struct.pack("<BIBbB", 0xE7, tick + offset, old_epoch, -5, 4) + state
        prediction.handle_message(Channel.SNAPSHOT, message)
    assert prediction.tick_adjustments == adjustments


def test_a_taken_command_is_not_kept() -> None:
    host = FakeHost()
    host.prediction.handle_message(
        77, Channel.COMMANDS, host.commands(0, Move(1.0, 0.0))
    )
    host.prediction.take(1, 0)
    assert host.prediction._players[1].commands == {}


def test_a_state_arriving_before_the_character_is_used_when_it_appears() -> None:
    player, _ = started_client()
    prediction = player.prediction
    body = player.body()
    prediction.bind(None)
    last = prediction._last_state_tick
    prediction.handle_message(
        Channel.SNAPSHOT, owner_state(last + 1, 77.0, 88.0, 0.0, 0.0)
    )
    prediction.bind(body)
    assert prediction.tick is not None
    assert body.capture()[:2] == (77.0, 88.0)


def test_the_own_character_starts_where_the_spawn_said() -> None:
    game = Game(conditions=LinkConditions())
    player = game.players[0]
    seen: list[Vector2] = []
    original = player.on_controlled

    def spy(entity: Entity | None) -> None:
        if entity is not None:
            seen.append(entity.get_component(Transform).position)
        original(entity)

    player.replication._on_controlled = spy
    game.join()
    assert seen == [Vector2(60, 150)]


def test_a_collider_off_the_origin_doesnt_shift_the_character() -> None:
    world, engine = build_world()
    entity = add_character(world)
    entity.get_component(Transform).position = Vector2(60, 150)
    entity.get_component(Collider).offset = Vector2(3, 5)
    body = TopDownPrediction(entity, CharacterMover(engine), velocity_of)
    body.advance(Move(1 / 3, 0.0), DT)
    body.advance(Move(1 / 3, 0.0), DT)
    assert entity.get_component(Transform).position == Vector2(62, 150)


# Everything below is hostile input.


class FakeHost:
    def __init__(self) -> None:
        self.sent: list[tuple[int, int, bytes]] = []
        self.prediction = PredictionHost(
            command_schema(), NEUTRAL, self.send, max_repeat_ticks=3
        )
        self.prediction.add_peer(77, 1)

    def send(self, peer: int, channel: Channel, data: bytes) -> bool:
        self.sent.append((peer, int(channel), data))
        return True

    def commands(self, newest: int, *moves: Move) -> bytes:
        schema = command_schema()
        return struct.pack("<BIBB", 0xE6, newest, 0, len(moves)) + b"".join(
            schema.encode(move) for move in moves
        )


def test_the_host_repeats_a_late_command_briefly_then_stands_still() -> None:
    host = FakeHost()
    command = Move(1.0, 0.0)
    assert host.prediction.handle_message(
        77, Channel.COMMANDS, host.commands(0, command)
    )
    taken = [host.prediction.take(1, tick) for tick in range(6)]
    assert taken == [command, command, command, command, NEUTRAL, NEUTRAL]
    assert host.prediction.late_commands == 5


def test_one_command_per_tick_however_many_are_sent() -> None:
    """Flooding commands must not move a character any faster."""
    game = Game(conditions=LinkConditions(latency=0.05))
    game.join()
    game.run(2.0)
    entity = game.character()
    transform = entity.get_component(Transform)
    transform.position = Vector2(60, 60)
    game.run(0.5)
    start = transform.position.x
    peer = next(iter(game.session.players))
    hostile = FakeHost()
    fastest = Move(500.0, 0.0)
    ticks = 60
    for _ in range(ticks):
        for _ in range(5):
            game.host_prediction.handle_message(
                peer,
                Channel.COMMANDS,
                hostile.commands(game.fixed_tick + 10, *[fastest] * 32),
            )
        game.frame()
    assert transform.position.x - start <= SPEED * DT * ticks + 1


@pytest.mark.parametrize(
    "tick",
    [0xFFFFFFFF, 1_000_000],
    ids=["largest", "far"],
)
def test_commands_far_in_the_future_are_not_kept(tick: int) -> None:
    host = FakeHost()
    message = host.commands(tick, *[Move(1.0, 0.0)] * 32)
    assert host.prediction.handle_message(77, Channel.COMMANDS, message)
    assert host.prediction.out_of_window == 32
    assert host.prediction.take(1, 0) == NEUTRAL
    # It must not pollute the slack it reports either, or the client would be told to
    # slow down because of a value it invented.
    host.prediction.step(1)
    assert host.prediction.late_commands == 0


def test_what_a_host_holds_for_a_player_is_bounded() -> None:
    host = FakeHost()
    for tick in range(0, 5000, 32):
        host.prediction.step(tick)
        host.prediction.handle_message(
            77, Channel.COMMANDS, host.commands(tick + 100, *[Move()] * 32)
        )
    player = host.prediction._players[1]
    assert len(player.commands) <= 122 + 32


def test_a_peer_with_no_slot_is_not_heard_and_cannot_speak_for_another() -> None:
    host = FakeHost()
    assert host.prediction.handle_message(
        999, Channel.COMMANDS, host.commands(0, Move(1.0, 0.0))
    )
    assert host.prediction.take(1, 0) == NEUTRAL
    assert host.prediction.take(5, 0) == NEUTRAL


@pytest.mark.parametrize(
    "message",
    [
        struct.pack("<BIBB", 0xE6, 0, 0, 0),
        struct.pack("<BIBB", 0xE6, 0, 0, 1),
        struct.pack("<BIBB", 0xE6, 0, 0, 255) + bytes(4 * 255),
        struct.pack("<BIBB", 0xE6, 0, 0, 33) + bytes(4 * 33),
        struct.pack("<BIBB", 0xE6, 0, 0, 2) + bytes(4 * 2 + 1),
        b"\xe6",
        b"\xe6\x00",
    ],
)
def test_a_malformed_command_message_is_dropped_not_raised(message: bytes) -> None:
    host = FakeHost()
    assert host.prediction.handle_message(77, Channel.COMMANDS, message)
    assert host.prediction.malformed == 1


def test_one_bad_value_discards_the_whole_message() -> None:
    @dataclass(frozen=True, slots=True)
    class Press:
        fire: bool = False

    prediction = PredictionHost(
        CommandSchema(Press, fire=Flag()), Press(), lambda *_: True
    )
    prediction.add_peer(1, 1)
    message = struct.pack("<BIBB", 0xE6, 1, 0, 2) + bytes([1, 9])
    assert prediction.handle_message(1, Channel.COMMANDS, message)
    assert prediction.malformed == 1
    assert prediction.take(1, 1) == Press()


def test_messages_that_arent_commands_are_left_for_the_game() -> None:
    host = FakeHost()
    assert not host.prediction.handle_message(77, Channel.COMMANDS, b"\x01hello")
    assert not host.prediction.handle_message(77, Channel.COMMANDS, b"")
    assert not host.prediction.handle_message(
        77, Channel.EVENTS, host.commands(0, Move())
    )


def test_the_host_driver_passes_the_games_own_messages_through() -> None:
    game = Game(conditions=LinkConditions())
    received: list[object] = []
    original = game.on_host_event

    def spy(event: object) -> None:
        received.append(event)
        original(event)

    game.driver._on_event = spy
    game.join()
    game.players[0].session.send(Channel.COMMANDS, b"\x01game")
    game.run(0.2)
    assert any(
        isinstance(e, MessageReceived) and e.data == b"\x01game" for e in received
    )


def test_random_bytes_never_raise_on_the_host() -> None:
    rng = random.Random(5)
    host = FakeHost()
    for _ in range(5000):
        data = bytes([0xE6]) + rng.randbytes(rng.randint(0, 200))
        host.prediction.handle_message(77, rng.randint(0, 5), data)


def owner_state(tick: int, *values: float) -> bytes:
    return struct.pack("<BIBbB", 0xE7, tick, 0, -128, len(values)) + (
        struct.pack(f"<{len(values)}d", *values)
    )


def started_client() -> tuple[Player, Game]:
    game = Game(conditions=LinkConditions())
    game.join()
    game.run(0.5)
    return game.players[0], game


@pytest.mark.parametrize(
    "values",
    [
        (math.nan, 0.0, 0.0, 0.0),
        (0.0, math.inf, 0.0, 0.0),
        (0.0, 0.0, -math.inf, 0.0),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 0.0, 0.0),
    ],
    ids=["nan", "inf", "negative-inf", "too-few", "too-many"],
)
def test_a_bad_state_cannot_reach_the_character(values: tuple[float, ...]) -> None:
    player, game = started_client()
    before = player.state()
    tick = game.fixed_tick + 1
    assert player.prediction.handle_message(
        Channel.SNAPSHOT, owner_state(tick, *values)
    )
    assert player.prediction.malformed == 1
    assert player.state() == before


@pytest.mark.parametrize(
    "message",
    [
        b"\xe7",
        struct.pack("<BIBbB", 0xE7, 1, 0, 0, 0),
        struct.pack("<BIBbB", 0xE7, 1, 0, 0, 255) + bytes(8 * 255),
        struct.pack("<BIBbB", 0xE7, 1, 0, 0, 2) + bytes(8),
    ],
)
def test_a_malformed_state_message_is_dropped_not_raised(message: bytes) -> None:
    player, _ = started_client()
    assert player.prediction.handle_message(Channel.SNAPSHOT, message)
    assert player.prediction.malformed == 1


def test_an_old_state_arriving_late_is_ignored() -> None:
    player, game = started_client()
    before = player.state()
    assert player.prediction.handle_message(
        Channel.SNAPSHOT, owner_state(1, 5.0, 5.0, 0.0, 0.0)
    )
    assert player.prediction.stale_states == 1
    assert player.state() == before
    assert game.fixed_tick > 1


def test_replay_work_from_one_message_is_bounded() -> None:
    player, game = started_client()
    last = player.prediction._last_state_tick
    player.prediction._tick += 100_000
    replayed = player.prediction.replayed_ticks
    player.prediction.handle_message(
        Channel.SNAPSHOT, owner_state(last + 1, 5.0, 5.0, 0.0, 0.0)
    )
    assert player.prediction.replayed_ticks - replayed <= 120
    assert game.fixed_tick >= 0


def test_random_bytes_never_raise_on_the_client() -> None:
    rng = random.Random(6)
    player, _ = started_client()
    for _ in range(5000):
        data = bytes([0xE7]) + rng.randbytes(rng.randint(0, 300))
        player.prediction.handle_message(rng.randint(0, 5), data)
    for value in player.state():
        assert math.isfinite(value)


def test_a_command_too_large_is_refused_when_the_schema_is_built() -> None:
    fields = {f"f{index}": Quantised(step=1.0, wide=True) for index in range(17)}
    with pytest.raises(ValueError, match="at most"):
        CommandSchema(Move, **fields)
    with pytest.raises(ValueError, match="at least one"):
        CommandSchema(Move)


def test_a_spawn_claiming_unknown_flags_is_dropped() -> None:
    world = EntityManager()
    replication = ReplicationClient(
        world, state_schema(), {"player": world.create_entity}
    )
    name = b"player"
    message = (
        struct.pack("<BIHBB", 0xE2, 1, 1, len(name), 0x80) + name + struct.pack("<H", 0)
    )
    assert replication.handle_message(Channel.EVENTS, message)
    assert replication.malformed == 1
    assert replication.entities() == {}
