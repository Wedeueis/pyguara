"""The native interpolator writes exactly what the Python path writes.

A component whose every field interpolates is blended natively; one with a
field that does not stays in Python, through `write_blended`. So two
components with the same interpolating fields, one of them carrying an extra
integer, give the two paths the same motion, and every value written is
compared, as `float.hex`, on every frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pytest

from pyguara.common.random import RandomStream
from pyguara.common.types import Vector2
from pyguara.ecs.component import StrictComponent
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.net import (
    Angle,
    Channel,
    Quantised,
    QuantisedVector,
    Replicated,
    ReplicationClient,
    ReplicationHost,
    ReplicationSchema,
    UInt8,
)


@dataclass(slots=True)
class Smooth(StrictComponent):
    """Every field interpolates, so the native path writes it."""

    position: Vector2 = field(default_factory=Vector2.zero)
    heading: float = 0.0
    height: float = 0.0


@dataclass(slots=True)
class Stepped(StrictComponent):
    """The same fields and an integer, so the Python path writes it."""

    position: Vector2 = field(default_factory=Vector2.zero)
    heading: float = 0.0
    height: float = 0.0
    level: int = 0


def _fields() -> dict[str, Any]:
    return {
        "position": QuantisedVector(step=0.25, snap_distance=64.0),
        "heading": Angle(bits=16),
        "height": Quantised(step=0.01),
    }


def _schema() -> ReplicationSchema:
    schema = ReplicationSchema()
    schema.register(Smooth, **_fields())
    schema.register(Stepped, **_fields(), level=UInt8())
    return schema


def _hexed(component: Any) -> tuple[str, ...]:
    return (
        component.position.x.hex(),
        component.position.y.hex(),
        float(component.heading).hex(),
        float(component.height).hex(),
    )


class _Game:
    """A host and one client, with every entity carrying both components."""

    def __init__(self, seed: int) -> None:
        self.rng = RandomStream(seed)
        self.host_world = EntityManager()
        self.outgoing: list[tuple[Channel, bytes]] = []
        self.host = ReplicationHost(
            self.host_world,
            _schema(),
            lambda peer, channel, data: self.outgoing.append((channel, data)) or True,
            snapshot_interval_ticks=3,
            max_snapshot_bytes=10**7,
        )
        self.client_world = EntityManager()
        self.client = ReplicationClient(
            self.client_world, _schema(), {"thing": self._spawn}
        )
        self.host.add_peer(1, 1)
        self.alive: list[Entity] = []
        self.tick = 0

    def _spawn(self) -> Entity:
        entity = self.client_world.create_entity()
        entity.add_component(Smooth())
        entity.add_component(Stepped())
        return entity

    def add(self) -> None:
        entity = self.host_world.create_entity()
        start = Vector2(self.rng.uniform(-500, 500), self.rng.uniform(-500, 500))
        entity.add_component(Smooth(position=start))
        entity.add_component(Stepped(position=start))
        entity.add_component(Replicated("thing"))
        self.alive.append(entity)

    def move(self) -> None:
        for entity in self.alive:
            jump = self.rng.uniform(0.0, 1.0) < 0.03
            dx = self.rng.uniform(-200, 200) if jump else self.rng.uniform(-3, 3)
            dy = self.rng.uniform(-200, 200) if jump else self.rng.uniform(-3, 3)
            turn = self.rng.uniform(-0.6, 0.6)
            rise = self.rng.uniform(-0.2, 0.2)
            for component_type in (Smooth, Stepped):
                component = entity.get_component(component_type)
                component.position = Vector2(
                    component.position.x + dx, component.position.y + dy
                )
                component.heading = (component.heading + turn) % math.tau
                component.height = component.height + rise
                self.host_world.notify_component_changed(entity.id, component_type)

    def frame(self, *, drop_snapshots: bool = False) -> None:
        self.tick += 1
        self.host.step(self.tick)
        messages, self.outgoing = self.outgoing, []
        for channel, data in messages:
            if drop_snapshots and channel == Channel.SNAPSHOT:
                continue
            self.client.handle_message(channel, data)
        self.client.update(1 / 60)

    def compare(self) -> list[str]:
        differing = []
        for entity in self.client_world.get_entities_with(Smooth, Stepped):
            smooth = _hexed(entity.get_component(Smooth))
            stepped = _hexed(entity.get_component(Stepped))
            if smooth != stepped:
                differing.append(f"{entity.id}: native {smooth}, python {stepped}")
        return differing


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_every_value_written_matches_the_python_path(seed: int) -> None:
    game = _Game(seed)
    for _ in range(40):
        game.add()
    frames = 0
    for frame in range(600):
        game.move()
        if frame % 37 == 0 and game.alive:
            game.host_world.remove_entity(
                game.alive.pop(int(game.rng.uniform(0, len(game.alive) - 1e-9))).id
            )
        if frame % 23 == 0:
            game.add()
        game.frame(drop_snapshots=200 <= frame < 215)
        differing = game.compare()
        assert not differing, f"frame {frame}: {differing[:3]}"
        frames += 1

    assert len(game.client.entities()) > 30
    assert frames == 600


def test_the_scenario_exercises_every_path() -> None:
    """Teleports, a lost burst of snapshots and churn, or the test is idle."""
    game = _Game(1)
    for _ in range(40):
        game.add()
    held_frames = 0
    for frame in range(300):
        game.move()
        game.frame(drop_snapshots=100 <= frame < 140)
        render = game.client.render_tick
        newest = game.client._newest_tick
        if render is not None and newest is not None and render >= newest:
            held_frames += 1
    assert held_frames > 0


def test_a_forgotten_remote_is_released() -> None:
    game = _Game(4)
    for _ in range(5):
        game.add()
    for _ in range(30):
        game.move()
        game.frame()
    kept = len(game.client._native)
    for entity in list(game.alive):
        game.host_world.remove_entity(entity.id)
    game.alive.clear()
    for _ in range(60):
        game.frame()
    assert kept == 5
    assert len(game.client._native) == 0
