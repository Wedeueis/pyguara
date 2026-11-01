"""Moving whole messages between peers: the protocol, and the UDP backend.

A `Transport` is what the session layer needs from a network and no more, so a
Steam transport can sit behind it later. The Rust core does the work: this module
only adapts it. See `rust/src/net/core.rs`.

Poll a transport once a frame. It never raises because of what a peer sent:
hostile bytes are dropped below this layer, and a core that fails says so with
`TransportFailed`.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Protocol

from pyguara import native

NET_PROTOCOL_VERSION = 1
"""Must equal `PROTOCOL_VERSION` in `rust/src/net/core.rs`."""

HOST_PEER = 0
"""The peer id a client uses for the host."""

# 12.5 kB per tick at the socket thread's 120 Hz is 12 Mbit/s, which is a ceiling
# on a burst such as a level transfer, not a rate anything sustains.
DEFAULT_SEND_BYTES_PER_TICK = 12_500


class Channel(IntEnum):
    """What a message is for, which decides how it is delivered."""

    CONTROL = 0
    """Reliable and ordered. Used by the session layer, not by games."""
    EVENTS = 1
    """Reliable and ordered: damage, deaths, drops, spawns."""
    COMMANDS = 2
    """Unreliable: per-tick player input, repeated across packets."""
    SNAPSHOT = 3
    """Unreliable, and possibly reordered, so messages must carry their tick."""
    LEVEL = 4
    """Reliable and ordered, and lowest priority: large transfers."""


@dataclass(frozen=True, slots=True)
class PeerConnected:
    """A peer finished the encrypted handshake."""

    peer: int
    user_data: bytes


@dataclass(frozen=True, slots=True)
class PeerDisconnected:
    """A peer is gone."""

    peer: int
    reason: str


@dataclass(frozen=True, slots=True)
class MessageDelivered:
    """A whole message arrived. Its contents are untrusted."""

    peer: int
    channel: int
    data: bytes


@dataclass(frozen=True, slots=True)
class TransportFailed:
    """The transport itself stopped working, and will deliver nothing more."""

    reason: str


TransportEvent = PeerConnected | PeerDisconnected | MessageDelivered | TransportFailed


@dataclass(frozen=True, slots=True)
class LinkStats:
    """How one peer's connection is doing."""

    rtt: float
    packet_loss: float
    bytes_sent_per_second: float
    bytes_received_per_second: float


class Transport(Protocol):
    """A way to exchange messages with peers."""

    def send(self, peer: int, channel: Channel, data: bytes) -> bool:
        """Queue a message.

        Args:
            peer: Who to send to. A client uses `HOST_PEER`.
            channel: How to deliver it.
            data: The message.

        Returns:
            False if it was not accepted: no such peer, or the channel is over
            its memory limit, which on a reliable channel means a backlog.
        """
        ...

    def poll(self) -> list[TransportEvent]:
        """Return everything that happened since the last call."""
        ...

    def disconnect(self, peer: int, flush: bool = False) -> None:
        """End a peer's connection.

        Args:
            peer: Who. A client's only peer is the host.
            flush: Wait until its reliable messages are acknowledged, within a
                few seconds, so that a final message can be read.
        """
        ...

    def stats(self, peer: int) -> LinkStats | None:
        """Return a peer's link statistics, or None if it is gone."""
        ...

    def close(self) -> None:
        """Say goodbye to every peer and release the network."""
        ...


def load_core() -> Any:
    """Return the native module, checked against this Python code.

    Called when a session starts rather than at import, so a single-player game
    on a platform with no wheel is unaffected. A backend, not a store, so
    `PYGUARA_NO_NATIVE=1` does not turn it off: ADR 0004, Decision 4.

    Returns:
        The extension module.

    Raises:
        RuntimeError: If the extension is missing or was built from other code.
    """
    module = native.require_extension("networked multiplayer")
    built = getattr(module, "NET_PROTOCOL_VERSION", None)
    if built != NET_PROTOCOL_VERSION:
        raise RuntimeError(
            f"The native extension speaks network protocol {built}, but this code "
            f"expects {NET_PROTOCOL_VERSION}. It is a stale build: run `make native`."
        )
    return module


class NativeTransport:
    """Adapts a native endpoint to `Transport`.

    Attributes:
        endpoint: The native endpoint, for the simulated network to drive.
    """

    def __init__(self, endpoint: Any) -> None:
        """Wrap an endpoint.

        Args:
            endpoint: A `NativeNetEndpoint`.
        """
        self.endpoint = endpoint

    def send(self, peer: int, channel: Channel, data: bytes) -> bool:
        """See `Transport.send`."""
        return bool(self.endpoint.send(peer, int(channel), data))

    def poll(self) -> list[TransportEvent]:
        """See `Transport.poll`."""
        events: list[TransportEvent] = []
        for item in self.endpoint.poll():
            kind = item[0]
            if kind == "message":
                events.append(MessageDelivered(item[1], item[2], item[3]))
            elif kind == "connected":
                events.append(PeerConnected(item[1], item[2]))
            elif kind == "disconnected":
                events.append(PeerDisconnected(item[1], item[2]))
            else:
                events.append(TransportFailed(item[2]))
        return events

    def disconnect(self, peer: int, flush: bool = False) -> None:
        """See `Transport.disconnect`."""
        self.endpoint.disconnect(peer, flush)

    def stats(self, peer: int) -> LinkStats | None:
        """See `Transport.stats`."""
        raw = self.endpoint.stats(peer)
        return LinkStats(**raw) if raw is not None else None

    def close(self) -> None:
        """See `Transport.close`."""
        self.endpoint.close()

    def counters(self) -> dict[str, int]:
        """Return what the core's guards have rejected so far."""
        return dict(self.endpoint.counters())


class UdpTransport(NativeTransport):
    """A `Transport` over a real UDP socket, driven by a Rust thread.

    The thread acknowledges, resends and sends keepalives without the GIL, so a
    stalled Python frame delays game state and not the connection.

    Attributes:
        local_address: The address the socket actually bound, as `ip:port`.
    """

    def __init__(self, endpoint: Any, bind: str) -> None:
        """Start the socket thread.

        Args:
            endpoint: A `NativeNetEndpoint`.
            bind: Where to bind, as `ip:port`.
        """
        super().__init__(endpoint)
        self.local_address: str = endpoint.start_udp(bind)

    @classmethod
    def host(
        cls,
        key: bytes,
        port: int,
        max_clients: int = 8,
        bind_ip: str = "0.0.0.0",  # noqa: S104 - a host has to be reachable
        send_bytes_per_tick: int = DEFAULT_SEND_BYTES_PER_TICK,
    ) -> UdpTransport:
        """Start hosting.

        Args:
            key: The session key from the invite.
            port: UDP port, or 0 for any free one.
            max_clients: How many may connect.
            bind_ip: Which local address to listen on.
            send_bytes_per_tick: Send budget per peer, per 120 Hz tick.

        Returns:
            The running transport.

        Raises:
            RuntimeError: If the native extension is missing or stale.
            OSError: If the port cannot be bound.
        """
        core = load_core()
        endpoint = core.NativeNetEndpoint.host(key, max_clients, send_bytes_per_tick)
        return cls(endpoint, _join_address(bind_ip, port))

    @classmethod
    def client(
        cls,
        key: bytes,
        client_id: int,
        host: str,
        port: int,
        user_data: bytes = b"",
        send_bytes_per_tick: int = DEFAULT_SEND_BYTES_PER_TICK,
    ) -> UdpTransport:
        """Start connecting to a host.

        Args:
            key: The session key from the invite.
            client_id: This client's id. Random, so that it cannot collide.
            host: The host's name or IP address.
            port: The host's UDP port.
            user_data: Up to 256 bytes the host receives with the connection.
            send_bytes_per_tick: Send budget per 120 Hz tick.

        Returns:
            The running transport.

        Raises:
            RuntimeError: If the native extension is missing or stale.
            OSError: If the host's name cannot be resolved.
        """
        core = load_core()
        family, _, _, _, address = socket.getaddrinfo(
            host, port, type=socket.SOCK_DGRAM
        )[0]
        server = _join_address(str(address[0]), int(address[1]))
        bind_ip = "::" if family == socket.AF_INET6 else "0.0.0.0"  # noqa: S104
        endpoint = core.NativeNetEndpoint.client(
            key, client_id, server, user_data, send_bytes_per_tick
        )
        return cls(endpoint, _join_address(bind_ip, 0))


def _join_address(ip: str, port: int) -> str:
    """Format an address the way Rust's `SocketAddr` parses it."""
    return f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"
