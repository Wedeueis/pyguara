"""Networked multiplayer: a listen server and the players who join it.

Opt-in, so a single-player game imports none of this. Importing it is always
safe, even with no native extension. A session is what needs one, and fails with
a clear message when it starts.

Everything arriving from the network is untrusted. The Rust core authenticates
packets and survives hostile ones, but it does not make a decoded value
sensible, so code above this package bounds-checks lengths, ids and enums itself.
See `docs/systems/networking.md`.
"""

from pyguara.net.session import (
    ClientSession,
    HostSession,
    Invite,
    Joined,
    Left,
    MessageReceived,
    PlayerJoined,
    PlayerLeft,
    Refused,
    SessionEvent,
    SessionFailed,
    Versions,
)
from pyguara.net.simulated import LinkConditions, SimulatedNetwork
from pyguara.net.transport import Channel, LinkStats, Transport, UdpTransport

__all__ = [
    "Channel",
    "ClientSession",
    "HostSession",
    "Invite",
    "Joined",
    "Left",
    "LinkConditions",
    "LinkStats",
    "MessageReceived",
    "PlayerJoined",
    "PlayerLeft",
    "Refused",
    "SessionEvent",
    "SessionFailed",
    "SimulatedNetwork",
    "Transport",
    "UdpTransport",
    "Versions",
]
