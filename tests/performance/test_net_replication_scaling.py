"""Replication's cost must stay linear in entities.

A ratio, not a wall-clock limit, so it holds on any machine.
"""

from __future__ import annotations

import time

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.net import (
    Angle,
    Channel,
    QuantisedVector,
    Replicated,
    ReplicationClient,
    ReplicationHost,
    ReplicationSchema,
)

pytestmark = pytest.mark.performance


def _schema() -> ReplicationSchema:
    schema = ReplicationSchema()
    schema.register(Transform, position=QuantisedVector(step=0.25), rotation=Angle())
    return schema


def _cost(count: int) -> tuple[float, float]:
    """Return the fastest host snapshot and client frame at `count` entities."""
    world = EntityManager()
    outgoing: list[tuple[Channel, bytes]] = []

    def send(peer: int, channel: Channel, data: bytes) -> bool:
        outgoing.append((channel, data))
        return True

    host = ReplicationHost(
        world, _schema(), send, snapshot_interval_ticks=1, max_snapshot_bytes=10**7
    )
    entities = []
    for index in range(count):
        entity = world.create_entity()
        entity.add_component(Transform(position=Vector2(index % 100, index % 77)))
        entity.add_component(Replicated("enemy"))
        entities.append(entity)
    client_world = EntityManager()

    def spawn() -> Entity:
        entity = client_world.create_entity()
        entity.add_component(Transform())
        return entity

    client = ReplicationClient(client_world, _schema(), {"enemy": spawn})
    host.add_peer(1, 1)
    best_host = best_client = float("inf")
    for tick in range(1, 40):
        for entity in entities:
            transform = entity.get_component(Transform)
            transform.position = transform.position + Vector2(1, 0)
        began = time.perf_counter()
        host.step(tick)
        best_host = min(best_host, time.perf_counter() - began)
        messages = list(outgoing)
        outgoing.clear()
        began = time.perf_counter()
        for channel, data in messages:
            client.handle_message(channel, data)
        client.update(1 / 60)
        if tick > 15:
            best_client = min(best_client, time.perf_counter() - began)
    assert len(client.entities()) == count
    return best_host, best_client


def test_host_and_client_cost_stay_linear() -> None:
    small_host, small_client = _cost(250)
    large_host, large_client = _cost(1000)

    assert large_host / small_host < 6.5
    assert large_client / small_client < 6.5
