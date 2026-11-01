#!/usr/bin/env python3
"""Phase 0 probes for the networked multiplayer plan.

`project/backlog/active/network_multiplayer.md` makes three claims this file
exists to test before any engine code depends on them:

    snapshot   what one snapshot really costs once it reads ECS components,
               which the plan's section 3 table left out
    notify     whether `notify_component_changed` can drive replication
    replay     whether one character's movement can be re-run on its own,
               which the plan names as its largest technical risk

None of it asserts. It reports, and the numbers go into the plan.

    uv run python tools/net_phase0.py
"""

from __future__ import annotations

import math
import os
import random
import secrets
import struct
import sys
import time
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyguara.ai.flocking_system import FlockingAgent, FlockingSystem  # noqa: E402
from pyguara.common.components import Transform  # noqa: E402
from pyguara.common.spatial import SpatialHash  # noqa: E402
from pyguara.common.types import Vector2  # noqa: E402
from pyguara.ecs.manager import EntityManager  # noqa: E402
from pyguara.events.dispatcher import EventDispatcher  # noqa: E402
from pyguara.kits.action_combat import Health  # noqa: E402
from pyguara.kits.topdown_movement.body import TopDownBody  # noqa: E402
from pyguara.kits.topdown_movement.system import TopDownSystem  # noqa: E402
from pyguara.net import (  # noqa: E402
    Angle,
    Channel,
    ClientSession,
    HostSession,
    MessageReceived,
    PlayerJoined,
    QuantisedVector,
    Replicated,
    ReplicationClient,
    ReplicationHost,
    ReplicationSchema,
    SimulatedNetwork,
    UInt16,
    Versions,
)
from pyguara.physics.backends.pymunk_impl import PymunkEngine  # noqa: E402
from pyguara.physics.character_mover import CharacterMover  # noqa: E402
from pyguara.physics.components import Collider, RigidBody  # noqa: E402
from pyguara.physics.physics_system import PhysicsSystem  # noqa: E402
from pyguara.physics.types import BodyType, ShapeType  # noqa: E402
from pyguara.spatial.components import SpatialTracked  # noqa: E402
from pyguara.spatial.system import SpatialIndexSystem  # noqa: E402

DT = 1.0 / 60.0
RECORD = struct.Struct("<HhhhhH")  # id, x, y, vx, vy, state: the plan's 12 bytes
INTERPOLATION_TICKS = 6  # the plan's ~100 ms of remote interpolation, at 60 Hz


def fastest(fn: Callable[[], object], rounds: int = 200) -> float:
    """Fastest of `rounds` calls, in milliseconds, as the plan's table is."""
    fn()
    best = math.inf
    for _ in range(rounds):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best * 1000.0


def build_horde(count: int) -> tuple[EntityManager, FlockingSystem]:
    """A horde of real components, moved by the real flocking system."""
    manager = EntityManager()
    rng = random.Random(count)
    side = 40.0 * math.sqrt(count)
    target = Vector2(side / 2, side / 2)
    for _ in range(count):
        entity = manager.create_entity()
        entity.add_component(
            Transform(position=Vector2(rng.uniform(0, side), rng.uniform(0, side)))
        )
        entity.add_component(
            FlockingAgent(max_speed=90.0, seek_weight=1.0, seek_target=target)
        )
        entity.add_component(Health(current=30, max_health=30))
        entity.add_component(SpatialTracked())
    return manager, FlockingSystem(manager, cell_size=48.0)


def probe_snapshot() -> None:
    """Read and pack a snapshot from live components, after real simulation."""
    print("\n== snapshot: read from ECS, then pack ==")
    print(
        f"{'entities':>8} {'read':>9} {'pack':>9} {'total':>9} {'%frame':>7} "
        f"{'bytes':>7} {'zlib1':>7} {'delta+z':>8} {'Mbit/s@20Hz':>12}"
    )
    for count in (200, 500, 1000):
        manager, flocking = build_horde(count)
        for _ in range(180):
            flocking.update(DT)

        ids: dict[str, int] = {}
        for index, entity in enumerate(
            manager.get_entities_with(Transform, FlockingAgent, Health)
        ):
            ids[entity.id] = index

        columns: list[tuple[int, float, float, float, float, int]] = []

        def read(
            manager: EntityManager = manager,
            ids: dict[str, int] = ids,
            columns: list[tuple[int, float, float, float, float, int]] = columns,
        ) -> None:
            columns.clear()
            append = columns.append
            for entity in manager.get_entities_with(Transform, FlockingAgent, Health):
                position = entity.get_component(Transform).position
                velocity = entity.get_component(FlockingAgent).velocity
                health = entity.get_component(Health)
                append(
                    (
                        ids[entity.id],
                        position.x,
                        position.y,
                        velocity.x,
                        velocity.y,
                        health.current,
                    )
                )

        buffer = bytearray(RECORD.size * count)

        def pack(
            columns: list[tuple[int, float, float, float, float, int]] = columns,
            buffer: bytearray = buffer,
        ) -> None:
            offset = 0
            pack_into = RECORD.pack_into
            size = RECORD.size
            for nid, x, y, vx, vy, hp in columns:
                pack_into(
                    buffer,
                    offset,
                    nid,
                    int(x * 4) & 0x7FFF,
                    int(y * 4) & 0x7FFF,
                    int(vx * 8),
                    int(vy * 8),
                    int(hp),
                )
                offset += size

        read_ms = fastest(read)
        pack_ms = fastest(pack)

        # Compressibility on real positions, and of a delta three fixed ticks
        # later -- what a 20 Hz snapshot would actually be encoded against.
        read()
        pack()
        first = bytes(buffer)
        for _ in range(3):
            flocking.update(DT)
        read()
        pack()
        second = bytes(buffer)
        xored = bytes(a ^ b for a, b in zip(first, second, strict=True))
        plain = len(second)
        z1 = len(zlib.compress(second, 1))
        delta = len(zlib.compress(xored, 1))
        total = read_ms + pack_ms
        print(
            f"{count:8d} {read_ms:8.3f}m {pack_ms:8.3f}m {total:8.3f}m "
            f"{total / (1000 / 60):7.1%} {plain:7d} {z1:7d} {delta:8d} "
            f"{plain * 8 * 20 / 1e6:12.2f}"
        )


def probe_notify() -> None:
    """Count writes against notifications for the real movement systems."""
    print("\n== notify: does each movement writer call notify? ==")

    def report(name: str, manager: EntityManager, step: Callable[[], None]) -> None:
        notified = [0]

        def on_changed(*_: object) -> None:
            notified[0] += 1

        manager.subscribe_component_changed(Transform, on_changed)
        entities = list(manager.get_entities_with(Transform))
        before = [e.get_component(Transform).position for e in entities]
        for _ in range(30):
            step()
        moved = sum(
            1
            for e, old in zip(entities, before, strict=True)
            if e.get_component(Transform).position != old
        )
        print(
            f"  {name:18} moved {moved:3d}/{len(entities):3d}, notified {notified[0]}"
        )

    manager, flocking = build_horde(50)
    report("FlockingSystem", manager, lambda: flocking.update(DT))

    engine = PymunkEngine()
    engine.initialize(Vector2(0, 0))
    manager = EntityManager()
    for i in range(10):
        entity = manager.create_entity()
        entity.add_component(Transform(position=Vector2(i * 40.0, 0.0)))
        entity.add_component(TopDownBody(velocity=Vector2(60, 30)))
    topdown = TopDownSystem(manager, engine, SpatialHash(cell_size=48.0))
    report("TopDownSystem", manager, lambda: topdown.update(DT))
    engine.cleanup()

    engine = PymunkEngine()
    engine.initialize(Vector2(0, 100))
    manager = EntityManager()
    physics = PhysicsSystem(engine, manager, EventDispatcher(), gravity=Vector2(0, 100))
    for i in range(10):
        entity = manager.create_entity()
        entity.add_component(Transform(position=Vector2(i * 40.0, 0.0)))
        entity.add_component(RigidBody())
        entity.add_component(Collider(shape_type=ShapeType.CIRCLE, dimensions=[5.0]))
    report("PhysicsSystem", manager, lambda: physics.update(DT))
    engine.cleanup()


class _ReplayWorld:
    """A walled room and the player, on the real systems, stepped as a host is.

    Args:
        enemy: None, "solid" (a moving kinematic body that blocks the mover) or
            "separation" (no collider; pushes the player positionally).
    """

    def __init__(self, enemy: str | None = None) -> None:
        self.engine = PymunkEngine()
        self.engine.initialize(Vector2(0, 0))
        self.manager = EntityManager()
        dispatcher = EventDispatcher()
        self.physics = PhysicsSystem(self.engine, self.manager, dispatcher)
        self.index: SpatialHash[str] = SpatialHash(cell_size=48.0)
        self.spatial = SpatialIndexSystem(self.manager, self.index, dispatcher)
        self.topdown = TopDownSystem(self.manager, self.engine, self.index)

        for x, y, w, h in (
            (200, -10, 460, 20),
            (200, 310, 460, 20),
            (-10, 150, 20, 340),
            (410, 150, 20, 340),
            (200, 150, 40, 40),
        ):
            wall = self.manager.create_entity()
            wall.add_component(Transform(position=Vector2(x, y)))
            wall.add_component(RigidBody(body_type=BodyType.STATIC))
            wall.add_component(Collider(shape_type=ShapeType.BOX, dimensions=[w, h]))

        separation = 14.0 if enemy == "separation" else 0.0
        self.player = self.manager.create_entity()
        self.player.add_component(Transform(position=Vector2(60, 150)))
        self.player.add_component(TopDownBody(separation_radius=separation))
        self.player.add_component(RigidBody(body_type=BodyType.KINEMATIC))
        self.player.add_component(
            Collider(shape_type=ShapeType.BOX, dimensions=[20, 20])
        )
        self.player.add_component(SpatialTracked())

        self.enemy = None
        if enemy:
            self.enemy = self.manager.create_entity()
            self.enemy.add_component(Transform(position=Vector2(120, 150)))
            self.enemy.add_component(TopDownBody(separation_radius=separation))
            self.enemy.add_component(SpatialTracked())
            if enemy == "solid":
                self.enemy.add_component(RigidBody(body_type=BodyType.KINEMATIC))
                self.enemy.add_component(
                    Collider(shape_type=ShapeType.BOX, dimensions=[24, 24])
                )

    def tick(self, velocity: Vector2) -> None:
        """One fixed tick: control, movement, index, physics."""
        self.player.get_component(TopDownBody).velocity = velocity
        if self.enemy is not None:
            # An enemy that chases, so it keeps meeting the player.
            to_player = (
                self.player.get_component(Transform).position
                - self.enemy.get_component(Transform).position
            )
            self.enemy.get_component(TopDownBody).velocity = (
                to_player.normalize() * 80.0
                if to_player.magnitude > 1
                else Vector2(0, 0)
            )
        self.topdown.update(DT)
        self.spatial.update(DT)
        self.physics.update(DT)

    def space_state(self) -> list[tuple[object, ...]]:
        """Every body's state: what a replay must leave alone."""
        assert self.engine.space is not None
        return sorted(
            (
                str(getattr(b, "entity_id", "")),
                tuple(b.position),
                tuple(b.velocity),
                b.angle,
            )
            for b in self.engine.space.bodies
        )


def _commands(ticks: int) -> list[Vector2]:
    """Scripted velocities that run into the room's walls and centre block."""
    rng = random.Random(7)
    out = []
    velocity = Vector2(200, 0)
    for tick in range(ticks):
        if tick % 25 == 0:
            angle = rng.uniform(0, math.tau)
            velocity = Vector2(math.cos(angle) * 217.3, math.sin(angle) * 217.3)
        out.append(velocity)
    return out


def _replay_scenario(enemy: str | None) -> None:
    """Run one authoritative session, then replay every window of it alone."""
    ticks = 600
    commands = _commands(ticks)
    half = Vector2(10, 10)
    world = _ReplayWorld(enemy)
    transform = world.player.get_component(Transform)
    body = world.player.get_component(TopDownBody)
    history = [(transform.position, body._remainder)]
    enemy_at = [world.enemy.get_component(Transform).position if world.enemy else None]
    blocked = 0
    for velocity in commands:
        before_tick = transform.position
        world.tick(velocity)
        moved = (transform.position - before_tick).magnitude
        blocked += moved < velocity.magnitude * DT - 2.0
        history.append((transform.position, body._remainder))
        enemy_at.append(
            world.enemy.get_component(Transform).position if world.enemy else None
        )

    mover = CharacterMover(world.engine)
    before = world.space_state()

    def show_enemy_at(tick: int) -> None:
        """Put a solid enemy where the client would be displaying it."""
        if enemy != "solid":
            return
        assert world.enemy is not None and world.engine.space is not None
        handle = world.enemy.get_component(RigidBody)._body_handle
        assert handle is not None
        handle.position = enemy_at[tick]
        world.engine.space.reindex_shapes_for_body(handle._body)

    def replay_from(tick: int, depth: int, keep_remainder: bool) -> Vector2:
        # The client replays at time tick + depth, showing every remote
        # entity INTERPOLATION_TICKS behind that, and it holds still for
        # the whole replay: the client has no later view of it.
        show_enemy_at(max(0, tick + depth - INTERPOLATION_TICKS))
        position, remainder = history[tick]
        if not keep_remainder:
            remainder = Vector2(0, 0)
        for step in range(tick, tick + depth):
            result = mover.move(
                position, half, commands[step] * DT, remainder, world.player.id
            )
            position, remainder = result.position, result.remainder
        return position

    print(f"  -- enemy: {enemy}; {blocked}/{ticks} ticks visibly blocked")
    for depth in (6, 12):
        differ = worst = differ_np = worst_np = cases = 0.0
        for tick in range(ticks - depth):
            cases += 1
            truth = history[tick + depth][0]
            error = (replay_from(tick, depth, True) - truth).magnitude
            differ += bool(error)
            worst = max(worst, error)
            error = (replay_from(tick, depth, False) - truth).magnitude
            differ_np += bool(error)
            worst_np = max(worst_np, error)
        print(
            f"     depth {depth:2d}: with remainder {differ / cases:6.1%} differ "
            f"(worst {worst:6.2f}px); position only {differ_np / cases:6.1%} "
            f"(worst {worst_np:6.2f}px)"
        )
    show_enemy_at(ticks)
    print(f"     physics world untouched by replay: {world.space_state() == before}")

    if enemy is None:
        for depth in (6, 12, 24):
            ms = fastest(lambda d=depth: replay_from(100, d, True), rounds=100)
            print(
                f"     cost, depth {depth:2d}: {ms:6.3f} ms "
                f"({ms / (1000 / 60):5.1%} of a frame, once per snapshot)"
            )
    world.engine.cleanup()


def probe_replay() -> None:
    """Can one character be re-run alone, from a past state, matching the host?"""
    print("\n== replay: re-run one character with CharacterMover alone ==")
    for enemy in (None, "solid", "separation"):
        _replay_scenario(enemy)


class _ProbeFrame:
    """One frame of a host and its clients, timing the host and the first client."""

    def __init__(
        self,
        network: SimulatedNetwork,
        host_session: HostSession,
        host: ReplicationHost,
        flocking: FlockingSystem,
        sessions: list[ClientSession],
        clients: list[ReplicationClient],
    ) -> None:
        self._network = network
        self._host_session = host_session
        self._host = host
        self._flocking = flocking
        self._sessions = sessions
        self._clients = clients
        self._tick = 0

    def _run_client(self, index: int) -> None:
        client = self._clients[index]
        for event in self._sessions[index].poll():
            if isinstance(event, MessageReceived):
                client.handle_message(event.channel, event.data)
        client.update(DT)

    def frame(self) -> tuple[float, float]:
        self._network.advance(DT)
        for event in self._host_session.poll():
            if isinstance(event, PlayerJoined):
                self._host.add_peer(event.peer, event.slot)
        self._flocking.update(DT)
        self._tick += 1
        began = time.perf_counter()
        self._host.step(self._tick)
        sent = time.perf_counter() - began
        began = time.perf_counter()
        self._run_client(0)
        applied = time.perf_counter() - began
        for index in range(1, len(self._clients)):
            self._run_client(index)
        return sent, applied


def _spawner_for(world: EntityManager) -> Callable[[], Any]:
    def spawn() -> Any:
        entity = world.create_entity()
        entity.add_component(Transform())
        entity.add_component(Health(current=1, max_health=1))
        return entity

    return spawn


def _make_schema() -> ReplicationSchema:
    built = ReplicationSchema()
    built.register(Transform, position=QuantisedVector(step=0.25), rotation=Angle())
    built.register(Health, current=UInt16())
    return built


def probe_replication() -> None:
    """What the built replication costs per frame, with the real core underneath."""
    print("\n== replication: built, 3 clients, real Rust core, no network loss ==")
    print(
        f"{'entities':>8} {'host send':>10} {'%frame':>7} {'client apply':>13} "
        f"{'%frame':>7} {'bytes/client':>13} {'Mbit/s':>7}"
    )
    for count in (200, 500, 1000):
        network = SimulatedNetwork(seed=count)
        key = secrets.token_bytes(32)
        host_transport = network.add_host(key)
        address = network.address_of(host_transport)
        versions = Versions("probe", "1")
        host_session = HostSession(host_transport, versions)
        manager, flocking = build_horde(count)
        for entity in list(manager.get_entities_with(Transform)):
            entity.add_component(Replicated("enemy"))

        bytes_sent = [0]

        def send(
            peer: int,
            channel: Channel,
            data: bytes,
            session: HostSession = host_session,
            counter: list[int] = bytes_sent,
        ) -> bool:
            counter[0] += len(data)
            return session.send(peer, channel, data)

        host = ReplicationHost(manager, _make_schema(), send)
        sessions = []
        clients = []
        worlds = []
        for _ in range(3):
            world = EntityManager()

            client_transport = network.add_client(key, address, versions.encode())
            sessions.append(ClientSession(client_transport))
            clients.append(
                ReplicationClient(world, _make_schema(), {"enemy": _spawner_for(world)})
            )
            worlds.append(world)

        world_state = _ProbeFrame(
            network, host_session, host, flocking, sessions, clients
        )
        for _ in range(240):
            world_state.frame()
        assert len(clients[0].entities()) == count

        bytes_sent[0] = 0
        frames = 300
        sends: list[float] = []
        applies: list[float] = []
        for _ in range(frames):
            sent, applied = world_state.frame()
            sends.append(sent)
            applies.append(applied)
        # Per frame, averaged over the snapshot cadence: a snapshot is every third.
        send_ms = sum(sends) / frames * 1000
        apply_ms = sum(applies) / frames * 1000
        snapshots = frames / 3
        per_client = bytes_sent[0] / 3 / snapshots
        print(
            f"{count:8d} {send_ms:9.3f}m {send_ms / (1000 / 60):7.1%} "
            f"{apply_ms:12.3f}m {apply_ms / (1000 / 60):7.1%} "
            f"{per_client:13.0f} {per_client * 8 * 20 / 1e6:7.2f}"
        )
        print(
            f"         worst frame: host {max(sends) * 1000:.2f} ms, "
            f"client {max(applies) * 1000:.2f} ms"
        )


def main() -> int:
    """Run every probe."""
    probe_snapshot()
    probe_notify()
    probe_replay()
    probe_replication()
    return 0


if __name__ == "__main__":
    sys.exit(main())
