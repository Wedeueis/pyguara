"""A seeded, in-process network that drives the real Rust core.

This sits below the reliability layer, so a test exercises the code that ships
with no sockets, no threads and no sleeps, and a failure replays from its seed.
It proves the logic. It cannot prove how a real connection behaves, or whether
playing over one feels good.

    network = SimulatedNetwork(seed=1, conditions=LinkConditions(loss=0.2))
    host = network.add_host(key)
    client = network.add_client(key, host_address=network.address_of(host))
    network.advance(1 / 60)
"""

from __future__ import annotations

import heapq
import random
import secrets
from collections.abc import Callable
from dataclasses import dataclass

from pyguara.net.transport import (
    DEFAULT_SEND_BYTES_PER_TICK,
    NativeTransport,
    load_core,
)


@dataclass(slots=True)
class LinkConditions:
    """What the network does to each datagram. Change them mid-test freely.

    Attributes:
        latency: One-way delay, in seconds.
        jitter: Extra delay, uniform between 0 and this, in seconds.
        loss: Chance a datagram vanishes.
        duplicate: Chance a datagram arrives twice.
        reorder: Chance a datagram is held back by `reorder_delay`.
        reorder_delay: How long a reordered datagram is held, in seconds.
    """

    latency: float = 0.0
    jitter: float = 0.0
    loss: float = 0.0
    duplicate: float = 0.0
    reorder: float = 0.0
    reorder_delay: float = 0.05


class SimulatedNetwork:
    """Real cores, a fake wire, and an explicit clock."""

    def __init__(
        self,
        seed: int = 0,
        conditions: LinkConditions | None = None,
        send_bytes_per_tick: int = DEFAULT_SEND_BYTES_PER_TICK,
    ) -> None:
        """Create an empty network.

        Args:
            seed: Decides every loss, delay and duplicate. The core's own keys
                are random, but no decision here depends on a packet's bytes, so
                a seed reproduces the same delivery pattern.
            conditions: Network behaviour. Defaults to a perfect network.
            send_bytes_per_tick: Send budget per endpoint, per `advance`.
        """
        self.conditions = conditions if conditions is not None else LinkConditions()
        self.now = 0.0
        self.tap: Callable[[str, str, bytes], object] | None = None
        """Sees every datagram put on the wire, as (source, destination, bytes)."""
        self.drop: Callable[[str, str, bytes], bool] | None = None
        """Decides a datagram's fate exactly, for a test that needs one lost."""
        self._rng = random.Random(seed)
        self._core = load_core()
        self._send_bytes_per_tick = send_bytes_per_tick
        self._endpoints: dict[str, NativeTransport] = {}
        self._in_flight: list[tuple[float, int, str, str, bytes]] = []
        self._sequence = 0
        self._next_host = 1

    def add_host(
        self, key: bytes, address: str | None = None, max_clients: int = 8
    ) -> NativeTransport:
        """Add a host.

        Args:
            key: The session key.
            address: Its address, or None to pick one.
            max_clients: How many may connect.

        Returns:
            Its transport.
        """
        endpoint = self._core.NativeNetEndpoint.host(
            key, max_clients, self._send_bytes_per_tick
        )
        return self._attach(endpoint, address)

    def add_client(
        self,
        key: bytes,
        host_address: str,
        user_data: bytes = b"",
        address: str | None = None,
    ) -> NativeTransport:
        """Add a client, which starts connecting on the next `advance`.

        Args:
            key: The session key it believes in.
            host_address: Where it sends.
            user_data: Up to 256 bytes the host receives with the connection.
            address: Its own address, or None to pick one.

        Returns:
            Its transport.
        """
        client_id = secrets.randbits(63)
        endpoint = self._core.NativeNetEndpoint.client(
            key, client_id, host_address, user_data, self._send_bytes_per_tick
        )
        return self._attach(endpoint, address)

    def _attach(self, endpoint: object, address: str | None) -> NativeTransport:
        if address is None:
            address = f"10.0.0.{self._next_host}:7000"
            self._next_host += 1
        transport = NativeTransport(endpoint)
        self._endpoints[address] = transport
        return transport

    def address_of(self, transport: NativeTransport) -> str:
        """Return a transport's address on this network."""
        for address, candidate in self._endpoints.items():
            if candidate is transport:
                return address
        raise KeyError("That transport is not on this network")

    def remove(self, transport: NativeTransport) -> None:
        """Take an endpoint off the network, as if the player's machine died."""
        del self._endpoints[self.address_of(transport)]

    def inject(self, source: str, destination: str, data: bytes) -> None:
        """Deliver a datagram at once, as an attacker's packet would arrive."""
        endpoint = self._endpoints.get(destination)
        if endpoint is not None:
            endpoint.endpoint.receive(source, data)

    def advance(self, dt: float) -> None:
        """Run the network and every endpoint forward.

        Args:
            dt: Seconds to advance.
        """
        self.now += dt
        while self._in_flight and self._in_flight[0][0] <= self.now:
            _, _, source, destination, data = heapq.heappop(self._in_flight)
            self.inject(source, destination, data)
        for address, transport in self._endpoints.items():
            transport.endpoint.tick(dt)
            for destination, data in transport.endpoint.drain_transmit():
                self._put_on_wire(address, destination, data)

    def _put_on_wire(self, source: str, destination: str, data: bytes) -> None:
        if self.tap is not None:
            self.tap(source, destination, data)
        if self.drop is not None and self.drop(source, destination, data):
            return
        conditions = self.conditions
        rng = self._rng
        if rng.random() < conditions.loss:
            return
        copies = 2 if rng.random() < conditions.duplicate else 1
        for _ in range(copies):
            delay = conditions.latency + rng.random() * conditions.jitter
            if rng.random() < conditions.reorder:
                delay += conditions.reorder_delay
            self._sequence += 1
            heapq.heappush(
                self._in_flight,
                (self.now + delay, self._sequence, source, destination, data),
            )
