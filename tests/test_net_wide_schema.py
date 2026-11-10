"""A schema with more than 16 component types replicates, with a wider mask.

A record says which components it carries in a mask. Up to 16 types it's 16 bits, as
before, so a game that fits pays nothing; past that it's 32 bits, up to 32 types. Host
and client build the same schema, so they agree on the width.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import pytest

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.component import StrictComponent
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.net import (
    ClientDriver,
    ClientSession,
    HostDriver,
    HostSession,
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


def _part(number: int) -> type[StrictComponent]:
    """A component type of its own, holding one number."""

    def init(self: StrictComponent) -> None:
        StrictComponent.__init__(self)

    namespace = {"__annotations__": {"value": int}, "value": 0, "__post_init__": init}
    return dataclass(slots=True)(type(f"Part{number}", (StrictComponent,), namespace))


PARTS = [_part(n) for n in range(31)]


def _schema(types: int) -> ReplicationSchema:
    """Transform, then `types - 1` parts."""
    schema = ReplicationSchema()
    schema.register(Transform, position=QuantisedVector(step=0.25))
    for part in PARTS[: types - 1]:
        schema.register(part, value=UInt16())
    return schema


def test_up_to_sixteen_types_keeps_the_sixteen_bit_mask() -> None:
    assert _schema(16).mask_format == "H"
    assert _schema(17).mask_format == "I"
    assert _schema(32).mask_format == "I"


def test_thirty_two_types_is_the_most() -> None:
    schema = _schema(32)
    with pytest.raises(ValueError, match="At most 32"):
        schema.register(_part(99), value=UInt16())


@dataclass
class _Clock:
    fixed_tick: int = 0


@pytest.mark.parametrize("types", [16, 20, 32])
def test_every_component_arrives_however_many_types_there_are(types: int) -> None:
    network = SimulatedNetwork(seed=1)
    key = secrets.token_bytes(32)
    transport = network.add_host(key)
    address = network.address_of(transport)
    session = HostSession(transport, VERSIONS)
    world = EntityManager()
    clock = _Clock()
    host = ReplicationHost(world, _schema(types), session.send)
    host_driver = HostDriver(clock, session, host)

    carried = PARTS[types - 5 : types - 1]
    guest_world = EntityManager()

    def spawn() -> Entity:
        entity = guest_world.create_entity()
        entity.add_component(Transform())
        for part in carried:
            entity.add_component(part())
        return entity

    client_session = ClientSession(network.add_client(key, address, VERSIONS.encode()))
    client = ReplicationClient(guest_world, _schema(types), {"thing": spawn})
    client_driver = ClientDriver(client_session, client)

    entity = world.create_entity()
    entity.add_component(Transform(position=Vector2(12.0, 34.0)))
    for number, part in enumerate(carried):
        entity.add_component(part(value=1000 + number))
    entity.add_component(Replicated("thing"))

    for _ in range(240):
        network.advance(DT)
        host_driver.before_fixed_updates(DT)
        client_driver.before_fixed_updates(DT)
        clock.fixed_tick += 1
        host_driver.after_fixed_updates(DT)
        client_driver.after_fixed_updates(DT)

    (arrived,) = client.entities().values()
    assert arrived.get_component(Transform).position == Vector2(12.0, 34.0)
    assert [arrived.get_component(p).value for p in carried] == [
        1000 + n for n in range(len(carried))
    ]
    assert client.malformed == 0
