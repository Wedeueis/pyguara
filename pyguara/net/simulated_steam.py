"""A stand-in for Steam, so a game can test its Steam path with no Steam.

`SimulatedSteamCloud` plays Steam's servers and `SimulatedSteam` one player's
`NativeSteam`. Hand a `SimulatedSteam` to `SteamNetwork` and everything above
it -- the Steam core, the transport, the lobby, the sessions -- is the real
code::

    cloud = SimulatedSteamCloud()
    host = SteamNetwork(cloud.add_player(1001), clock=clock)
    guest = SteamNetwork(cloud.add_player(1002), clock=clock)

What it keeps of Steam is what the transport and lobby depend on:

- A message from someone new raises `session_request` and is held until
  accepted; a peer already sent to is accepted without asking.
- Lobbies are friends-only and capped; entering and leaving reach every
  other member as `lobby_member`; a missing or full lobby is refused with
  Steam's enter response.
- Delivery is instant and lossless, in order. Relay latency and loss are
  what the two-machine playtest is for, not this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_RESULT_OK = 1
_ENTER_SUCCESS = 1
_ENTER_DOESNT_EXIST = 2
_ENTER_FULL = 4
_FIRST_LOBBY = 109775241000000001


@dataclass
class _Lobby:
    owner: int
    size: int
    members: list[int] = field(default_factory=list)


class SimulatedSteamCloud:
    """Steam's servers: who is online, the lobbies, messages in flight."""

    def __init__(self) -> None:
        """Start with nobody online."""
        self.players: dict[int, SimulatedSteam] = {}
        self._lobbies: dict[int, _Lobby] = {}
        self._next_lobby = _FIRST_LOBBY

    def add_player(self, steam_id: int, persona_name: str = "") -> SimulatedSteam:
        """Bring a player online and return their Steam."""
        steam = SimulatedSteam(self, steam_id, persona_name or f"player {steam_id}")
        self.players[steam_id] = steam
        return steam

    def lobby_members(self, lobby_id: int) -> list[int]:
        """Return a lobby's members, or none if it does not exist."""
        lobby = self._lobbies.get(lobby_id)
        return list(lobby.members) if lobby else []

    def _create(self, owner: int, size: int) -> int:
        lobby_id = self._next_lobby
        self._next_lobby += 1
        self._lobbies[lobby_id] = _Lobby(owner, size, [owner])
        return lobby_id

    def _enter(self, lobby_id: int, steam_id: int) -> int:
        lobby = self._lobbies.get(lobby_id)
        if lobby is None:
            return _ENTER_DOESNT_EXIST
        if steam_id not in lobby.members:
            if len(lobby.members) >= lobby.size:
                return _ENTER_FULL
            lobby.members.append(steam_id)
            self._tell(lobby_id, steam_id, True)
        return _ENTER_SUCCESS

    def _leave(self, lobby_id: int, steam_id: int) -> None:
        lobby = self._lobbies.get(lobby_id)
        if lobby is None or steam_id not in lobby.members:
            return
        self._tell(lobby_id, steam_id, False)
        lobby.members.remove(steam_id)
        if not lobby.members:
            del self._lobbies[lobby_id]
        elif lobby.owner == steam_id:
            lobby.owner = lobby.members[0]

    def _owner(self, lobby_id: int) -> int:
        lobby = self._lobbies.get(lobby_id)
        return lobby.owner if lobby else 0

    def _tell(self, lobby_id: int, about: int, joined: bool) -> None:
        for member in self._lobbies[lobby_id].members:
            if member != about and member in self.players:
                self.players[member].callbacks.append(
                    ("lobby_member", lobby_id, about, joined)
                )


class SimulatedSteam:
    """One player's Steam, shaped like `NativeSteam`.

    Attributes:
        steam_id: This player's Steam ID.
        persona_name: Their Steam name.
        callbacks: Waiting for `run_callbacks`; a test may add its own.
        rich_presence: What friends would see.
        accepted_sessions: Every `accept_session`, in order.
        held: Messages from peers not yet accepted, by sender.
        is_shut_down: Whether `shutdown` was called.
    """

    def __init__(
        self, cloud: SimulatedSteamCloud, steam_id: int, persona_name: str
    ) -> None:
        """Use `SimulatedSteamCloud.add_player`."""
        self._cloud = cloud
        self.steam_id = steam_id
        self.persona_name = persona_name
        self.callbacks: list[tuple[Any, ...]] = []
        self.rich_presence: dict[str, str] = {}
        self.accepted_sessions: list[int] = []
        self.held: dict[int, list[bytes]] = {}
        self.is_shut_down = False
        self._inbox: list[tuple[int, bytes]] = []
        self._accepted: set[int] = set()
        self._sent_to: set[int] = set()
        self._lobbies: set[int] = set()

    def init_relay(self) -> None:
        """Nothing to reach."""

    def run_callbacks(self) -> list[tuple[Any, ...]]:
        """Take every callback waiting."""
        taken, self.callbacks = self.callbacks, []
        return taken

    def accept_session(self, steam_id: int) -> bool:
        """Accept a peer, delivering what it sent while held."""
        self.accepted_sessions.append(steam_id)
        self._accepted.add(steam_id)
        self._inbox.extend((steam_id, data) for data in self.held.pop(steam_id, []))
        return True

    def close_session(self, steam_id: int) -> bool:
        """Forget a peer's session."""
        self._accepted.discard(steam_id)
        return True

    def send(self, steam_id: int, data: bytes, reliable: bool = False) -> bool:
        """Deliver at once, or hold it until the peer accepts."""
        self._sent_to.add(steam_id)
        peer = self._cloud.players.get(steam_id)
        if peer is None or peer.is_shut_down:
            return True
        if self.steam_id in peer._accepted or self.steam_id in peer._sent_to:
            peer._inbox.append((self.steam_id, bytes(data)))
            return True
        if self.steam_id not in peer.held:
            peer.callbacks.append(("session_request", self.steam_id))
        peer.held.setdefault(self.steam_id, []).append(bytes(data))
        return True

    def receive(self) -> list[tuple[int, bytes]]:
        """Take every message waiting."""
        taken, self._inbox = self._inbox, []
        return taken

    def create_lobby(self, max_members: int) -> None:
        """Create a lobby; reported by `run_callbacks`."""
        lobby_id = self._cloud._create(self.steam_id, max_members)
        self._lobbies.add(lobby_id)
        self.callbacks.append(("lobby_created", _RESULT_OK, lobby_id))

    def join_lobby(self, lobby_id: int) -> None:
        """Enter a lobby; reported by `run_callbacks`."""
        response = self._cloud._enter(lobby_id, self.steam_id)
        if response == _ENTER_SUCCESS:
            self._lobbies.add(lobby_id)
        self.callbacks.append(("lobby_entered", lobby_id, response))

    def leave_lobby(self, lobby_id: int) -> None:
        """Leave a lobby, telling its other members."""
        self._lobbies.discard(lobby_id)
        self._cloud._leave(lobby_id, self.steam_id)

    def lobby_owner(self, lobby_id: int) -> int:
        """Return the lobby's owner, or 0."""
        return self._cloud._owner(lobby_id)

    def lobby_members(self, lobby_id: int) -> list[int]:
        """Return the lobby's members."""
        return self._cloud.lobby_members(lobby_id)

    def set_rich_presence(self, key: str, value: str) -> bool:
        """Set what friends see."""
        self.rich_presence[key] = value
        return True

    def clear_rich_presence(self) -> None:
        """Clear what friends see."""
        self.rich_presence.clear()

    def open_invite_dialog(self, lobby_id: int) -> None:
        """There is no overlay."""

    def shutdown(self) -> None:
        """Go offline, leaving any lobby."""
        for lobby_id in list(self._lobbies):
            self.leave_lobby(lobby_id)
        self.is_shut_down = True
