"""Networked multiplayer: a listen server and the players who join it.

Opt-in, so a single-player game imports none of this. Importing it is always
safe, even with no native extension. A session is what needs one, and fails with
a clear message when it starts.

Everything arriving from the network is untrusted. The Rust core authenticates
packets and survives hostile ones, but it does not make a decoded value
sensible, so code above this package bounds-checks lengths, ids and enums itself.
See `docs/systems/networking.md`.
"""

from pyguara.net.driver import ClientDriver, HostDriver
from pyguara.net.events import EventRelay
from pyguara.net.prediction import (
    CommandSchema,
    PredictedBody,
    PredictionClient,
    PredictionHost,
)
from pyguara.net.replication import Replicated, ReplicationClient, ReplicationHost
from pyguara.net.schema import (
    Angle,
    Choice,
    EntityRef,
    EnumField,
    Flag,
    Int32,
    Quantised,
    QuantisedVector,
    ReplicationSchema,
    UInt8,
    UInt16,
)
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
from pyguara.net.steam import SteamNetwork, SteamTransport
from pyguara.net.steam_lobby import SteamLobby, lobby_from_args
from pyguara.net.transport import Channel, LinkStats, Transport, UdpTransport

__all__ = [
    "Angle",
    "Channel",
    "Choice",
    "ClientDriver",
    "ClientSession",
    "CommandSchema",
    "EntityRef",
    "EnumField",
    "EventRelay",
    "Flag",
    "HostDriver",
    "HostSession",
    "Int32",
    "Invite",
    "Joined",
    "Left",
    "LinkConditions",
    "LinkStats",
    "MessageReceived",
    "PlayerJoined",
    "PlayerLeft",
    "Quantised",
    "PredictedBody",
    "PredictionClient",
    "PredictionHost",
    "QuantisedVector",
    "Refused",
    "Replicated",
    "ReplicationClient",
    "ReplicationHost",
    "ReplicationSchema",
    "SessionEvent",
    "SessionFailed",
    "SimulatedNetwork",
    "SteamLobby",
    "SteamNetwork",
    "SteamTransport",
    "Transport",
    "UInt16",
    "UInt8",
    "UdpTransport",
    "Versions",
    "lobby_from_args",
]
