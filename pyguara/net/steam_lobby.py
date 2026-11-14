"""Steam lobbies: who may join a hosted game, and where a guest connects.

A host opens a **friends-only** lobby. Steam shows "Join Game" to the host's
friends through rich presence, and the overlay's invite dialog sends invites.
Being in the lobby is what admits a player: each member who enters becomes
`MemberAdmitted` (allow that Steam ID on the transport) and each who leaves
becomes `MemberRemoved` (revoke it). A guest enters the lobby first and then
connects to its owner, which `LobbyJoined` names.

`SteamLobby` is sans-IO over the slice of `NativeSteam` it uses
(`SteamLobbyApi`), so it runs against a fake in tests. It neither drains
Steam's callbacks nor touches a transport: the caller feeds it every tuple
`NativeSteam.run_callbacks()` returns, and acts on the events it gives back.

Everything from a lobby or a friend's rich presence is untrusted. A lobby ID
arriving that way is parsed strictly by `parse_lobby_id`, and a join request
is only reported -- never acted on -- so the game decides whether to leave
what it is doing.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

CONNECT_KEY = "connect"
"""The rich presence key Steam reads for "Join Game"."""

CONNECT_ARGUMENT = "+connect_lobby"
"""What Steam puts before a lobby ID when it launches the game to join one."""

_MAX_STEAM_ID = 2**64 - 1
_RESULT_OK = 1
_ENTER_SUCCESS = 1
_ENTER_FAILURES = {
    2: "the lobby no longer exists",
    3: "not allowed to join this lobby",
    4: "the lobby is full",
    5: "Steam could not join the lobby",
    6: "banned from this lobby",
    7: "limited Steam accounts cannot join lobbies",
    9: "this Steam account is community banned",
    10: "a member of the lobby has blocked you",
    11: "you have blocked a member of the lobby",
    15: "too many join attempts; try again shortly",
}


class SteamLobbyApi(Protocol):
    """The part of `NativeSteam` a lobby uses."""

    @property
    def steam_id(self) -> int:
        """The local player's Steam ID."""
        ...

    def create_lobby(self, max_members: int) -> None:
        """Create a friends-only lobby."""
        ...

    def join_lobby(self, lobby_id: int) -> None:
        """Enter a lobby."""
        ...

    def leave_lobby(self, lobby_id: int) -> None:
        """Leave a lobby."""
        ...

    def lobby_owner(self, lobby_id: int) -> int:
        """Return the Steam ID owning a lobby, or 0."""
        ...

    def lobby_members(self, lobby_id: int) -> list[int]:
        """Return the members of a lobby this player is in."""
        ...

    def set_rich_presence(self, key: str, value: str) -> bool:
        """Set one rich presence key."""
        ...

    def clear_rich_presence(self) -> None:
        """Clear every rich presence key."""
        ...

    def open_invite_dialog(self, lobby_id: int) -> None:
        """Open the overlay's invite dialog."""
        ...


@dataclass(frozen=True)
class LobbyOpened:
    """The host's lobby exists; friends can see it and be invited."""

    lobby_id: int


@dataclass(frozen=True)
class LobbyJoined:
    """The guest is in the lobby; connect the transport to `host`."""

    lobby_id: int
    host: int


@dataclass(frozen=True)
class LobbyFailed:
    """Opening or joining a lobby failed; the lobby is idle again."""

    reason: str


@dataclass(frozen=True)
class MemberAdmitted:
    """A player entered the host's lobby; allow their Steam ID."""

    steam_id: int


@dataclass(frozen=True)
class MemberRemoved:
    """A player left the host's lobby; revoke their Steam ID."""

    steam_id: int


@dataclass(frozen=True)
class JoinRequested:
    """The player asked, through Steam, to join this lobby.

    Reported rather than acted on: the game decides whether to leave what it
    is doing, then calls `SteamLobby.leave` and `SteamLobby.join`.
    """

    lobby_id: int


LobbyEvent = (
    LobbyOpened
    | LobbyJoined
    | LobbyFailed
    | MemberAdmitted
    | MemberRemoved
    | JoinRequested
)


class LobbyState(enum.Enum):
    """Where a `SteamLobby` is."""

    IDLE = "idle"
    OPENING = "opening"
    HOSTING = "hosting"
    JOINING = "joining"
    JOINED = "joined"


def parse_lobby_id(text: str) -> int | None:
    """Read a lobby ID from untrusted text, or None if it is not one."""
    text = text.strip()
    if not text.isascii() or not text.isdigit() or len(text) > 20:
        return None
    value = int(text)
    return value if 0 < value <= _MAX_STEAM_ID else None


def lobby_from_connect(connect: str) -> int | None:
    """Return the lobby a `+connect_lobby <id>` string names, or None."""
    parts = connect.split()
    if len(parts) != 2 or parts[0] != CONNECT_ARGUMENT:
        return None
    return parse_lobby_id(parts[1])


def lobby_from_args(args: Sequence[str]) -> int | None:
    """Return the lobby Steam launched the game to join, from its arguments.

    Steam starts a game that is not running with `+connect_lobby <id>` when
    the player accepts an invite or joins a friend.
    """
    for index, argument in enumerate(args[:-1]):
        if argument == CONNECT_ARGUMENT:
            return parse_lobby_id(args[index + 1])
    return None


class SteamLobby:
    """One player's lobby: the one they host, or the one they joined.

    Args:
        api: Steam, usually a `NativeSteam`.
    """

    def __init__(self, api: SteamLobbyApi) -> None:
        """Start idle, in no lobby."""
        self._api = api
        self._state = LobbyState.IDLE
        self._lobby = 0
        self._host = 0
        self._admitted: set[int] = set()

    @property
    def state(self) -> LobbyState:
        """Where this lobby is."""
        return self._state

    @property
    def lobby_id(self) -> int:
        """The lobby this player is in, or 0."""
        return self._lobby if self._state in _IN_LOBBY else 0

    @property
    def admitted(self) -> frozenset[int]:
        """The members a host has admitted, itself excluded."""
        return frozenset(self._admitted)

    def host(self, max_players: int) -> None:
        """Open a friends-only lobby for `max_players`, the host included.

        Raises:
            RuntimeError: This player is already in or entering a lobby.
        """
        self._require_idle()
        self._api.create_lobby(max_players)
        self._state = LobbyState.OPENING

    def join(self, lobby_id: int) -> None:
        """Enter `lobby_id` as a guest.

        Raises:
            RuntimeError: This player is already in or entering a lobby.
        """
        self._require_idle()
        self._api.join_lobby(lobby_id)
        self._lobby = lobby_id
        self._state = LobbyState.JOINING

    def invite(self) -> None:
        """Open the overlay's dialog for inviting friends to this lobby.

        Raises:
            RuntimeError: This player is not in a lobby.
        """
        if self._state not in _IN_LOBBY:
            raise RuntimeError("not in a lobby to invite anyone to")
        self._api.open_invite_dialog(self._lobby)

    def leave(self) -> None:
        """Leave the lobby, if in one, and stop showing "Join Game"."""
        if self._state in (*_IN_LOBBY, LobbyState.JOINING):
            self._api.leave_lobby(self._lobby)
        if self._state in _IN_LOBBY:
            self._api.clear_rich_presence()
        self._state = LobbyState.IDLE
        self._lobby = 0
        self._host = 0
        self._admitted.clear()

    def handle(self, callback: tuple[object, ...]) -> list[LobbyEvent]:
        """Take one tuple from `NativeSteam.run_callbacks()`.

        Tuples that are not about this lobby, including the session ones the
        transport takes, give no events.
        """
        match callback:
            case ("lobby_created", int(result), int(lobby)):
                return self._on_created(result, lobby)
            case ("lobby_entered", int(lobby), int(response)):
                return self._on_entered(lobby, response)
            case ("lobby_member", int(lobby), int(member), bool(joined)):
                return self._on_member(lobby, member, joined)
            case ("join_requested", int(lobby)):
                return self._join_requested(lobby)
            case ("connect_requested", str(connect)):
                named = lobby_from_connect(connect)
                return [] if named is None else self._join_requested(named)
        return []

    def _require_idle(self) -> None:
        if self._state is not LobbyState.IDLE:
            raise RuntimeError(f"already {self._state.value}; leave first")

    def _show_join_game(self) -> None:
        self._api.set_rich_presence(CONNECT_KEY, f"{CONNECT_ARGUMENT} {self._lobby}")

    def _on_created(self, result: int, lobby: int) -> list[LobbyEvent]:
        if self._state is not LobbyState.OPENING:
            return []
        if result != _RESULT_OK or lobby == 0:
            self._state = LobbyState.IDLE
            return [LobbyFailed(f"Steam could not create a lobby (EResult {result})")]
        self._state = LobbyState.HOSTING
        self._lobby = lobby
        self._host = self._api.steam_id
        self._show_join_game()
        events: list[LobbyEvent] = [LobbyOpened(lobby)]
        for member in self._api.lobby_members(lobby):
            events.extend(self._on_member(lobby, member, True))
        return events

    def _on_entered(self, lobby: int, response: int) -> list[LobbyEvent]:
        if self._state is not LobbyState.JOINING or lobby != self._lobby:
            return []
        owner = self._api.lobby_owner(lobby) if response == _ENTER_SUCCESS else 0
        if response != _ENTER_SUCCESS or owner in (0, self._api.steam_id):
            if response == _ENTER_SUCCESS:
                self._api.leave_lobby(lobby)
                reason = "the lobby has no host"
            else:
                reason = _ENTER_FAILURES.get(response, f"could not join ({response})")
            self._state = LobbyState.IDLE
            self._lobby = 0
            return [LobbyFailed(reason)]
        self._state = LobbyState.JOINED
        self._host = owner
        self._show_join_game()
        return [LobbyJoined(lobby, owner)]

    def _on_member(self, lobby: int, member: int, joined: bool) -> list[LobbyEvent]:
        if (
            self._state is not LobbyState.HOSTING
            or lobby != self._lobby
            or member == self._api.steam_id
        ):
            return []
        if joined and member not in self._admitted:
            self._admitted.add(member)
            return [MemberAdmitted(member)]
        if not joined and member in self._admitted:
            self._admitted.discard(member)
            return [MemberRemoved(member)]
        return []

    def _join_requested(self, lobby: int) -> list[LobbyEvent]:
        if lobby == 0 or (self._state in _IN_LOBBY and lobby == self._lobby):
            return []
        return [JoinRequested(lobby)]


_IN_LOBBY = (LobbyState.HOSTING, LobbyState.JOINED)
